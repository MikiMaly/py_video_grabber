#!/usr/bin/env python3
import argparse
import asyncio
import sys
import time
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

# PyInstaller: when frozen, modules are in _MEIPASS; otherwise next to this file
if getattr(sys, "frozen", False):
    _base = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    _exe_dir = Path(sys.executable).parent
else:
    _base = Path(__file__).parent
    _exe_dir = Path(__file__).parent

sys.path.insert(0, str(_base))

from v6_4boxed import (
    GrabberDaemon,
    load_config,
    find_csv,
    load_urls_from_csv,
    fmt_hhmmss,
    fmt_size,
)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

daemon: GrabberDaemon | None = None

# ──────────────────────────────────────────────
#  HTML frontend (embedded)
# ──────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Grabber</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; font-size: 14px; overflow: hidden; height: 100vh; display: flex; flex-direction: column; }

  /* ── header ── */
  header { flex-shrink: 0; padding: 10px 20px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 20px; }
  header h1 { font-size: 17px; color: #f0f6fc; font-weight: 600; margin-right: auto; letter-spacing: 0.3px; }
  .stat { display: flex; flex-direction: column; align-items: center; min-width: 48px; }
  .stat-val { font-size: 18px; font-weight: 700; line-height: 1; }
  .stat-lbl { font-size: 10px; color: #8b949e; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.6px; }
  .s-active  .stat-val { color: #58a6ff; }
  .s-queued  .stat-val { color: #8b949e; }
  .s-pending .stat-val { color: #d29922; }
  .s-done    .stat-val { color: #3fb950; }
  .s-fail    .stat-val { color: #f85149; }
  #shutdown-banner { display: none; color: #f85149; font-size: 13px; font-weight: 600; }

  /* ── add-bar ── */
  .add-bar { flex-shrink: 0; padding: 8px 20px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; gap: 8px; align-items: center; }
  .add-bar input { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 7px 12px; color: #c9d1d9; font-size: 14px; outline: none; transition: border-color .15s; }
  .add-bar input:focus { border-color: #58a6ff; }
  .add-bar input::placeholder { color: #484f58; }
  .btn { background: #238636; color: #fff; border: none; border-radius: 6px; padding: 7px 16px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background .15s; white-space: nowrap; }
  .btn:hover { background: #2ea043; }
  .btn-prio { background: #1f6feb; padding: 4px 9px; font-size: 12px; }
  .btn-prio:hover { background: #388bfd; }
  #toast { font-size: 12px; color: #f85149; min-width: 80px; }

  /* ── info bar ── */
  .info-bar { flex-shrink: 0; padding: 4px 20px; font-size: 11px; color: #8b949e; background: #0d1117; border-bottom: 1px solid #21262d; }

  /* ── table ── */
  .table-wrap { flex: 1; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  colgroup .col-id    { width: 44px; }
  colgroup .col-st    { width: 110px; }
  colgroup .col-title { width: auto; }
  colgroup .col-prog  { width: 280px; }
  colgroup .col-act   { width: 74px; }
  thead th { padding: 7px 10px; text-align: left; font-size: 11px; font-weight: 600; color: #8b949e; background: #161b22; border-bottom: 1px solid #30363d; position: sticky; top: 0; z-index: 1; text-transform: uppercase; letter-spacing: 0.5px; }
  tbody tr { border-bottom: 1px solid #21262d; transition: background .1s; }
  tbody tr:hover { background: #161b22; }
  td { padding: 7px 10px; vertical-align: middle; overflow: hidden; }

  /* ── status badges ── */
  .badge { display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase; }
  .b-downloading { background: #1f3a5f; color: #58a6ff; }
  .b-queued      { background: #2d333b; color: #8b949e; }
  .b-pending     { background: #2d2208; color: #d29922; }
  .b-done        { background: #1a3d2b; color: #3fb950; }
  .b-fail        { background: #3d1a1a; color: #f85149; }

  /* ── title cell ── */
  .t-title { font-weight: 500; color: #f0f6fc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-url   { font-size: 11px; color: #484f58; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }

  /* ── progress cell ── */
  .bar-bg   { background: #21262d; border-radius: 4px; height: 5px; margin-bottom: 5px; }
  .bar-fill { height: 5px; border-radius: 4px; background: #58a6ff; transition: width 0.6s linear; }
  .prog-row { display: flex; gap: 10px; font-size: 12px; color: #8b949e; flex-wrap: wrap; }
  .pct   { color: #c9d1d9; font-weight: 600; }
  .spd   { color: #3fb950; }
  .eta   { color: #58a6ff; }
  .eta.bad { color: #f85149; }
  .dim   { color: #484f58; }
  .retry-tag { color: #d29922; font-size: 11px; }
  .prio-tag  { color: #58a6ff; font-size: 11px; }
  .path-txt  { font-size: 11px; color: #8b949e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .err-txt   { font-size: 11px; color: #f85149; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* ── status line ── */
  .statusline { flex-shrink: 0; padding: 4px 20px; font-size: 11px; color: #484f58; background: #161b22; border-top: 1px solid #30363d; }
  .empty-row td { padding: 40px; text-align: center; color: #484f58; }
</style>
</head>
<body>

<header>
  <h1>&#9660; Video Grabber</h1>
  <span id="shutdown-banner">&#9888; Shutting down&hellip;</span>
  <div class="stat s-active" ><span class="stat-val" id="s-active">0</span><span class="stat-lbl">active</span></div>
  <div class="stat s-queued" ><span class="stat-val" id="s-queued">0</span><span class="stat-lbl">queued</span></div>
  <div class="stat s-pending"><span class="stat-val" id="s-pending">0</span><span class="stat-lbl">pending</span></div>
  <div class="stat s-done"   ><span class="stat-val" id="s-done">0</span><span class="stat-lbl">done</span></div>
  <div class="stat s-fail"   ><span class="stat-val" id="s-fail">0</span><span class="stat-lbl">fail</span></div>
</header>

<div class="add-bar">
  <input type="text" id="url-input" placeholder="Vlo&#382; URL videa a stiskni Enter&hellip;" autocomplete="off" spellcheck="false">
  <button class="btn" onclick="addUrl()">+ P&#345;idat</button>
  <span id="toast"></span>
</div>

<div class="info-bar" id="info-bar">Načítám&hellip;</div>

<div class="table-wrap">
  <table>
    <colgroup>
      <col class="col-id">
      <col class="col-st">
      <col class="col-title">
      <col class="col-prog">
      <col class="col-act">
    </colgroup>
    <thead>
      <tr>
        <th>#</th>
        <th>Status</th>
        <th>Název / URL</th>
        <th>Průběh</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="jobs-body">
      <tr class="empty-row"><td colspan="5">Žádné joby&hellip;</td></tr>
    </tbody>
  </table>
</div>

<div class="statusline" id="statusline">Připojuji&hellip;</div>

<script>
const input = document.getElementById('url-input');
input.addEventListener('keydown', e => { if (e.key === 'Enter') addUrl(); });

let toastTimer = null;
function showToast(msg, color) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.color = color || '#f85149';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.textContent = ''; }, 3000);
}

async function addUrl() {
  const url = input.value.trim();
  if (!url) return;
  input.value = '';
  const r = await fetch('/api/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url})
  });
  const d = await r.json();
  if (!d.ok) showToast(d.error === 'duplicate' ? 'Duplicitní URL' : d.error);
  else showToast('Přidáno ✓', '#3fb950');
}

async function bumpPriority(jid) {
  await fetch('/api/priority', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({jid})
  });
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtSize(b) {
  if (!b) return '?';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return i === 0 ? Math.round(b) + u[i] : b.toFixed(1) + u[i];
}

function renderJob(j) {
  const badgeClass = `badge b-${j.status}`;
  const badgeLabel = j.status === 'downloading' ? 'Stahuje' :
                     j.status === 'queued'      ? 'Ve frontě' :
                     j.status === 'pending'     ? 'Čeká' :
                     j.status === 'done'        ? 'Hotovo' : 'Chyba';

  const titleHtml = j.title
    ? `<div class="t-title">${esc(j.title)}</div><div class="t-url">${esc(j.url)}</div>`
    : `<div class="t-url" style="color:#8b949e">${esc(j.url)}</div>`;

  let progHtml = '';
  let actHtml  = '';

  if (j.status === 'downloading') {
    const pct = j.progress_pct || 0;
    const etaCls = j.eta_bad ? 'eta bad' : 'eta';
    progHtml = `
      <div class="bar-bg"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="prog-row">
        <span class="pct">${pct.toFixed(1)}%</span>
        <span>${fmtSize(j.downloaded)} / ${j.total_str}</span>
        <span class="spd">${j.speed_str}</span>
        ${j.eta_str ? `<span class="${etaCls}">ETA ${j.eta_str}</span>` : ''}
        <span class="dim">ELAP ${j.elapsed_str}</span>
      </div>`;
  } else if (j.status === 'queued') {
    progHtml = `<span class="dim">Do fronty: ${j.enqueued_at}</span>`;
  } else if (j.status === 'pending') {
    const now = Date.now() / 1000;
    let badge = '';
    if (j.retry_count > 0 && j.retry_after > now) {
      const w = Math.ceil(j.retry_after - now);
      badge = `<span class="retry-tag"> · retry ${j.retry_count}/${j.max_retries} za ${w}s</span>`;
    } else if (j.retry_count > 0) {
      badge = `<span class="retry-tag"> · retry ${j.retry_count}/${j.max_retries}</span>`;
    } else if (j.priority > 0) {
      badge = `<span class="prio-tag"> · prio+${j.priority}</span>`;
    }
    progHtml = `<span class="dim">Přidáno ${j.added_at}</span>${badge}`;
    actHtml  = `<button class="btn btn-prio" onclick="bumpPriority(${j.jid})">&#8679; Prio</button>`;
  } else if (j.status === 'done') {
    const fname = j.final_path ? j.final_path.replace(/\\\\/g,'/').split('/').pop() : '?';
    progHtml = `
      <div class="path-txt" title="${esc(j.final_path)}">${esc(fname)}</div>
      <div class="prog-row"><span>${j.total_str}</span><span class="dim">za ${j.elapsed_str}</span></div>`;
  } else if (j.status === 'fail') {
    progHtml = `<div class="err-txt" title="${esc(j.error)}">${esc(j.error || 'neznámá chyba')}</div>`;
  }

  return `<tr>
    <td style="color:#8b949e;font-size:12px">${j.jid}</td>
    <td><span class="${badgeClass}">${badgeLabel}</span></td>
    <td>${titleHtml}</td>
    <td>${progHtml}</td>
    <td>${actHtml}</td>
  </tr>`;
}

async function refresh() {
  try {
    const r = await fetch('/api/state');
    const d = await r.json();
    const s = d.stats;

    document.getElementById('s-active').textContent  = s.active;
    document.getElementById('s-queued').textContent  = s.queued;
    document.getElementById('s-pending').textContent = s.pending;
    document.getElementById('s-done').textContent    = s.done;
    document.getElementById('s-fail').textContent    = s.fail;

    document.getElementById('info-bar').textContent =
      `Výstup: ${s.out_dir}   Workers: ${s.workers}   Limit fronty: ${s.queue_limit}`;

    document.getElementById('shutdown-banner').style.display = s.shutting_down ? 'inline' : 'none';

    const tbody = document.getElementById('jobs-body');
    if (d.jobs.length === 0) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">Žádné joby – vlož URL výše</td></tr>';
    } else {
      tbody.innerHTML = d.jobs.map(renderJob).join('');
    }

    document.getElementById('statusline').textContent =
      `Aktualizováno: ${new Date().toLocaleTimeString('cs-CZ')}`;
  } catch (e) {
    document.getElementById('statusline').textContent = 'Spojení ztraceno – opakuji…';
  }
}

refresh();
setInterval(refresh, 1000);
</script>
</body>
</html>"""


# ──────────────────────────────────────────────
#  FastAPI
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if daemon:
        with daemon.lock:
            daemon._shutting_down = True
        for _ in range(60):
            with daemon.lock:
                active = sum(1 for j in daemon.jobs.values() if j.status == "downloading")
            if active == 0:
                break
            await asyncio.sleep(0.5)
        daemon._save_state()
        daemon.stop_event.set()


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML


@app.get("/api/state")
async def get_state():
    now = time.time()
    with daemon.lock:
        jobs_list = []
        for j in daemon.jobs.values():
            pct = (j.downloaded / j.total * 100) if j.total > 0 else 0
            end = j.finished_at if j.finished_at else now
            elapsed = (end - j.started_at) if j.started_at else 0
            jobs_list.append({
                "jid": j.jid,
                "url": j.url,
                "status": j.status,
                "title": j.title or "",
                "downloaded": j.downloaded,
                "total": j.total,
                "speed": j.speed,
                "eta": j.eta,
                "progress_pct": round(pct, 1),
                "speed_str": f"{j.speed / 1_048_576:.1f} MB/s" if j.speed else "",
                "eta_str": fmt_hhmmss(j.eta) if j.eta else "",
                "elapsed_str": fmt_hhmmss(elapsed),
                "total_str": fmt_size(j.total),
                "retry_count": j.retry_count,
                "max_retries": daemon.max_retries,
                "priority": j.priority,
                "error": j.error[:200] if j.error else "",
                "final_path": j.final_path or "",
                "enqueued_at": time.strftime("%H:%M:%S", time.localtime(j.enqueued_at)) if j.enqueued_at else "",
                "added_at": time.strftime("%H:%M:%S", time.localtime(j.added_at)) if j.added_at else "",
                "retry_after": j.retry_after,
                "eta_bad": j.eta_bad,
                "_sort": (
                    {"downloading": 0, "queued": 1, "pending": 2, "fail": 3, "done": 4}.get(j.status, 9),
                    -j.priority if j.status == "pending" else 0,
                    -j.jid,
                ),
            })

        jobs_list.sort(key=lambda x: x["_sort"])
        for j in jobs_list:
            del j["_sort"]

        stats = {
            "active":      sum(1 for j in daemon.jobs.values() if j.status == "downloading"),
            "queued":      sum(1 for j in daemon.jobs.values() if j.status == "queued"),
            "pending":     sum(1 for j in daemon.jobs.values() if j.status == "pending"),
            "done":        sum(1 for j in daemon.jobs.values() if j.status == "done"),
            "fail":        sum(1 for j in daemon.jobs.values() if j.status == "fail"),
            "workers":     int(daemon.cfg["max_workers"]),
            "queue_limit": daemon.queue_limit,
            "out_dir":     str(daemon.out_dir),
            "shutting_down": daemon._shutting_down,
        }

    return {"stats": stats, "jobs": jobs_list}


class AddReq(BaseModel):
    url: str


class PrioReq(BaseModel):
    jid: int


@app.post("/api/add")
async def add_url(req: AddReq):
    try:
        job_id = daemon.add_url(req.url.strip())
        return {"ok": True, "job_id": job_id}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/priority")
async def bump_priority(req: PrioReq):
    msg = daemon.bump_priority(req.jid)
    return {"ok": True, "message": msg}


# ──────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────

def main():
    global daemon

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    # When frozen as .exe, resolve config relative to the exe directory
    if getattr(sys, "frozen", False) and not Path(args.config).is_absolute():
        args.config = str(_exe_dir / args.config)

    cfg = load_config(args.config)
    config_dir = Path(args.config).resolve().parent
    state_path = (config_dir / cfg.get("state_file", "grabber_state.json")).resolve()

    daemon = GrabberDaemon(cfg, state_path)
    daemon._load_state()
    daemon.start(web_mode=True)

    if cfg.get("csv_autoload", True):
        csv_path = find_csv(config_dir, cfg)
        if csv_path:
            urls = load_urls_from_csv(csv_path)
            count = daemon.add_many_urls(urls)
            daemon.csv_loaded_from = csv_path.name
            daemon.csv_loaded_count = count

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    print(f"Video Grabber → http://localhost:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
