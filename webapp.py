#!/usr/bin/env python3
import argparse
import asyncio
import sys
import time
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

if getattr(sys, "frozen", False):
    _base = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    _exe_dir = Path(sys.executable).parent
else:
    _base = Path(__file__).parent
    _exe_dir = Path(__file__).parent

sys.path.insert(0, str(_base))

from grabber import GrabberDaemon, load_config, fmt_hhmmss, fmt_size

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

daemon: GrabberDaemon | None = None


def _d() -> GrabberDaemon:
    assert daemon is not None, "Daemon not initialized"
    return daemon

# ──────────────────────────────────────────────
#  HTML
# ──────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Grabber</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', system-ui, sans-serif;
         font-size: 14px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

  /* ── header ── */
  header { flex-shrink: 0; padding: 8px 20px; background: #161b22; border-bottom: 1px solid #30363d;
           display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  header h1 { font-size: 16px; color: #f0f6fc; font-weight: 600; margin-right: auto; }
  .stat { display: flex; flex-direction: column; align-items: center; min-width: 44px; }
  .stat-val { font-size: 17px; font-weight: 700; line-height: 1; }
  .stat-lbl { font-size: 10px; color: #8b949e; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
  .s-active .stat-val { color: #58a6ff; }
  .s-queue  .stat-val { color: #d29922; }
  .s-done   .stat-val { color: #3fb950; }
  .s-fail   .stat-val { color: #f85149; }
  #shutdown-banner { display: none; color: #f85149; font-size: 12px; font-weight: 600; }

  /* workers control */
  .workers-ctrl { display: flex; align-items: center; gap: 5px; border-left: 1px solid #30363d; padding-left: 16px; }
  .btn-adj { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px;
             width: 22px; height: 22px; cursor: pointer; font-size: 15px; line-height: 1;
             display: flex; align-items: center; justify-content: center; padding: 0; }
  .btn-adj:hover { background: #388bfd; border-color: #388bfd; }
  #workers-val { font-size: 17px; font-weight: 700; color: #c9d1d9; min-width: 18px; text-align: center; }

  /* ── staging ── */
  .staging { flex-shrink: 0; background: #161b22; border-bottom: 2px solid #30363d; }
  .stage-input-row { display: flex; gap: 8px; align-items: center; padding: 10px 20px; border-bottom: 1px solid #21262d; }
  .stage-input-row input { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                            padding: 8px 12px; color: #c9d1d9; font-size: 14px; outline: none; transition: border-color .15s; }
  .stage-input-row input:focus { border-color: #58a6ff; }
  .stage-input-row input::placeholder { color: #484f58; }
  .stage-list { max-height: 130px; overflow-y: auto; }
  .stage-item { display: flex; align-items: center; gap: 8px; padding: 4px 20px; border-bottom: 1px solid #21262d; }
  .stage-item:last-child { border-bottom: none; }
  .stage-url { flex: 1; font-size: 12px; color: #8b949e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .staged-empty { padding: 8px 20px; font-size: 12px; color: #484f58; }
  .stage-footer { display: flex; align-items: center; gap: 10px; padding: 8px 20px; flex-wrap: wrap; }
  .folder-row { display: flex; align-items: center; gap: 6px; margin-left: auto; }
  .folder-input { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                  padding: 5px 10px; color: #c9d1d9; font-size: 12px; width: 260px; outline: none; transition: border-color .15s; }
  .folder-input:focus { border-color: #58a6ff; }
  .fmt-select { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                padding: 5px 8px; color: #c9d1d9; font-size: 12px; outline: none; cursor: pointer; }
  .fmt-select:focus { border-color: #58a6ff; }

  /* ── buttons ── */
  .btn { background: #238636; color: #fff; border: none; border-radius: 6px; padding: 7px 16px;
         cursor: pointer; font-size: 14px; font-weight: 500; transition: background .15s; white-space: nowrap; }
  .btn:hover { background: #2ea043; }
  .btn:disabled { background: #21262d; color: #484f58; cursor: default; }
  .btn-danger { background: #6e7681; }
  .btn-danger:hover { background: #8b949e; }
  .btn-sm { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px;
            padding: 5px 10px; cursor: pointer; font-size: 12px; transition: background .15s; white-space: nowrap; }
  .btn-sm:hover { background: #30363d; }
  .btn-prio   { background: #1f6feb; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-prio:hover   { background: #388bfd; }
  .btn-cancel { background: #6e7681; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-cancel:hover { background: #8b949e; }
  .btn-retry  { background: #388bfd; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-retry:hover  { background: #58a6ff; }
  .btn-remove { background: none; border: none; color: #484f58; cursor: pointer; font-size: 14px; padding: 0 4px; }
  .btn-remove:hover { color: #f85149; }
  #toast { font-size: 12px; min-width: 80px; }

  /* ── table ── */
  .table-wrap { flex: 1; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  colgroup .col-id  { width: 40px; }
  colgroup .col-st  { width: 100px; }
  colgroup .col-ttl { width: auto; }
  colgroup .col-prg { width: 270px; }
  colgroup .col-act { width: 130px; }
  thead th { padding: 6px 10px; text-align: left; font-size: 11px; font-weight: 600; color: #8b949e;
             background: #161b22; border-bottom: 1px solid #30363d; position: sticky; top: 0; z-index: 1;
             text-transform: uppercase; letter-spacing: 0.5px; }
  tbody tr { border-bottom: 1px solid #21262d; transition: background .1s; }
  tbody tr:hover { background: #161b22; }
  td { padding: 6px 10px; vertical-align: middle; overflow: hidden; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .b-downloading { background: #1f3a5f; color: #58a6ff; }
  .b-queued      { background: #2d2208; color: #d29922; }
  .b-pending     { background: #2d2208; color: #d29922; }
  .b-done        { background: #1a3d2b; color: #3fb950; }
  .b-fail        { background: #3d1a1a; color: #f85149; }
  .t-title { font-weight: 500; color: #f0f6fc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-url   { font-size: 11px; color: #484f58; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
  .bar-bg  { background: #21262d; border-radius: 4px; height: 5px; margin-bottom: 4px; }
  .bar-fill{ height: 5px; border-radius: 4px; background: #58a6ff; transition: width 0.6s linear; }
  .prog-row{ display: flex; gap: 8px; font-size: 12px; color: #8b949e; flex-wrap: wrap; }
  .pct { color: #c9d1d9; font-weight: 600; }
  .spd { color: #3fb950; }
  .eta { color: #58a6ff; }
  .eta.bad { color: #f85149; }
  .elap { color: #d29922; }
  .dim { color: #484f58; }
  .retry-tag { color: #d29922; font-size: 11px; }
  .prio-tag  { color: #58a6ff; font-size: 11px; }
  .path-txt  { font-size: 11px; color: #8b949e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .err-txt   { font-size: 11px; color: #f85149; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .act-btns  { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
  .empty-row td { padding: 40px; text-align: center; color: #484f58; }
  .statusline { flex-shrink: 0; padding: 3px 20px; font-size: 11px; color: #484f58;
                background: #161b22; border-top: 1px solid #30363d; }
</style>
</head>
<body>

<header>
  <h1>&#9660; Video Grabber</h1>
  <span id="shutdown-banner">&#9888; Shutting down&hellip;</span>
  <div class="stat s-active"><span class="stat-val" id="s-active">0</span><span class="stat-lbl">active</span></div>
  <div class="stat s-queue" ><span class="stat-val" id="s-queue" >0</span><span class="stat-lbl">queue</span></div>
  <div class="stat s-done"  ><span class="stat-val" id="s-done"  >0</span><span class="stat-lbl">done</span></div>
  <div class="stat s-fail"  ><span class="stat-val" id="s-fail"  >0</span><span class="stat-lbl">fail</span></div>
  <div class="workers-ctrl">
    <button class="btn-adj" onclick="adjustWorkers(-1)">&#8722;</button>
    <span id="workers-val">2</span>
    <button class="btn-adj" onclick="adjustWorkers(+1)">&#43;</button>
    <span class="stat-lbl">workers</span>
  </div>
</header>

<div class="staging">
  <div class="stage-input-row">
    <input type="text" id="url-input"
           placeholder="URL nebo domena.com/video — Enter nebo klikni P&#345;idat&hellip;"
           autocomplete="off" spellcheck="false">
    <button class="btn" onclick="addToStaging()">+ P&#345;idat</button>
    <span id="toast"></span>
  </div>
  <div class="stage-list" id="stage-list">
    <div class="staged-empty">Fronta je pr&#225;zdn&#225; &ndash; vlo&#382; URL v&#253;&#353;e</div>
  </div>
  <div class="stage-footer">
    <button class="btn" id="btn-dl-all" onclick="downloadAll()" disabled>&#9654; Sta&#382;en&#237; (0)</button>
    <button class="btn btn-danger" id="btn-clear" onclick="clearStaging()" style="display:none">&#10005; Zru&#353;it v&#353;e</button>
    <div class="folder-row">
      <select class="fmt-select" id="fmt-select" onchange="changeFormat(this.value)" title="Form&#225;t">
        <option value="bv*+ba/b">Nejlep&#353;&#237; kvalita</option>
        <option value="bv[height<=1080]+ba/b">Max 1080p</option>
        <option value="bv[height<=720]+ba/b">Max 720p</option>
        <option value="bv[height<=480]+ba/b">Max 480p</option>
        <option value="worst/w">Nejmen&#353;&#237; soubor</option>
      </select>
      <span style="color:#8b949e;font-size:12px">Slo&#382;ka:</span>
      <input type="text" id="out-dir-input" class="folder-input" placeholder="&hellip;">
      <button class="btn-sm" onclick="browseFolder()" title="Vybrat slo&#382;ku">&#128193;</button>
      <button class="btn-sm" onclick="changeOutDir()">Zm&#283;nit</button>
    </div>
  </div>
</div>

<div class="table-wrap">
  <table>
    <colgroup>
      <col class="col-id"><col class="col-st"><col class="col-ttl"><col class="col-prg"><col class="col-act">
    </colgroup>
    <thead>
      <tr><th>#</th><th>Status</th><th>N&#225;zev / URL</th><th>Pr&#367;b&#283;h</th><th></th></tr>
    </thead>
    <tbody id="jobs-body">
      <tr class="empty-row"><td colspan="5">&#381;&#225;dn&#233; joby&hellip;</td></tr>
    </tbody>
  </table>
</div>

<div class="statusline" id="statusline">P&#345;ipojuji&hellip;</div>

<script>
// ── URL normalization ──
function normalizeUrl(raw) {
  raw = raw.trim();
  if (!raw) return null;
  // Already has scheme
  if (/^https?:\/\//i.test(raw)) return raw;
  // Looks like a domain/path — prepend https://
  if (raw.includes('.') && !raw.startsWith(' ')) return 'https://' + raw;
  return null;
}

// ── staging ──
let stagedUrls = [];

const urlInput = document.getElementById('url-input');
urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') addToStaging(); });
urlInput.addEventListener('paste', () => {
  setTimeout(() => {
    const text = urlInput.value;
    const parts = text.split(/[\n\r,;]+/);
    if (parts.length > 1) {
      parts.forEach(p => { const u = normalizeUrl(p); if (u) pushStaged(u); });
      urlInput.value = '';
      renderStaging();
    }
  }, 0);
});

function pushStaged(url) {
  if (url && !stagedUrls.includes(url)) { stagedUrls.push(url); return true; }
  return false;
}

function addToStaging() {
  const raw = urlInput.value.trim();
  if (!raw) return;
  // Split on whitespace/comma/semicolon and try each token
  const tokens = raw.split(/[\s,;]+/);
  let added = 0;
  tokens.forEach(t => { const u = normalizeUrl(t); if (u && pushStaged(u)) added++; });
  urlInput.value = '';
  renderStaging();
  if (added) showToast(added + ' URL přidáno ✓', '#3fb950');
  else showToast('Žádné platné URL');
}

function removeStaged(i) { stagedUrls.splice(i, 1); renderStaging(); }
function clearStaging()   { stagedUrls = []; renderStaging(); }

function renderStaging() {
  const list   = document.getElementById('stage-list');
  const btnDl  = document.getElementById('btn-dl-all');
  const btnCl  = document.getElementById('btn-clear');
  btnDl.textContent = '▶ Stažení (' + stagedUrls.length + ')';
  btnDl.disabled = stagedUrls.length === 0;
  btnCl.style.display = stagedUrls.length ? '' : 'none';
  if (!stagedUrls.length) {
    list.innerHTML = '<div class="staged-empty">Fronta je prázdná – vlož URL výše</div>';
    return;
  }
  list.innerHTML = stagedUrls.map((url, i) =>
    '<div class="stage-item">' +
      '<span class="stage-url" title="' + esc(url) + '">' + esc(url) + '</span>' +
      '<button class="btn-remove" onclick="removeStaged(' + i + ')">&#10005;</button>' +
    '</div>'
  ).join('');
}

async function downloadAll() {
  if (!stagedUrls.length) return;
  const btn = document.getElementById('btn-dl-all');
  btn.disabled = true;
  btn.textContent = 'Odesílám…';
  try {
    const r = await fetch('/api/add_bulk', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({urls: stagedUrls})
    });
    const d = await r.json();
    showToast('Zahájeno: ' + d.added + '/' + d.total + ' ✓', '#3fb950');
    clearStaging();
  } catch(e) {
    showToast('Chyba spojení');
    renderStaging();
  }
}

// ── folder & format ──
let folderReady = false;

async function browseFolder() {
  const r = await fetch('/api/browse_folder');
  const d = await r.json();
  if (d.ok) {
    document.getElementById('out-dir-input').value = d.path;
    showToast('Složka změněna ✓', '#3fb950');
  } else if (!d.cancelled) {
    showToast(d.error || 'Chyba');
  }
}

async function changeOutDir() {
  const inp  = document.getElementById('out-dir-input');
  const path = inp.value.trim();
  if (!path) return;
  const r = await fetch('/api/set_outdir', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})
  });
  const d = await r.json();
  if (d.ok) { inp.value = d.path; showToast('Složka změněna ✓', '#3fb950'); }
  else showToast(d.error);
}
document.getElementById('out-dir-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') changeOutDir();
});

async function changeFormat(fmt) {
  await fetch('/api/set_format', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fmt})
  });
}

// ── workers ──
async function adjustWorkers(delta) {
  const cur = parseInt(document.getElementById('workers-val').textContent) || 1;
  const n   = Math.max(1, Math.min(16, cur + delta));
  const r   = await fetch('/api/set_workers', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({n})
  });
  const d = await r.json();
  if (d.ok) document.getElementById('workers-val').textContent = d.workers;
}

// ── job actions ──
async function bumpPriority(jid) {
  await fetch('/api/priority', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({jid}) });
}
async function cancelJob(jid) {
  await fetch('/api/cancel', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({jid}) });
}
async function retryJob(jid) {
  await fetch('/api/retry', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({jid}) });
}

// ── helpers ──
let toastTimer = null;
function showToast(msg, color) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.color = color || '#f85149';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.textContent = ''; }, 3000);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtSize(b) {
  if (!b) return '?';
  const u = ['B','KB','MB','GB','TB']; let i = 0;
  while (b >= 1024 && i < u.length-1) { b /= 1024; i++; }
  return i === 0 ? Math.round(b)+u[i] : b.toFixed(1)+u[i];
}

// ── render jobs ──
function renderJob(j) {
  const labels = {downloading:'Stahuje', queued:'Ve frontě', pending:'Čeká', done:'Hotovo', fail:'Chyba'};
  const titleHtml = j.title
    ? '<div class="t-title">'+esc(j.title)+'</div><div class="t-url">'+esc(j.url)+'</div>'
    : '<div class="t-url" style="color:#8b949e">'+esc(j.url)+'</div>';

  let progHtml = '', actHtml = '';

  if (j.status === 'downloading') {
    const pct = j.progress_pct || 0;
    progHtml =
      '<div class="bar-bg"><div class="bar-fill" style="width:'+pct+'%"></div></div>' +
      '<div class="prog-row">' +
        '<span class="pct">'+pct.toFixed(1)+'%</span>' +
        '<span>'+fmtSize(j.downloaded)+' / '+j.total_str+'</span>' +
        '<span class="spd">'+j.speed_str+'</span>' +
        '<span class="elap">čas stahování '+j.elapsed_str+'</span>' +
        (j.eta_str ? '<span class="eta'+(j.eta_bad?' bad':'')+'">čas do stažení '+j.eta_str+'</span>' : '') +
      '</div>';

  } else if (j.status === 'queued') {
    progHtml = '<span class="dim">Ve frontě od '+j.enqueued_at+'</span>';
    actHtml  =
      '<div class="act-btns">' +
        '<button class="btn-prio"   onclick="bumpPriority('+j.jid+')">↑ Prio</button>' +
        '<button class="btn-cancel" onclick="cancelJob('+j.jid+')">✕</button>' +
      '</div>';

  } else if (j.status === 'pending') {
    const now = Date.now() / 1000;
    let badge = '';
    if (j.retry_count > 0 && j.retry_after > now) {
      badge = '<span class="retry-tag">· retry '+j.retry_count+'/'+j.max_retries+' za '+Math.ceil(j.retry_after-now)+'s</span>';
    } else if (j.retry_count > 0) {
      badge = '<span class="retry-tag">· retry '+j.retry_count+'/'+j.max_retries+'</span>';
    } else if (j.priority > 0) {
      badge = '<span class="prio-tag">· prio+'+j.priority+'</span>';
    }
    progHtml = '<span class="dim">Přidáno '+j.added_at+'</span>'+badge;
    actHtml  =
      '<div class="act-btns">' +
        '<button class="btn-prio"   onclick="bumpPriority('+j.jid+')">↑ Prio</button>' +
        '<button class="btn-cancel" onclick="cancelJob('+j.jid+')">✕</button>' +
      '</div>';

  } else if (j.status === 'done') {
    const fname = j.final_path ? j.final_path.replace(/\\/g,'/').split('/').pop() : '?';
    progHtml =
      '<div class="path-txt" title="'+esc(j.final_path)+'">'+esc(fname)+'</div>' +
      '<div class="prog-row"><span>'+j.total_str+'</span><span class="dim">za '+j.elapsed_str+'</span></div>';

  } else if (j.status === 'fail') {
    progHtml = '<div class="err-txt" title="'+esc(j.error)+'">'+esc(j.error||'neznámá chyba')+'</div>';
    actHtml  = '<button class="btn-retry" onclick="retryJob('+j.jid+')">↺ Retry</button>';
  }

  return '<tr>' +
    '<td style="color:#8b949e;font-size:12px">'+j.jid+'</td>' +
    '<td><span class="badge b-'+j.status+'">'+(labels[j.status]||j.status)+'</span></td>' +
    '<td>'+titleHtml+'</td>' +
    '<td>'+progHtml+'</td>' +
    '<td>'+actHtml+'</td>' +
    '</tr>';
}

// ── polling ──
async function refresh() {
  try {
    const r = await fetch('/api/state');
    const d = await r.json();
    const s = d.stats;

    document.getElementById('s-active').textContent = s.active;
    document.getElementById('s-queue').textContent  = s.queued + s.pending;
    document.getElementById('s-done').textContent   = s.done;
    document.getElementById('s-fail').textContent   = s.fail;
    document.getElementById('workers-val').textContent = s.workers;
    document.getElementById('shutdown-banner').style.display = s.shutting_down ? 'inline' : 'none';

    if (!folderReady) {
      document.getElementById('out-dir-input').value = s.out_dir;
      // sync format selector
      const sel = document.getElementById('fmt-select');
      for (let i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === s.format) { sel.selectedIndex = i; break; }
      }
      folderReady = true;
    }

    const tbody = document.getElementById('jobs-body');
    if (!d.jobs.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">Frónta je prázdná</td></tr>';
    } else {
      tbody.innerHTML = d.jobs.map(renderJob).join('');
    }
    document.getElementById('statusline').textContent =
      'Workers: '+s.workers+' | Aktualizováno: '+new Date().toLocaleTimeString('cs-CZ');
  } catch(e) {
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
                "jid":          j.jid,
                "url":          j.url,
                "status":       j.status,
                "title":        j.title or "",
                "downloaded":   j.downloaded,
                "total":        j.total,
                "speed":        j.speed,
                "eta":          j.eta,
                "progress_pct": round(pct, 1),
                "speed_str":    f"{j.speed / 1_048_576:.1f} MB/s" if j.speed else "",
                "eta_str":      fmt_hhmmss(j.eta) if j.eta else "",
                "elapsed_str":  fmt_hhmmss(elapsed),
                "total_str":    fmt_size(j.total),
                "retry_count":  j.retry_count,
                "max_retries":  daemon.max_retries,
                "priority":     j.priority,
                "error":        j.error[:200] if j.error else "",
                "final_path":   j.final_path or "",
                "enqueued_at":  time.strftime("%H:%M:%S", time.localtime(j.enqueued_at)) if j.enqueued_at else "",
                "added_at":     time.strftime("%H:%M:%S", time.localtime(j.added_at)) if j.added_at else "",
                "retry_after":  j.retry_after,
                "eta_bad":      j.eta_bad,
                "_sort": (
                    {"downloading": 0, "queued": 1, "pending": 2, "fail": 3, "done": 4}.get(j.status, 9),
                    -j.priority,
                    -j.jid,
                ),
            })
        jobs_list.sort(key=lambda x: x["_sort"])
        for j in jobs_list:
            del j["_sort"]

        stats = {
            "active":        sum(1 for j in daemon.jobs.values() if j.status == "downloading"),
            "queued":        sum(1 for j in daemon.jobs.values() if j.status == "queued"),
            "pending":       sum(1 for j in daemon.jobs.values() if j.status == "pending"),
            "done":          sum(1 for j in daemon.jobs.values() if j.status == "done"),
            "fail":          sum(1 for j in daemon.jobs.values() if j.status == "fail"),
            "workers":       _d()._max_workers,
            "format":        _d().cfg.get("format", "bv*+ba/b"),
            "out_dir":       str(daemon.out_dir),
            "shutting_down": daemon._shutting_down,
        }

    return {"stats": stats, "jobs": jobs_list}


class BulkReq(BaseModel):
    urls: list[str]

class PrioReq(BaseModel):
    jid: int

class WorkersReq(BaseModel):
    n: int

class FormatReq(BaseModel):
    fmt: str

class SetOutDirReq(BaseModel):
    path: str


@app.post("/api/add_bulk")
async def add_bulk(req: BulkReq):
    return daemon.add_bulk(req.urls)


@app.post("/api/priority")
async def bump_priority(req: PrioReq):
    return {"ok": True, "message": daemon.bump_priority(req.jid)}


@app.post("/api/cancel")
async def cancel_job(req: PrioReq):
    return {"ok": True, "message": daemon.cancel_job(req.jid)}


@app.post("/api/retry")
async def retry_job(req: PrioReq):
    return {"ok": True, "message": daemon.retry_job(req.jid)}


@app.post("/api/set_workers")
async def set_workers(req: WorkersReq):
    n = _d().set_workers(req.n)
    return {"ok": True, "workers": n}


@app.post("/api/set_format")
async def set_format(req: FormatReq):
    _d().set_format(req.fmt)
    return {"ok": True}


@app.post("/api/set_outdir")
async def set_outdir(req: SetOutDirReq):
    try:
        resolved = daemon.set_out_dir(req.path)
        return {"ok": True, "path": resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/browse_folder")
async def browse_folder():
    def _pick():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(parent=root, title="Vyber složku pro stahování")
        root.destroy()
        return path
    loop = asyncio.get_event_loop()
    path = await loop.run_in_executor(None, _pick)
    if not path:
        return {"ok": False, "cancelled": True}
    try:
        resolved = daemon.set_out_dir(path)
        return {"ok": True, "path": resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ──────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────

def main():
    global daemon

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port",   type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if getattr(sys, "frozen", False) and not Path(args.config).is_absolute():
        args.config = str(_exe_dir / args.config)

    cfg = load_config(args.config)
    config_dir = Path(args.config).resolve().parent
    state_path = (config_dir / cfg.get("state_file", "grabber_state.json")).resolve()

    daemon = GrabberDaemon(cfg, state_path)
    daemon._load_state()
    daemon.start()

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    print(f"Video Grabber -> http://localhost:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
