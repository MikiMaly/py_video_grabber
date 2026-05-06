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
<title>Ultimate Video Downloader</title>
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

  /* workers display */
  .workers-disp { display: flex; align-items: center; gap: 5px; border-left: 1px solid #30363d; padding-left: 16px; }
  .workers-disp .sep { color: #484f58; padding: 0 3px; }
  #workers-val, #frags-val { font-size: 17px; font-weight: 700; color: #c9d1d9; min-width: 18px; text-align: center; }

  /* ── tabs nav ── */
  .tabs-nav { flex-shrink: 0; background: #161b22; border-bottom: 2px solid #30363d; display: flex; }
  .tab-btn { background: none; border: none; border-bottom: 3px solid transparent; margin-bottom: -2px;
             padding: 8px 20px; color: #8b949e; cursor: pointer; font-size: 13px; font-weight: 500;
             transition: color .15s, border-color .15s; }
  .tab-btn:hover { color: #c9d1d9; }
  .tab-btn.active { color: #f0f6fc; border-bottom-color: #58a6ff; }

  /* ── tab containers ── */
  #tab-download { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
  #tab-settings { flex: 1; overflow-y: auto; }

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

  /* ── settings ── */
  .settings-scroll { max-width: 620px; padding: 20px; }
  .settings-section { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                       padding: 16px; margin-bottom: 16px; }
  .settings-section-title { font-size: 11px; font-weight: 600; color: #8b949e; text-transform: uppercase;
                              letter-spacing: 0.5px; margin-bottom: 12px; }
  .settings-row { display: flex; align-items: center; gap: 12px; padding: 7px 0;
                  border-bottom: 1px solid #21262d; }
  .settings-row:last-child { border-bottom: none; padding-bottom: 0; }
  .settings-row label { font-size: 13px; color: #c9d1d9; min-width: 175px; flex-shrink: 0; }
  .settings-hint { font-size: 11px; color: #484f58; }
  .settings-input { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                    padding: 6px 10px; color: #c9d1d9; font-size: 13px; outline: none; }
  .settings-input:focus { border-color: #58a6ff; }
  .settings-input-num { width: 90px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                         padding: 6px 10px; color: #c9d1d9; font-size: 13px; outline: none; text-align: right; }
  .settings-input-num:focus { border-color: #58a6ff; }
  .settings-select { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
                     padding: 6px 8px; color: #c9d1d9; font-size: 13px; outline: none; cursor: pointer; }
  .settings-select:focus { border-color: #58a6ff; }
  .settings-actions { display: flex; align-items: center; gap: 16px; }
  #settings-toast { font-size: 13px; }

  /* ── version badge ── */
  .version-badge { font-size: 11px; color: #484f58; font-weight: 400; margin-left: 10px; }

  /* ── audio checkbox ── */
  .audio-chk-label { display: flex; align-items: center; gap: 5px; font-size: 12px;
                     color: #8b949e; cursor: pointer; white-space: nowrap; user-select: none;
                     border-right: 1px solid #30363d; padding-right: 16px; }
  .audio-chk-label input { accent-color: #3fb950; cursor: pointer; width: 14px; height: 14px; }
  .audio-chk-label.active { color: #3fb950; }

  /* ── audio badge in queue ── */
  .audio-badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 10px;
                 font-weight: 700; background: #1a3d2b; color: #3fb950; margin-left: 6px;
                 vertical-align: middle; letter-spacing: 0.3px; }

  /* ── statusline ── */
  .statusline { flex-shrink: 0; padding: 3px 20px; font-size: 11px; color: #484f58;
                background: #161b22; border-top: 1px solid #30363d; }
</style>
</head>
<body>

<header>
  <h1>&#9660; Ultimate Video Downloader <span class="version-badge">v6.9 &middot; autospeed + audio update</span></h1>
  <span id="shutdown-banner">&#9888; Shutting down&hellip;</span>
  <label class="audio-chk-label" id="audio-chk-label" title="Sta&#382;en&#237; jen zvuku (MP3 / M4A)">
    <input type="checkbox" id="audio-only-chk" onchange="toggleAudioOnly()"> Jen audio
  </label>
  <div class="stat s-active"><span class="stat-val" id="s-active">0</span><span class="stat-lbl">active</span></div>
  <div class="stat s-queue" ><span class="stat-val" id="s-queue" >0</span><span class="stat-lbl">queue</span></div>
  <div class="stat s-done"  ><span class="stat-val" id="s-done"  >0</span><span class="stat-lbl">done</span></div>
  <div class="stat s-fail"  ><span class="stat-val" id="s-fail"  >0</span><span class="stat-lbl">fail</span></div>
  <div class="workers-disp">
    <span id="workers-val">?</span><span class="stat-lbl">workers</span>
    <span class="sep">|</span>
    <span id="frags-val">?</span><span id="adapt-badge" style="display:none;font-size:10px;color:#3fb950;padding-left:3px">auto</span><span class="stat-lbl">frags</span>
  </div>
</header>

<nav class="tabs-nav">
  <button class="tab-btn active" data-tab="download" onclick="switchTab('download')">&#9654; Stahov&#225;n&#237;</button>
  <button class="tab-btn" data-tab="settings" onclick="switchTab('settings')">&#9881; Nastaven&#237;</button>
</nav>

<!-- Tab: Stahování -->
<div id="tab-download">
  <div class="staging">
    <div class="stage-input-row">
      <input type="text" id="url-input"
             placeholder="URL nebo domena.com/video &mdash; Enter nebo klikni P&#345;idat&hellip;"
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
          <option value="ba/b">Jen audio (MP3)</option>
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
</div>

<!-- Tab: Nastavení -->
<div id="tab-settings" style="display:none">
  <div class="settings-scroll">

    <div class="settings-actions" style="margin-bottom:16px">
      <button class="btn" onclick="saveSettings()">Ulo&#382;it nastaven&#237;</button>
      <span id="settings-toast"></span>
    </div>

    <div class="settings-section">
      <div class="settings-section-title">Stahov&#225;n&#237;</div>
      <div class="settings-row">
        <label>Slo&#382;ka</label>
        <input type="text" id="cfg-download-dir" class="settings-input" placeholder="./downloads">
        <button class="btn-sm" onclick="cfgBrowseFolder()">&#128193;</button>
      </div>
      <div class="settings-row">
        <label>Workers</label>
        <input type="number" id="cfg-workers" class="settings-input-num" min="1" max="16">
        <span class="settings-hint">1&ndash;16 paraleln&#237;ch stahov&#225;n&#237;</span>
      </div>
      <div class="settings-row">
        <label>Concurrent fragments</label>
        <input type="number" id="cfg-concurrent-fragments" class="settings-input-num" min="1" max="32">
        <span class="settings-hint">fragmenty jednoho videa paraleln&#283;</span>
      </div>
      <div class="settings-row">
        <label>Auto-adapt fragmenty</label>
        <input type="checkbox" id="cfg-adapt-frags" onchange="toggleAdaptBounds()" style="width:18px;height:18px;cursor:pointer;accent-color:#58a6ff">
        <span class="settings-hint">automaticky p&#345;izp&#367;sobovat po&#269;et fragment&#367; podle rychlosti</span>
      </div>
      <div class="settings-row" id="adapt-bounds-row">
        <label>Rozsah adapt. (min&nbsp;/&nbsp;max)</label>
        <input type="number" id="cfg-adapt-min" class="settings-input-num" min="1" max="32" style="width:70px">
        <span style="color:#484f58;padding:0 6px">&#8211;</span>
        <input type="number" id="cfg-adapt-max" class="settings-input-num" min="1" max="32" style="width:70px">
        <span class="settings-hint">rozsah auto-adapt</span>
      </div>
    </div>

    <div class="settings-section">
      <div class="settings-section-title">Form&#225;t &amp; Kvalita</div>
      <div class="settings-row">
        <label>Form&#225;t</label>
        <select id="cfg-format" class="settings-select">
          <option value="bv*+ba/b">Nejlep&#353;&#237; kvalita</option>
          <option value="bv[height<=1080]+ba/b">Max 1080p</option>
          <option value="bv[height<=720]+ba/b">Max 720p</option>
          <option value="bv[height<=480]+ba/b">Max 480p</option>
          <option value="worst/w">Nejmen&#353;&#237; soubor</option>
          <option value="ba/b">Jen audio (MP3)</option>
        </select>
      </div>
    </div>

    <div class="settings-section">
      <div class="settings-section-title">Retry &amp; Timeouty</div>
      <div class="settings-row">
        <label>Timeout (s)</label>
        <input type="number" id="cfg-timeout" class="settings-input-num" min="5">
      </div>
      <div class="settings-row">
        <label>Retries yt-dlp</label>
        <input type="number" id="cfg-retries" class="settings-input-num" min="0">
      </div>
      <div class="settings-row">
        <label>Fragment retries</label>
        <input type="number" id="cfg-fragment-retries" class="settings-input-num" min="0">
      </div>
      <div class="settings-row">
        <label>Max retries (app)</label>
        <input type="number" id="cfg-max-retries" class="settings-input-num" min="0">
        <span class="settings-hint">po kter&#253;ch job selže natr&#253;no</span>
      </div>
      <div class="settings-row">
        <label>Retry base delay (s)</label>
        <input type="number" id="cfg-retry-delay" class="settings-input-num" min="1">
        <span class="settings-hint">exponenci&#225;ln&#237; backoff</span>
      </div>
    </div>

    <div class="settings-section">
      <div class="settings-section-title">Syst&#233;m</div>
      <div class="settings-row">
        <label>User-Agent</label>
        <input type="text" id="cfg-user-agent" class="settings-input">
      </div>
      <div class="settings-row">
        <label>FFmpeg cesta</label>
        <input type="text" id="cfg-ffmpeg-path" class="settings-input" placeholder="/opt/homebrew/bin/ffmpeg">
      </div>
    </div>

  </div>
</div>

<div class="statusline" id="statusline">P&#345;ipojuji&hellip;</div>

<script>
// ── URL normalization ──
function normalizeUrl(raw) {
  raw = raw.trim();
  if (!raw) return null;
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.includes('.') && !raw.startsWith(' ')) return 'https://' + raw;
  return null;
}

// ── tabs ──
function switchTab(tab) {
  document.getElementById('tab-download').style.display = tab === 'download' ? 'flex' : 'none';
  document.getElementById('tab-settings').style.display = tab === 'settings' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  if (tab === 'settings' && !settingsLoaded) loadSettings();
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
      body: JSON.stringify({urls: stagedUrls, audio_only: document.getElementById('audio-only-chk').checked})
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

let _prevVideoFormat = 'bv*+ba/b';

function syncAudioCheckbox(fmt) {
  const chk = document.getElementById('audio-only-chk');
  const lbl = document.getElementById('audio-chk-label');
  const isAudio = fmt === 'ba/b';
  chk.checked = isAudio;
  lbl.classList.toggle('active', isAudio);
}

function toggleAudioOnly() {
  const chk = document.getElementById('audio-only-chk');
  const sel = document.getElementById('fmt-select');
  if (chk.checked) {
    _prevVideoFormat = sel.value !== 'ba/b' ? sel.value : _prevVideoFormat;
    changeFormat('ba/b');
  } else {
    changeFormat(_prevVideoFormat);
  }
}

async function changeFormat(fmt) {
  const sel = document.getElementById('fmt-select');
  for (let i = 0; i < sel.options.length; i++) {
    if (sel.options[i].value === fmt) { sel.selectedIndex = i; break; }
  }
  syncAudioCheckbox(fmt);
  await fetch('/api/set_format', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fmt})
  });
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
  const labels = {downloading:'Stahuje', queued:'Ve frontě', pending:'Čeká', done:'Hotovo', fail:'Chyba'};
  const audioBadge = j.audio_only ? '<span class="audio-badge">MP3</span>' : '';
  const titleHtml = j.title
    ? '<div class="t-title">'+esc(j.title)+audioBadge+'</div><div class="t-url">'+esc(j.url)+'</div>'
    : '<div class="t-url" style="color:#8b949e">'+esc(j.url)+audioBadge+'</div>';

  let progHtml = '', actHtml = '';

  if (j.status === 'downloading') {
    const pct = j.progress_pct || 0;
    progHtml =
      '<div class="bar-bg"><div class="bar-fill" style="width:'+pct+'%"></div></div>' +
      '<div class="prog-row">' +
        '<span class="pct">'+pct.toFixed(1)+'%</span>' +
        '<span>'+fmtSize(j.downloaded)+' / '+j.total_str+'</span>' +
        '<span class="spd">'+j.speed_str+'</span>' +
        '<span class="elap">čas stahování '+j.elapsed_str+'</span>' +
        (j.eta_str ? '<span class="eta'+(j.eta_bad?' bad':'')+'">čas do stažení '+j.eta_str+'</span>' : '') +
      '</div>';

  } else if (j.status === 'queued') {
    progHtml = '<span class="dim">Ve frontě od '+j.enqueued_at+'</span>';
    actHtml  =
      '<div class="act-btns">' +
        '<button class="btn-prio"   onclick="bumpPriority('+j.jid+')">↑ Prio</button>' +
        '<button class="btn-cancel" onclick="cancelJob('+j.jid+')">✕</button>' +
      '</div>';

  } else if (j.status === 'pending') {
    const now = Date.now() / 1000;
    let badge = '';
    if (j.retry_count > 0 && j.retry_after > now) {
      badge = '<span class="retry-tag">· retry '+j.retry_count+'/'+j.max_retries+' za '+Math.ceil(j.retry_after-now)+'s</span>';
    } else if (j.retry_count > 0) {
      badge = '<span class="retry-tag">· retry '+j.retry_count+'/'+j.max_retries+'</span>';
    } else if (j.priority > 0) {
      badge = '<span class="prio-tag">· prio+'+j.priority+'</span>';
    }
    progHtml = '<span class="dim">Přidáno '+j.added_at+'</span>'+badge;
    actHtml  =
      '<div class="act-btns">' +
        '<button class="btn-prio"   onclick="bumpPriority('+j.jid+')">↑ Prio</button>' +
        '<button class="btn-cancel" onclick="cancelJob('+j.jid+')">✕</button>' +
      '</div>';

  } else if (j.status === 'done') {
    const fname = j.final_path ? j.final_path.replace(/\\/g,'/').split('/').pop() : '?';
    progHtml =
      '<div class="path-txt" title="'+esc(j.final_path)+'">'+esc(fname)+'</div>' +
      '<div class="prog-row"><span>'+j.total_str+'</span><span class="dim">za '+j.elapsed_str+'</span></div>';

  } else if (j.status === 'fail') {
    progHtml = '<div class="err-txt" title="'+esc(j.error)+'">'+esc(j.error||'neznámá chyba')+'</div>';
    actHtml  = '<button class="btn-retry" onclick="retryJob('+j.jid+')">↺ Retry</button>';
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
    document.getElementById('frags-val').textContent   = s.concurrent_fragments;
    document.getElementById('adapt-badge').style.display = s.auto_adapt ? '' : 'none';
    document.getElementById('shutdown-banner').style.display = s.shutting_down ? 'inline' : 'none';

    if (!folderReady) {
      document.getElementById('out-dir-input').value = s.out_dir;
      const sel = document.getElementById('fmt-select');
      for (let i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === s.format) { sel.selectedIndex = i; break; }
      }
      syncAudioCheckbox(s.format);
      folderReady = true;
    }

    const tbody = document.getElementById('jobs-body');
    if (!d.jobs.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">Fronta je prázdná</td></tr>';
    } else {
      tbody.innerHTML = d.jobs.map(renderJob).join('');
    }
    document.getElementById('statusline').textContent =
      'Workers: '+s.workers+' · Frags: '+s.concurrent_fragments+(s.auto_adapt?' (auto)':'')+' | Aktualizováno: '+new Date().toLocaleTimeString('cs-CZ');
  } catch(e) {
    document.getElementById('statusline').textContent = 'Spojení ztraceno – opakuji…';
  }
}

refresh();
setInterval(refresh, 1000);

// ── settings ──
let settingsLoaded = false;

async function loadSettings() {
  try {
    const r = await fetch('/api/config');
    const d = await r.json();
    document.getElementById('cfg-download-dir').value          = d.download_dir;
    document.getElementById('cfg-workers').value               = d.max_workers;
    document.getElementById('cfg-concurrent-fragments').value  = d.concurrent_fragments;
    const sel = document.getElementById('cfg-format');
    for (let i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === d.format) { sel.selectedIndex = i; break; }
    }
    document.getElementById('cfg-timeout').value               = d.timeout_sec;
    document.getElementById('cfg-retries').value               = d.retries;
    document.getElementById('cfg-fragment-retries').value      = d.fragment_retries;
    document.getElementById('cfg-max-retries').value           = d.max_retries;
    document.getElementById('cfg-retry-delay').value           = d.retry_base_delay;
    document.getElementById('cfg-user-agent').value            = d.user_agent;
    document.getElementById('cfg-ffmpeg-path').value           = d.ffmpeg_path;
    document.getElementById('cfg-adapt-frags').checked         = d.adapt_frags;
    document.getElementById('cfg-adapt-min').value             = d.adapt_min_frags;
    document.getElementById('cfg-adapt-max').value             = d.adapt_max_frags;
    toggleAdaptBounds();
    settingsLoaded = true;
  } catch(e) {
    showSettingsToast('Chyba načítání nastavení', '#f85149');
  }
}

async function saveSettings() {
  const payload = {
    download_dir:         document.getElementById('cfg-download-dir').value.trim(),
    max_workers:          parseInt(document.getElementById('cfg-workers').value) || 1,
    concurrent_fragments: parseInt(document.getElementById('cfg-concurrent-fragments').value) || 1,
    format:               document.getElementById('cfg-format').value,
    timeout_sec:          parseInt(document.getElementById('cfg-timeout').value) || 60,
    retries:              parseInt(document.getElementById('cfg-retries').value) || 0,
    fragment_retries:     parseInt(document.getElementById('cfg-fragment-retries').value) || 0,
    max_retries:          parseInt(document.getElementById('cfg-max-retries').value) || 0,
    retry_base_delay:     parseFloat(document.getElementById('cfg-retry-delay').value) || 10,
    user_agent:           document.getElementById('cfg-user-agent').value.trim(),
    ffmpeg_path:          document.getElementById('cfg-ffmpeg-path').value.trim(),
    adapt_frags:          document.getElementById('cfg-adapt-frags').checked,
    adapt_min_frags:      parseInt(document.getElementById('cfg-adapt-min').value) || 1,
    adapt_max_frags:      parseInt(document.getElementById('cfg-adapt-max').value) || 16,
  };
  try {
    const r = await fetch('/api/set_config', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (d.ok) {
      showSettingsToast('Nastavení uloženo ✓', '#3fb950');
      settingsLoaded = false;
      if (payload.download_dir) document.getElementById('out-dir-input').value = payload.download_dir;
      const stageFmt = document.getElementById('fmt-select');
      for (let i = 0; i < stageFmt.options.length; i++) {
        if (stageFmt.options[i].value === payload.format) { stageFmt.selectedIndex = i; break; }
      }
      syncAudioCheckbox(payload.format);
    } else {
      showSettingsToast(d.error || 'Chyba', '#f85149');
    }
  } catch(e) {
    showSettingsToast('Chyba spojení', '#f85149');
  }
}

async function cfgBrowseFolder() {
  const r = await fetch('/api/browse_folder');
  const d = await r.json();
  if (d.ok) {
    document.getElementById('cfg-download-dir').value = d.path;
    document.getElementById('out-dir-input').value = d.path;
    showSettingsToast('Složka vybrána ✓', '#3fb950');
  } else if (!d.cancelled) {
    showSettingsToast(d.error || 'Chyba', '#f85149');
  }
}

function toggleAdaptBounds() {
  const on = document.getElementById('cfg-adapt-frags').checked;
  document.getElementById('adapt-bounds-row').style.opacity = on ? '1' : '0.4';
}

let settingsToastTimer = null;
function showSettingsToast(msg, color) {
  const t = document.getElementById('settings-toast');
  t.textContent = msg;
  t.style.color = color || '#f85149';
  if (settingsToastTimer) clearTimeout(settingsToastTimer);
  settingsToastTimer = setTimeout(() => { t.textContent = ''; }, 3000);
}
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
                "audio_only":   j.audio_only,
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
            "active":               sum(1 for j in daemon.jobs.values() if j.status == "downloading"),
            "queued":               sum(1 for j in daemon.jobs.values() if j.status == "queued"),
            "pending":              sum(1 for j in daemon.jobs.values() if j.status == "pending"),
            "done":                 sum(1 for j in daemon.jobs.values() if j.status == "done"),
            "fail":                 sum(1 for j in daemon.jobs.values() if j.status == "fail"),
            "workers":              _d()._max_workers,
            "concurrent_fragments": int(_d().cfg.get("concurrent_fragments", 3)),
            "auto_adapt":           _d()._auto_adapt,
            "format":               _d().cfg.get("format", "bv*+ba/b"),
            "out_dir":              str(daemon.out_dir),
            "shutting_down":        daemon._shutting_down,
        }

    return {"stats": stats, "jobs": jobs_list}


class BulkReq(BaseModel):
    urls: list[str]
    audio_only: bool = False

class PrioReq(BaseModel):
    jid: int

class FormatReq(BaseModel):
    fmt: str

class SetOutDirReq(BaseModel):
    path: str

class SetConfigReq(BaseModel):
    download_dir: str | None = None
    max_workers: int | None = None
    concurrent_fragments: int | None = None
    format: str | None = None
    timeout_sec: int | None = None
    retries: int | None = None
    fragment_retries: int | None = None
    max_retries: int | None = None
    retry_base_delay: float | None = None
    user_agent: str | None = None
    ffmpeg_path: str | None = None
    adapt_frags: bool | None = None
    adapt_min_frags: int | None = None
    adapt_max_frags: int | None = None


@app.post("/api/add_bulk")
async def add_bulk(req: BulkReq):
    return daemon.add_bulk(req.urls, audio_only=req.audio_only)


@app.post("/api/priority")
async def bump_priority(req: PrioReq):
    return {"ok": True, "message": daemon.bump_priority(req.jid)}


@app.post("/api/cancel")
async def cancel_job(req: PrioReq):
    return {"ok": True, "message": daemon.cancel_job(req.jid)}


@app.post("/api/retry")
async def retry_job(req: PrioReq):
    return {"ok": True, "message": daemon.retry_job(req.jid)}


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
    def _pick() -> str | None:
        if sys.platform == "darwin":
            import subprocess
            r = subprocess.run(
                ["osascript", "-e",
                 'POSIX path of (choose folder with prompt "Vyber složku pro stahování")'],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                return r.stdout.strip().rstrip("/")
            return None
        else:
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            path = filedialog.askdirectory(parent=root, title="Vyber složku pro stahování")
            root.destroy()
            return path or None

    loop = asyncio.get_event_loop()
    path = await loop.run_in_executor(None, _pick)
    if not path:
        return {"ok": False, "cancelled": True}
    try:
        resolved = daemon.set_out_dir(path)
        return {"ok": True, "path": resolved}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/config")
async def get_config():
    d = _d()
    cfg = d.cfg
    frag_ret = cfg.get("fragment_retries")
    return {
        "download_dir":         str(d.out_dir),
        "max_workers":          d._max_workers,
        "concurrent_fragments": int(cfg.get("concurrent_fragments", 3)),
        "format":               cfg.get("format", "bv*+ba/b"),
        "timeout_sec":          int(cfg.get("timeout_sec", 60)),
        "retries":              int(cfg.get("retries", 20)),
        "fragment_retries":     int(frag_ret) if frag_ret is not None else int(cfg.get("retries", 20)),
        "max_retries":          d.max_retries,
        "retry_base_delay":     d.retry_base_delay,
        "user_agent":           cfg.get("user_agent", ""),
        "ffmpeg_path":          cfg.get("ffmpeg_path", ""),
        "adapt_frags":          d._auto_adapt,
        "adapt_min_frags":      int(cfg.get("adapt_min_frags", 1)),
        "adapt_max_frags":      int(cfg.get("adapt_max_frags", 16)),
    }


@app.post("/api/set_config")
async def set_config(req: SetConfigReq):
    d = _d()
    try:
        if req.download_dir:
            d.set_out_dir(req.download_dir)
        if req.max_workers is not None:
            d.set_workers(req.max_workers)
        if req.format is not None:
            d.set_format(req.format)
        if req.adapt_frags is not None:
            d.set_adapt(req.adapt_frags)
        with d.lock:
            if req.concurrent_fragments is not None:
                d.cfg["concurrent_fragments"] = max(1, req.concurrent_fragments)
            if req.timeout_sec is not None:
                d.cfg["timeout_sec"] = max(5, req.timeout_sec)
            if req.retries is not None:
                d.cfg["retries"] = max(0, req.retries)
            if req.fragment_retries is not None:
                d.cfg["fragment_retries"] = max(0, req.fragment_retries)
            if req.max_retries is not None:
                d.max_retries = max(0, req.max_retries)
                d.cfg["max_retries"] = d.max_retries
            if req.retry_base_delay is not None:
                d.retry_base_delay = max(1.0, req.retry_base_delay)
                d.cfg["retry_base_delay"] = d.retry_base_delay
            if req.user_agent is not None:
                d.cfg["user_agent"] = req.user_agent
            if req.ffmpeg_path is not None:
                d.cfg["ffmpeg_path"] = req.ffmpeg_path
            if req.adapt_min_frags is not None:
                d.cfg["adapt_min_frags"] = max(1, req.adapt_min_frags)
            if req.adapt_max_frags is not None:
                d.cfg["adapt_max_frags"] = max(1, req.adapt_max_frags)
        return {"ok": True}
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

    print(f"Ultimate Video Downloader -> http://localhost:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
