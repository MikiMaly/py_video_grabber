import csv
import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from yt_dlp import YoutubeDL

URL_FINDER = re.compile(r"https?://[^\s,;\"']+", re.IGNORECASE)
INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = INVALID_CHARS_RE.sub("_", name)
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    return name[:max_len] if len(name) > max_len else name


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("download_dir", "./downloads")
    cfg.setdefault("max_workers", 2)
    cfg.setdefault("timeout_sec", 60)
    cfg.setdefault("format", "bv*+ba/b")
    cfg.setdefault("retries", 20)
    cfg.setdefault("fragment_retries", None)
    cfg.setdefault("concurrent_fragments", 3)
    cfg.setdefault("user_agent", "Mozilla/5.0")
    cfg.setdefault("ffmpeg_path", "")
    cfg.setdefault("prefetch_metadata", True)
    cfg.setdefault("prefetch_workers", 1)
    cfg.setdefault("adapt_frags", True)
    cfg.setdefault("adapt_min_frags", 1)
    cfg.setdefault("adapt_max_frags", 16)
    cfg.setdefault("max_retries", 3)
    cfg.setdefault("retry_base_delay", 10)
    cfg.setdefault("state_file", "grabber_state.json")
    return cfg


def fmt_hhmmss(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h}:{m:02d}:{sec:02d}"


def fmt_size(num_bytes: int) -> str:
    if not num_bytes:
        return "?"
    b = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while b >= 1024 and i < len(units) - 1:
        b /= 1024.0
        i += 1
    return f"{int(b)}{units[i]}" if i == 0 else f"{b:.1f}{units[i]}"


def estimate_bytes_from_info(info: dict) -> int:
    if not isinstance(info, dict):
        return 0
    for k in ("filesize", "filesize_approx"):
        v = info.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    rf = info.get("requested_formats")
    if isinstance(rf, list) and rf:
        total = 0
        for f in rf:
            if not isinstance(f, dict):
                continue
            v = f.get("filesize") or f.get("filesize_approx")
            if isinstance(v, (int, float)) and v > 0:
                total += int(v)
        if total > 0:
            return total
    dur = info.get("duration")
    tbr = info.get("tbr")
    if isinstance(dur, (int, float)) and dur > 0 and isinstance(tbr, (int, float)) and tbr > 0:
        return int((tbr * 1000.0 / 8.0) * float(dur))
    return 0


def load_urls_from_csv(csv_path: Path) -> list[str]:
    urls: list[str] = []
    try:
        with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    if not cell:
                        continue
                    for u in URL_FINDER.findall(str(cell)):
                        urls.append(u.strip())
    except Exception:
        return []
    seen: set[str] = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


@dataclass
class Job:
    jid: int
    job_id: str
    url: str
    status: str = "pending"   # pending / queued / downloading / done / fail

    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int = 0

    added_at: float = 0.0
    enqueued_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0

    error: str = ""
    final_path: str = ""

    last_eta: int = -1
    last_eta_check_at: float = 0.0
    eta_bad: bool = False

    meta_done: bool = False
    title: str = ""
    retry_count: int = 0
    priority: int = 0
    retry_after: float = 0.0
    audio_only: bool = False


class GrabberDaemon:
    def __init__(self, cfg: dict, state_path: Path):
        self.cfg = cfg
        self.out_dir = Path(cfg["download_dir"]).expanduser().resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # jobs dict is the single source of truth — no separate queue.Queue
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        # meta prefetch still uses a queue (fire-and-forget pattern)
        self.meta_q: queue.Queue[str] = queue.Queue()
        self.pending: list[str] = []   # job_ids not yet eligible for download

        self._jid_counter = 0
        self._jid_index: dict[int, str] = {}

        self._max_workers = int(cfg.get("max_workers", 2))
        self._running_workers = 0
        self._worker_lock = threading.Lock()

        self._auto_adapt: bool = bool(cfg.get("adapt_frags", True))
        self._adapt_direction: int = 1
        self._adapt_prev_speed: float = 0.0

        self.max_retries = int(cfg.get("max_retries", 3))
        self.retry_base_delay = float(cfg.get("retry_base_delay", 10))

        self._state_path = state_path
        self._shutting_down: bool = False

    # ── internal helpers ──

    def _new_job_id(self, jid: int) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{ts}_{jid:04d}"

    def _queued_count_locked(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status == "queued")

    def _get_next_queued_locked(self) -> str | None:
        """Pick highest-priority queued job and mark it as downloading."""
        candidates = [j for j in self.jobs.values() if j.status == "queued"]
        if not candidates:
            return None
        # Sort: higher priority first, then earlier enqueued_at
        best = max(candidates, key=lambda j: (j.priority, -j.enqueued_at))
        best.status = "downloading"
        if best.started_at == 0.0:
            best.started_at = time.time()
        return best.job_id

    def _enqueue_locked(self, job_id: str):
        j = self.jobs[job_id]
        if j.status != "pending":
            return
        j.status = "queued"
        j.enqueued_at = time.time()
        if self.cfg.get("prefetch_metadata", True) and not (j.title and j.total > 0):
            j.meta_done = False
            self.meta_q.put(job_id)
        else:
            j.meta_done = True

    # ── public API ──

    def add_url(self, url: str, priority: int = 0, audio_only: bool = False) -> str:
        url = (url or "").strip()
        if not url:
            raise ValueError("empty")
        with self.lock:
            for j in self.jobs.values():
                if j.url == url and j.status in ("pending", "queued", "downloading"):
                    raise ValueError("duplicate")
            self._jid_counter += 1
            jid = self._jid_counter
            job_id = self._new_job_id(jid)
            job = Job(jid=jid, job_id=job_id, url=url, added_at=time.time(), priority=priority, audio_only=audio_only)
            self.jobs[job_id] = job
            self._jid_index[jid] = job_id
            self._enqueue_locked(job_id)
        return job_id

    def add_bulk(self, urls: list[str], audio_only: bool = False) -> dict:
        added = 0
        skipped = 0
        for u in urls:
            try:
                self.add_url(u.strip(), audio_only=audio_only)
                added += 1
            except ValueError:
                skipped += 1
        return {"added": added, "skipped": skipped, "total": len(urls)}

    def bump_priority(self, jid: int) -> str:
        with self.lock:
            job_id = self._jid_index.get(jid)
            if not job_id:
                return f"job {jid} not found"
            j = self.jobs.get(job_id)
            if not j:
                return f"job {jid} not found"
            if j.status in ("pending", "queued"):
                j.priority += 1
                return f"ok: job {jid} priority -> {j.priority}"
            return f"job {jid} is {j.status} (not bumpable)"

    def cancel_job(self, jid: int) -> str:
        with self.lock:
            job_id = self._jid_index.get(jid)
            if not job_id:
                return f"job {jid} not found"
            j = self.jobs.get(job_id)
            if not j:
                return f"job {jid} not found"
            if j.status not in ("pending", "queued"):
                return f"job {jid} is {j.status} (can only cancel pending/queued)"
            j.status = "fail"
            j.finished_at = time.time()
            j.error = "cancelled"
            if job_id in self.pending:
                self.pending.remove(job_id)
        return f"ok: job {jid} cancelled"

    def retry_job(self, jid: int) -> str:
        with self.lock:
            job_id = self._jid_index.get(jid)
            if not job_id:
                return f"job {jid} not found"
            j = self.jobs.get(job_id)
            if not j:
                return f"job {jid} not found"
            if j.status != "fail":
                return f"job {jid} is {j.status} (can only retry failed)"
            j.status = "pending"
            j.retry_count = 0
            j.retry_after = 0.0
            j.error = ""
            j.downloaded = 0
            j.total = 0
            j.speed = 0.0
            j.eta = 0
            j.started_at = 0.0
            j.finished_at = 0.0
            j.final_path = ""
            self._enqueue_locked(job_id)
        return f"ok: job {jid} requeued"

    def set_out_dir(self, path: str) -> str:
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.out_dir = p
            self.cfg["download_dir"] = str(p)
        return str(p)

    def set_workers(self, n: int) -> int:
        n = max(1, min(16, int(n)))
        self._max_workers = n
        self.cfg["max_workers"] = n
        # Spawn extra threads if we're increasing
        with self._worker_lock:
            deficit = n - self._running_workers
        for _ in range(max(0, deficit)):
            threading.Thread(target=self.worker_loop, daemon=True).start()
        return n

    def set_format(self, fmt: str) -> None:
        with self.lock:
            self.cfg["format"] = fmt.strip()

    def set_adapt(self, enabled: bool) -> None:
        self._auto_adapt = enabled
        with self.lock:
            self.cfg["adapt_frags"] = enabled

    # ── state persistence ──

    def _save_state(self):
        try:
            with self.lock:
                data = {
                    "version": 1,
                    "jid_counter": self._jid_counter,
                    "jobs": [
                        {
                            "jid": j.jid,
                            "job_id": j.job_id,
                            "url": j.url,
                            "status": j.status,
                            "priority": j.priority,
                            "retry_count": j.retry_count,
                            "title": j.title,
                            "added_at": j.added_at,
                            "finished_at": j.finished_at,
                            "error": j.error,
                            "final_path": j.final_path,
                            "audio_only": j.audio_only,
                        }
                        for j in self.jobs.values()
                    ],
                }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(self._state_path)
        except Exception:
            pass

    def _load_state(self) -> int:
        if not self._state_path.exists():
            return 0
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0
        if data.get("version") != 1:
            return 0
        restored = 0
        seen_urls: set[str] = set()
        max_jid = self._jid_counter
        for jd in data.get("jobs", []):
            if jd.get("status") not in ("pending", "queued", "downloading"):
                continue
            url = str(jd.get("url", ""))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            jid = int(jd["jid"])
            job = Job(
                jid=jid,
                job_id=str(jd["job_id"]),
                url=url,
                status="pending",
                priority=int(jd.get("priority", 0)),
                retry_count=int(jd.get("retry_count", 0)),
                title=str(jd.get("title", "")),
                added_at=float(jd.get("added_at", time.time())),
                audio_only=bool(jd.get("audio_only", False)),
            )
            self.jobs[job.job_id] = job
            self._jid_index[jid] = job.job_id
            self.pending.append(job.job_id)
            max_jid = max(max_jid, jid)
            restored += 1
        self._jid_counter = max_jid
        return restored

    # ── yt-dlp ──

    def _ffmpeg_available(self, ffmpeg_loc: str) -> bool:
        import shutil
        if ffmpeg_loc:
            return Path(ffmpeg_loc).is_file()
        return shutil.which("ffmpeg") is not None

    def _build_ydl_opts(self, job: Job) -> dict:
        if job.title:
            safe_title = sanitize_filename(job.title)
            outtmpl = str(self.out_dir / f"{job.job_id}_{safe_title}.%(ext)s")
        else:
            outtmpl = str(self.out_dir / f"{job.job_id}_%(title)s.%(ext)s")

        headers = {"User-Agent": self.cfg["user_agent"], "Referer": job.url}
        ffmpeg_loc = (self.cfg.get("ffmpeg_path") or "").strip()
        retries = int(self.cfg["retries"])
        frag_cfg = self.cfg.get("fragment_retries")
        fragment_retries = int(frag_cfg) if frag_cfg is not None else retries

        def hook(d):
            with self.lock:
                j = self.jobs.get(job.job_id)
                if not j:
                    return
                st = d.get("status")
                if st == "downloading":
                    if j.started_at == 0.0:
                        j.started_at = time.time()
                    j.status = "downloading"
                    j.downloaded = int(d.get("downloaded_bytes") or 0)
                    new_total = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
                    if new_total > j.total:
                        j.total = new_total
                    j.speed = float(d.get("speed") or 0.0)
                    j.eta = int(d.get("eta") or 0)
                    now2 = time.time()
                    if j.last_eta_check_at == 0.0:
                        j.last_eta_check_at = now2
                        j.last_eta = j.eta
                        j.eta_bad = False
                    elif now2 - j.last_eta_check_at >= 2.0 and j.last_eta >= 0 and j.eta >= 0:
                        actual_drop = j.last_eta - j.eta
                        j.eta_bad = actual_drop < max(1, int(now2 - j.last_eta_check_at) // 2)
                        j.last_eta_check_at = now2
                        j.last_eta = j.eta
                elif st == "finished":
                    fn = d.get("filename")
                    if fn:
                        j.final_path = str(Path(fn).resolve())
                elif st == "error":
                    j.status = "fail"

        if job.audio_only:
            if self._ffmpeg_available(ffmpeg_loc):
                opts_fmt = "ba/b"
                post = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else:
                opts_fmt = "ba[ext=m4a]/ba/b"
                post = []
        else:
            opts_fmt = self.cfg["format"]
            post = []

        opts = {
            "format": opts_fmt,
            "outtmpl": outtmpl,
            "retries": retries,
            "fragment_retries": fragment_retries,
            "concurrent_fragment_downloads": int(self.cfg["concurrent_fragments"]),
            "socket_timeout": int(self.cfg["timeout_sec"]),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "http_headers": headers,
            "progress_hooks": [hook],
        }
        if post:
            opts["postprocessors"] = post
        if not job.audio_only:
            opts["merge_output_format"] = "mp4"
            opts["remuxvideo"] = "mp4"
        if ffmpeg_loc:
            opts["ffmpeg_location"] = ffmpeg_loc
        return opts

    # ── worker threads ──

    def feeder_loop(self):
        """Moves pending jobs (retry wait / overflow) back to queued when ready."""
        while not self.stop_event.is_set():
            if not self._shutting_down:
                with self.lock:
                    now = time.time()
                    ready = [
                        jid for jid in list(self.pending)
                        if jid in self.jobs
                        and self.jobs[jid].status == "pending"
                        and self.jobs[jid].retry_after <= now
                    ]
                    for jid in ready:
                        self.pending.remove(jid)
                        self._enqueue_locked(jid)
            time.sleep(0.2)

    def meta_loop(self):
        while not self.stop_event.is_set():
            try:
                job_id = self.meta_q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                with self.lock:
                    job = self.jobs.get(job_id)
                if not job or job.meta_done:
                    continue
                headers = {"User-Agent": self.cfg["user_agent"], "Referer": job.url}
                ffmpeg_loc = (self.cfg.get("ffmpeg_path") or "").strip()
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noprogress": True,
                    "skip_download": True,
                    "http_headers": headers,
                    "socket_timeout": int(self.cfg["timeout_sec"]),
                    "retries": int(self.cfg["retries"]),
                }
                if ffmpeg_loc:
                    opts["ffmpeg_location"] = ffmpeg_loc
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(job.url, download=False)
                size_bytes = estimate_bytes_from_info(info)
                title = info.get("title", "") if isinstance(info, dict) else ""
                with self.lock:
                    j = self.jobs.get(job_id)
                    if j:
                        if j.total <= 0 and size_bytes > 0:
                            j.total = int(size_bytes)
                        if title and not j.title:
                            j.title = str(title)
                        j.meta_done = True
            except Exception:
                with self.lock:
                    j = self.jobs.get(job_id)
                    if j:
                        j.meta_done = True
            finally:
                self.meta_q.task_done()

    def worker_loop(self):
        with self._worker_lock:
            self._running_workers += 1
        while not self.stop_event.is_set():
            # Gracefully exit if workers were reduced
            with self._worker_lock:
                if self._running_workers > self._max_workers:
                    self._running_workers -= 1
                    return
            job_id = None
            with self.lock:
                if not self._shutting_down:
                    job_id = self._get_next_queued_locked()
            if job_id is None:
                time.sleep(0.1)
                continue
            job = self.jobs.get(job_id)
            if not job:
                time.sleep(0.1)
                continue
            try:
                opts = self._build_ydl_opts(job)
                with YoutubeDL(opts) as ydl:
                    ydl.extract_info(job.url, download=True)
                if not job.final_path:
                    matches = sorted(
                        self.out_dir.glob(job.job_id + "*"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if matches:
                        job.final_path = str(matches[0].resolve())
                mp4 = self.out_dir / f"{job.job_id}.mp4"
                if mp4.exists():
                    job.final_path = str(mp4.resolve())
                with self.lock:
                    job.status = "done"
                    job.finished_at = time.time()
            except Exception as e:
                with self.lock:
                    if job.retry_count < self.max_retries:
                        delay = self.retry_base_delay * (2 ** job.retry_count)
                        job.retry_count += 1
                        job.status = "pending"
                        job.retry_after = time.time() + delay
                        job.started_at = 0.0
                        job.downloaded = 0
                        job.speed = 0.0
                        job.eta = 0
                        job.eta_bad = False
                        job.last_eta_check_at = 0.0
                        self.pending.append(job_id)
                    else:
                        job.status = "fail"
                        job.finished_at = time.time()
                        job.error = str(e)
        with self._worker_lock:
            self._running_workers -= 1

    def _state_save_loop(self):
        while not self.stop_event.is_set():
            time.sleep(10)
            self._save_state()

    def _adaptive_loop(self):
        """Hill-climb concurrent_fragments every 12s to maximise observed throughput."""
        while not self.stop_event.is_set():
            time.sleep(12)
            if not self._auto_adapt:
                self._adapt_prev_speed = 0.0
                self._adapt_direction = 1
                continue
            with self.lock:
                active = [j for j in self.jobs.values() if j.status == "downloading"]
                if not active:
                    self._adapt_prev_speed = 0.0
                    continue
                total_speed = sum(j.speed for j in active)
                cur_frags = int(self.cfg.get("concurrent_fragments", 3))
                min_f = int(self.cfg.get("adapt_min_frags", 1))
                max_f = int(self.cfg.get("adapt_max_frags", 16))
                # if speed dropped >10 % compared to last sample, reverse direction
                if self._adapt_prev_speed > 0 and total_speed < self._adapt_prev_speed * 0.9:
                    self._adapt_direction = -self._adapt_direction
                new_frags = max(min_f, min(max_f, cur_frags + self._adapt_direction))
                self.cfg["concurrent_fragments"] = new_frags
                self._adapt_prev_speed = total_speed

    def start(self):
        for _ in range(self._max_workers):
            threading.Thread(target=self.worker_loop, daemon=True).start()
        if self.cfg.get("prefetch_metadata", True):
            for _ in range(int(self.cfg.get("prefetch_workers", 1))):
                threading.Thread(target=self.meta_loop, daemon=True).start()
        threading.Thread(target=self.feeder_loop, daemon=True).start()
        threading.Thread(target=self._state_save_loop, daemon=True).start()
        threading.Thread(target=self._adaptive_loop, daemon=True).start()
