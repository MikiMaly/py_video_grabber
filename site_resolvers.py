"""Fallback resolver for pages yt-dlp can't extract directly.

Some tube-style sites embed their player from a generic "file-hosting" backend
(iframe -> POST /dl with a file_code -> JS `sources: [{file:"...m3u8"}]`) that
yt-dlp has no extractor for, and whose CDN also blocks non-browser TLS
fingerprints. This module detects that pattern, replicates the browser flow
with curl_cffi (TLS impersonation), and downloads the resulting HLS stream
directly with ffmpeg-free segment fetching (since ffmpeg's own TLS stack gets
blocked the same way plain urllib does).

Only engaged as a fallback when yt-dlp itself fails to extract a URL.
"""
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

try:
    from curl_cffi import requests as cf_requests
except ImportError:
    cf_requests = None

IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
FILE_CODE_FIELD_RE = re.compile(r'name=["\']file_code["\']\s+value=["\']([^"\']*)["\']', re.IGNORECASE)
SOURCE_M3U8_RE = re.compile(r'file\s*:\s*"([^"]+\.m3u8[^"]*)"')
SOURCE_MP4_RE = re.compile(r'file\s*:\s*"([^"]+\.mp4[^"]*)"')
STREAM_INF_RE = re.compile(
    r'#EXT-X-STREAM-INF:[^\n]*BANDWIDTH=(\d+)[^\n]*\n([^\n#][^\n]*)', re.IGNORECASE)
EXTINF_RE = re.compile(r'#EXTINF:([\d.]+),\s*\n([^\n#][^\n]*)')

IMPERSONATE = "chrome"


@dataclass
class ResolvedStream:
    master_url: str
    referer: str
    title: str = ""
    kind: str = "hls"          # "hls" playlist or a direct "mp4" file


def available() -> bool:
    return cf_requests is not None


def _extract_file_code(embed_url: str) -> str:
    path = embed_url.split("?")[0].split("#")[0].rstrip("/")
    last = path.rsplit("/", 1)[-1]
    return last.rsplit("-", 1)[-1]


def try_resolve_embed_chain(url: str, timeout: int = 20) -> "ResolvedStream | None":
    """Follows: page -> iframe embed -> POST /dl -> direct HLS/mp4 URL."""
    if cf_requests is None:
        return None

    try:
        page = cf_requests.get(url, impersonate=IMPERSONATE, timeout=timeout)
        if page.status_code >= 400:
            return None
        page_html = page.text
    except Exception:
        return None

    title = ""
    m = re.search(r'<title[^>]*>([^<]+)</title>', page_html, re.IGNORECASE)
    if m:
        title = m.group(1).strip()

    for iframe_src in IFRAME_RE.findall(page_html):
        embed_url = urljoin(url, iframe_src)
        resolved = _try_resolve_embed_url(embed_url, referer=url, timeout=timeout)
        if resolved:
            if title and not resolved.title:
                resolved.title = title
            return resolved
    return None


def _try_resolve_embed_url(embed_url: str, referer: str, timeout: int) -> "ResolvedStream | None":
    try:
        headers = {"Referer": referer}
        r = cf_requests.get(embed_url, headers=headers, impersonate=IMPERSONATE, timeout=timeout)
        if r.status_code >= 400:
            return None
        embed_html = r.text
    except Exception:
        return None

    if 'file_code' not in embed_html:
        return None

    code_field = FILE_CODE_FIELD_RE.search(embed_html)
    file_code = code_field.group(1) if (code_field and code_field.group(1)) else _extract_file_code(embed_url)
    if not file_code:
        return None

    dl_url = urljoin(embed_url, "/dl")
    data = {"op": "embed", "file_code": file_code, "auto": "1", "referer": ""}
    try:
        r2 = cf_requests.post(
            dl_url, data=data, headers={"Referer": embed_url},
            impersonate=IMPERSONATE, timeout=timeout,
        )
        if r2.status_code >= 400:
            return None
        body = r2.text
    except Exception:
        return None

    hls_match = SOURCE_M3U8_RE.search(body)
    src_match = hls_match or SOURCE_MP4_RE.search(body)
    if not src_match:
        return None

    return ResolvedStream(
        master_url=src_match.group(1),
        referer=embed_url,
        kind="hls" if hls_match else "mp4",
    )


def _pick_best_variant(master_text: str, base_url: str) -> str:
    variants = STREAM_INF_RE.findall(master_text)
    if not variants:
        return base_url
    best = max(variants, key=lambda v: int(v[0]))
    return urljoin(base_url, best[1].strip())


def _get_segments(variant_text: str, base_url: str):
    segs = EXTINF_RE.findall(variant_text)
    return [(float(dur), urljoin(base_url, uri.strip())) for dur, uri in segs]


def _download_direct(
    resolved: ResolvedStream,
    dest_path: Path,
    ffmpeg_location: str = "",
    progress_hook=None,
    timeout: int = 30,
    cancel_check=None,
    audio_only: bool = False,
) -> Path:
    """Streams a direct mp4 source to dest_path.

    Some embeds hand back a plain file instead of a playlist; fetching that as
    a playlist would pull the whole video into memory and hit the timeout.
    """
    import shutil
    import subprocess
    import time as _time

    headers = {"Referer": resolved.referer}
    tmpdir = Path(tempfile.mkdtemp(prefix="uvd_mp4_"))
    tmp_file = tmpdir / "video.mp4"
    start_time = _time.time()
    downloaded = 0

    try:
        # curl_cffi's Response is not a context manager — close it by hand
        resp = cf_requests.get(
            resolved.master_url, headers=headers, impersonate=IMPERSONATE,
            timeout=max(timeout, 600), stream=True,
        )
        try:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            with open(tmp_file, "wb") as out_f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if cancel_check and cancel_check():
                        raise RuntimeError("cancelled")
                    if not chunk:
                        continue
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if progress_hook:
                        elapsed = max(_time.time() - start_time, 0.01)
                        speed = downloaded / elapsed
                        progress_hook({
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total or downloaded,
                            "speed": speed,
                            "eta": int((total - downloaded) / speed) if (total and speed > 0) else 0,
                        })
        finally:
            resp.close()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if audio_only:
            ffmpeg_bin = ffmpeg_location or "ffmpeg"
            cmd = [ffmpeg_bin, "-y", "-i", str(tmp_file),
                   "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(dest_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg audio extract failed: {result.stderr[-2000:]}")
        else:
            shutil.move(str(tmp_file), str(dest_path))

        if progress_hook:
            progress_hook({"status": "finished", "filename": str(dest_path)})
        return dest_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def download_hls(
    resolved: ResolvedStream,
    dest_path: Path,
    ffmpeg_location: str = "",
    progress_hook=None,
    timeout: int = 30,
    max_workers: int = 4,
    cancel_check=None,
    audio_only: bool = False,
) -> Path:
    """Downloads the resolved HLS stream and remuxes it to dest_path (mp4).

    progress_hook(dict) receives the same shape yt-dlp progress hooks use:
    {'status': 'downloading'|'finished'|'error', 'downloaded_bytes', 'total_bytes', 'speed'}
    """
    if resolved.kind == "mp4":
        return _download_direct(
            resolved, dest_path, ffmpeg_location=ffmpeg_location,
            progress_hook=progress_hook, timeout=timeout,
            cancel_check=cancel_check, audio_only=audio_only,
        )

    import concurrent.futures
    import shutil
    import subprocess
    import time as _time

    headers = {"Referer": resolved.referer}

    master = cf_requests.get(resolved.master_url, headers=headers, impersonate=IMPERSONATE, timeout=timeout)
    master.raise_for_status()
    variant_url = _pick_best_variant(master.text, resolved.master_url)

    variant = cf_requests.get(variant_url, headers=headers, impersonate=IMPERSONATE, timeout=timeout)
    variant.raise_for_status()
    segments = _get_segments(variant.text, variant_url)
    if not segments:
        raise RuntimeError("No HLS segments found in variant playlist")

    total_duration = sum(d for d, _ in segments)
    approx_bitrate_bps = 1_500_000  # rough fallback; refined once first segments land
    total_estimate = int(total_duration * approx_bitrate_bps / 8) or 1

    tmpdir = Path(tempfile.mkdtemp(prefix="uvd_hls_"))
    parts = [None] * len(segments)
    downloaded = [0]
    start_time = _time.time()

    def fetch(i_url):
        i, seg_url = i_url
        if cancel_check and cancel_check():
            return
        last_err = None
        for attempt in range(4):
            try:
                resp = cf_requests.get(seg_url, headers=headers, impersonate=IMPERSONATE, timeout=max(timeout, 60))
                resp.raise_for_status()
                break
            except Exception as e:
                last_err = e
        else:
            raise last_err
        part_path = tmpdir / f"{i:06d}.ts"
        part_path.write_bytes(resp.content)
        parts[i] = part_path
        downloaded[0] += len(resp.content)
        if progress_hook:
            elapsed = max(_time.time() - start_time, 0.01)
            speed = downloaded[0] / elapsed
            done_frac = (i + 1) / len(segments)
            total_now = max(total_estimate, int(downloaded[0] / max(done_frac, 0.01)))
            progress_hook({
                "status": "downloading",
                "downloaded_bytes": downloaded[0],
                "total_bytes": total_now,
                "speed": speed,
                "eta": int((total_now - downloaded[0]) / speed) if speed > 0 else 0,
            })

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(fetch, enumerate(seg_url for _, seg_url in segments)))

        if cancel_check and cancel_check():
            raise RuntimeError("cancelled")

        combined = tmpdir / "combined.ts"
        with open(combined, "wb") as out_f:
            for p in parts:
                if p is None:
                    raise RuntimeError("A segment failed to download")
                with open(p, "rb") as in_f:
                    shutil.copyfileobj(in_f, out_f)

        ffmpeg_bin = ffmpeg_location or "ffmpeg"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if audio_only:
            cmd = [ffmpeg_bin, "-y", "-i", str(combined), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(dest_path)]
        else:
            cmd = [ffmpeg_bin, "-y", "-i", str(combined), "-c", "copy", "-movflags", "+faststart", str(dest_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg remux failed: {result.stderr[-2000:]}")

        if progress_hook:
            progress_hook({"status": "finished", "filename": str(dest_path)})
        return dest_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
