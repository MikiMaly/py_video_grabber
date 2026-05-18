#!/usr/bin/env python3
import argparse
import asyncio
import os
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
    os.environ['PATH'] = str(_exe_dir) + os.pathsep + os.environ.get('PATH', '')
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
<link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABzUlEQVR4nGNkQAJi0kr/GegAXj29xwhjM6Jb7tR99yQtLd9XqmyO7AhGdMthCmgFkO0AOYKRnpZjcwQTvS0HAZBdsKhmIaRY0S2fgZGJmeHejj4GJY8ihv///jKI6rgz3NrQyPDh3kkGVb9ahl9f3jAwsbAxKLrmMfz//4/h44OzDJcXZjH8/vqOoGOYyPHBy/MbGUR13MBsES1nhpfnN4PZD/ZOZThYpcPw490TBlnbBKLMYiKo4j9azvz/n+Hl+U0MojouDDxSmgw/P71k+PH+CVz635+fDO/vHGfgElWkjgP+/vzKwCOhzsDCwcvAJarE8OfnF4YfH54z/Hj/jEHJrQAcGsiAkZmFgV/BmOH7m4fUccDLC1sY2AUkGWwbzjBwCskyvLqwFSz+4vxGBmENB4ZXF7fB1So4ZzM4tF5l4BJTZnh0aB5RDmAhpAAUxKcn+GGIPzuxAoxh4P6uiWBMKmBiGGDANNAOYKFEs1P3XTh7X6ny0AwBplEHMIxGwUiPAhZK8z+6GKnlARM5DsBlCTmFERM5DsBm2cgsCfdBfU2u7yl2AKWWU8UBlAIm9HY63Tsmr6B9NHo5AqNrxgAFA9o5RXcErQFy9xwAPPzHm2LbwvUAAAAASUVORK5CYII=">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0e1a; color: #e5e7eb; font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
         font-size: 14px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

  /* ── header ── */
  header { flex-shrink: 0; padding: 8px 20px; background: #131825; border-bottom: 1px solid rgba(255,255,255,0.1);
           display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  header h1 { font-size: 16px; color: #e5e7eb; font-weight: 600; margin-right: auto; }
  .stat { display: flex; flex-direction: column; align-items: center; min-width: 44px; }
  .stat-val { font-size: 17px; font-weight: 700; line-height: 1; }
  .stat-lbl { font-size: 10px; color: #94a3b8; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
  .s-active .stat-val { color: #3b82f6; }
  .s-queue  .stat-val { color: #f59e0b; }
  .s-done   .stat-val { color: #22c55e; }
  .s-fail   .stat-val { color: #ef4444; }
  #shutdown-banner { display: none; color: #ef4444; font-size: 12px; font-weight: 600; }

  /* workers display */
  .workers-disp { display: flex; align-items: center; gap: 5px; }
  .workers-disp .sep { color: #64748b; padding: 0 3px; }
  #workers-val, #frags-val { font-size: 15px; font-weight: 700; color: #e5e7eb; min-width: 18px; text-align: center; }

  /* ── tabs nav ── */
  .tabs-nav { flex-shrink: 0; background: #131825; border-bottom: 2px solid rgba(255,255,255,0.1);
              display: flex; align-items: center; }
  .tab-btn { background: none; border: none; border-bottom: 3px solid transparent; margin-bottom: -2px;
             padding: 8px 20px; color: #94a3b8; cursor: pointer; font-size: 13px; font-weight: 500;
             transition: color .15s, border-color .15s; }
  .tab-btn:hover { color: #e5e7eb; }
  .tab-btn.active { color: #e5e7eb; border-bottom-color: #22c55e; }
  .tab-btn.tab-icon { padding: 6px 16px; font-size: 18px; line-height: 1; }
  .tabs-nav-right { margin-left: auto; display: flex; align-items: center; gap: 14px; padding: 0 20px; }

  /* ── tab containers ── */
  #tab-download { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
  #tab-settings { flex: 1; overflow-y: auto; }

  /* ── staging ── */
  .staging { flex-shrink: 0; background: #131825; border-bottom: 2px solid rgba(255,255,255,0.1); }
  .stage-input-row { display: flex; gap: 10px; align-items: center; padding: 28px 20px; border-bottom: 1px solid #1a2332;
                     transition: background .15s; }
  .stage-input-row.drag-over { background: rgba(34,197,94,0.08); }
  .stage-input-row.drag-over input { border-color: #22c55e; box-shadow: 0 0 0 3px rgba(34,197,94,0.18); }
  .stage-input-row input { flex: 1; background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px;
                            padding: 22px 18px; color: #e5e7eb; font-size: 17px; outline: none;
                            transition: border-color .15s, box-shadow .15s; }
  .stage-input-row input:focus { border-color: #22c55e; box-shadow: 0 0 0 2px rgba(34,197,94,0.15); }
  .stage-input-row input::placeholder { color: #64748b; }
  .stage-list { max-height: 40vh; overflow-y: auto; }
  .stage-item { display: flex; align-items: center; gap: 8px; padding: 4px 20px; border-bottom: 1px solid #1a2332; }
  .stage-item:last-child { border-bottom: none; }
  .stage-url { flex: 1; font-size: 12px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .staged-empty { padding: 8px 20px; font-size: 12px; color: #64748b; }
  .stage-footer { display: flex; align-items: center; gap: 10px; padding: 8px 20px; flex-wrap: wrap; }
  .folder-row { display: flex; align-items: center; gap: 6px; margin-left: auto; }
  .folder-input { background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                  padding: 5px 10px; color: #e5e7eb; font-size: 12px; width: 260px; outline: none; transition: border-color .15s; }
  .folder-input:focus { border-color: #3b82f6; }
  .fmt-select { background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                padding: 5px 8px; color: #e5e7eb; font-size: 12px; outline: none; cursor: pointer; }
  .fmt-select:focus { border-color: #3b82f6; }

  /* ── buttons ── */
  .btn { background: #22c55e; color: #0a0e1a; border: none; border-radius: 8px; padding: 7px 16px;
         cursor: pointer; font-size: 14px; font-weight: 600; transition: background .15s; white-space: nowrap; }
  .btn:hover { background: #16a34a; }
  .btn:disabled { background: #1a2332; color: #64748b; cursor: default; }
  .btn-danger { background: #475569; }
  .btn-danger:hover { background: #94a3b8; }
  .btn-sm { background: #1a2332; border: 1px solid rgba(255,255,255,0.1); color: #e5e7eb; border-radius: 6px;
            padding: 5px 10px; cursor: pointer; font-size: 12px; transition: background .15s; white-space: nowrap; }
  .btn-sm:hover { background: rgba(255,255,255,0.1); }
  .btn-prio   { background: #3b82f6; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-prio:hover   { background: #60a5fa; }
  .btn-cancel { background: #475569; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-cancel:hover { background: #94a3b8; }
  .btn-retry  { background: #60a5fa; padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-retry:hover  { background: #3b82f6; }
  .btn-remove { background: none; border: none; color: #64748b; cursor: pointer; font-size: 14px; padding: 0 4px; }
  .btn-remove:hover { color: #ef4444; }
  #toast { font-size: 12px; min-width: 80px; }

  /* ── table ── */
  .table-wrap { flex: 1; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  colgroup .col-id  { width: 40px; }
  colgroup .col-st  { width: 100px; }
  colgroup .col-ttl { width: auto; }
  colgroup .col-prg { width: 270px; }
  colgroup .col-act { width: 130px; }
  thead th { padding: 6px 10px; text-align: left; font-size: 11px; font-weight: 600; color: #94a3b8;
             background: #131825; border-bottom: 1px solid rgba(255,255,255,0.1); position: sticky; top: 0; z-index: 1;
             text-transform: uppercase; letter-spacing: 0.5px; }
  tbody tr { border-bottom: 1px solid #1a2332; transition: background .1s; }
  tbody tr:hover { background: #131825; }
  td { padding: 6px 10px; vertical-align: middle; overflow: hidden; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .b-downloading { background: rgba(59,130,246,0.15); color: #3b82f6; }
  .b-queued      { background: rgba(245,158,11,0.15); color: #f59e0b; }
  .b-pending     { background: rgba(245,158,11,0.15); color: #f59e0b; }
  .b-done        { background: rgba(34,197,94,0.15); color: #22c55e; }
  .b-fail        { background: rgba(239,68,68,0.15); color: #ef4444; }
  .t-title { font-weight: 500; color: #e5e7eb; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-url   { font-size: 11px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
  .bar-bg  { background: #1a2332; border-radius: 4px; height: 5px; margin-bottom: 4px; }
  .bar-fill{ height: 5px; border-radius: 4px; background: #3b82f6; transition: width 0.6s linear; }
  .prog-row{ display: flex; gap: 8px; font-size: 12px; color: #94a3b8; flex-wrap: wrap; }
  .pct { color: #e5e7eb; font-weight: 600; }
  .spd { color: #22c55e; }
  .eta { color: #3b82f6; }
  .eta.bad { color: #ef4444; }
  .elap { color: #f59e0b; }
  .dim { color: #64748b; }
  .retry-tag { color: #f59e0b; font-size: 11px; }
  .prio-tag  { color: #3b82f6; font-size: 11px; }
  .path-txt  { font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .err-txt   { font-size: 11px; color: #ef4444; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .act-btns  { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
  .empty-row td { padding: 40px; text-align: center; color: #64748b; }

  /* ── settings ── */
  .settings-scroll { max-width: 620px; padding: 20px; }
  .settings-section { background: #131825; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
                       padding: 16px; margin-bottom: 16px; }
  .settings-section-title { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase;
                              letter-spacing: 0.5px; margin-bottom: 12px; }
  .settings-row { display: flex; align-items: center; gap: 12px; padding: 7px 0;
                  border-bottom: 1px solid #1a2332; }
  .settings-row:last-child { border-bottom: none; padding-bottom: 0; }
  .settings-row label { font-size: 13px; color: #e5e7eb; min-width: 175px; flex-shrink: 0; }
  .settings-hint { font-size: 11px; color: #64748b; }
  .settings-input { flex: 1; background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                    padding: 6px 10px; color: #e5e7eb; font-size: 13px; outline: none; }
  .settings-input:focus { border-color: #3b82f6; }
  .settings-input-num { width: 90px; background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                         padding: 6px 10px; color: #e5e7eb; font-size: 13px; outline: none; text-align: right; }
  .settings-input-num:focus { border-color: #3b82f6; }
  .settings-select { background: #0a0e1a; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                     padding: 6px 8px; color: #e5e7eb; font-size: 13px; outline: none; cursor: pointer; }
  .settings-select:focus { border-color: #3b82f6; }
  .settings-actions { display: flex; align-items: center; gap: 16px; }
  #settings-toast { font-size: 13px; }

  /* ── version badge ── */
  .version-badge { font-size: 11px; color: #64748b; font-weight: 400; margin-left: 10px; }

  /* ── download app button ── */
  .dl-app-btn { font-size: 12px; color: #3b82f6; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                padding: 4px 10px; text-decoration: none; white-space: nowrap; }
  .dl-app-btn:hover { background: #1a2332; border-color: #3b82f6; }

  /* ── audio checkbox ── */
  .audio-chk-label { display: flex; align-items: center; gap: 5px; font-size: 12px;
                     color: #94a3b8; cursor: pointer; white-space: nowrap; user-select: none;
                     border-right: 1px solid rgba(255,255,255,0.1); padding-right: 16px; }
  .audio-chk-label input { accent-color: #22c55e; cursor: pointer; width: 14px; height: 14px; }
  .audio-chk-label.active { color: #22c55e; }

  /* ── audio badge in queue ── */
  .audio-badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 10px;
                 font-weight: 700; background: rgba(34,197,94,0.15); color: #22c55e; margin-left: 6px;
                 vertical-align: middle; letter-spacing: 0.3px; }

  /* ── statusline ── */
  .statusline { flex-shrink: 0; padding: 3px 20px; font-size: 11px; color: #64748b;
                background: #131825; border-top: 1px solid rgba(255,255,255,0.1); }

  /* ════════════════════════════════════════════════════════════
     ── v8 design refresh ──
     Hero header, stat-cards, job-cards, animations, halos,
     floating toasts, empty states, hover lifts, lucide icons.
     ════════════════════════════════════════════════════════════ */

  /* hero header */
  header { padding: 16px 24px; gap: 20px; }
  .brand { display: flex; align-items: center; gap: 12px; margin-right: auto; }
  .brand .logo { width: 28px; height: 28px; }
  .brand h1 { font-size: 22px; font-weight: 700; margin: 0;
              background: linear-gradient(135deg, #22c55e 0%, #14b8a6 100%);
              -webkit-background-clip: text; background-clip: text; color: transparent;
              -webkit-text-fill-color: transparent; }
  .version-badge { font-size: 11px; color: #64748b; font-weight: 500;
                   padding: 2px 8px; background: rgba(255,255,255,0.04);
                   border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; }

  /* stat cards */
  .stat-cards { display: flex; gap: 10px; }
  .stat-card { position: relative; padding: 10px 16px 10px 14px; min-width: 82px;
               background: #1a2332; border: 1px solid rgba(255,255,255,0.06);
               border-radius: 12px; transition: transform .2s ease, border-color .2s, box-shadow .2s; }
  .stat-card:hover { transform: translateY(-2px); }
  .stat-card.s-active:hover { border-color: rgba(59,130,246,0.4); box-shadow: 0 6px 20px rgba(59,130,246,0.08); }
  .stat-card.s-queue:hover  { border-color: rgba(245,158,11,0.4); box-shadow: 0 6px 20px rgba(245,158,11,0.08); }
  .stat-card.s-done:hover   { border-color: rgba(34,197,94,0.4);  box-shadow: 0 6px 20px rgba(34,197,94,0.08); }
  .stat-card.s-fail:hover   { border-color: rgba(239,68,68,0.4);  box-shadow: 0 6px 20px rgba(239,68,68,0.08); }
  .stat-card .stat-icon { position: absolute; top: 9px; right: 10px; opacity: 0.5; }
  .stat-card .stat-num  { font-size: 22px; font-weight: 700; line-height: 1; }
  .stat-card .stat-cap  { font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
  .stat-card.s-active .stat-num { color: #3b82f6; }
  .stat-card.s-queue  .stat-num { color: #f59e0b; }
  .stat-card.s-done   .stat-num { color: #22c55e; }
  .stat-card.s-fail   .stat-num { color: #ef4444; }

  /* job cards */
  .job-list { padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
  .job-card { position: relative; padding: 14px 18px 14px 22px; background: #131825;
              border: 1px solid rgba(255,255,255,0.08); border-radius: 12px;
              transition: transform .2s, border-color .2s, box-shadow .2s;
              overflow: hidden; animation: card-in .25s ease-out; }
  .job-card:hover { transform: translateY(-1px); border-color: rgba(255,255,255,0.15); }
  .job-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
                      background: var(--accent, #94a3b8); }
  .job-card.j-downloading { --accent: #3b82f6; }
  .job-card.j-queued      { --accent: #f59e0b; }
  .job-card.j-pending     { --accent: #f59e0b; }
  .job-card.j-done        { --accent: #22c55e; }
  .job-card.j-fail        { --accent: #ef4444; }
  .job-card.j-downloading::after {
    content: ''; position: absolute; left: -20%; top: -20%; right: -20%; bottom: -20%;
    background: radial-gradient(ellipse at 30% 50%, rgba(59,130,246,0.08) 0%, transparent 60%);
    pointer-events: none; animation: pulse-halo 2.5s ease-in-out infinite; z-index: 0; }
  @keyframes pulse-halo { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
  @keyframes card-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  .job-card > * { position: relative; z-index: 1; }

  .job-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
  .job-status-pill { display: inline-flex; align-items: center; gap: 6px;
                     font-size: 11px; font-weight: 600; text-transform: uppercase;
                     letter-spacing: 0.4px; padding: 3px 10px; border-radius: 20px;
                     background: rgba(255,255,255,0.04); color: var(--accent); }
  .job-status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
                          box-shadow: 0 0 6px var(--accent); }
  .job-card.j-downloading .job-status-pill .dot { animation: blink 1.2s ease-in-out infinite; }
  @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  .job-id { color: #64748b; font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .job-actions { margin-left: auto; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .job-title { font-size: 14px; font-weight: 500; color: #e5e7eb;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
  .job-url { font-size: 11px; color: #64748b;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .job-progress { margin-top: 10px; }
  .job-progress .bar-bg { background: rgba(255,255,255,0.05); height: 6px; border-radius: 4px; overflow: hidden; }
  .job-progress .bar-fill { height: 6px; border-radius: 4px;
                            background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 60%, white));
                            transition: width 0.6s linear;
                            box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 50%, transparent); }
  .job-meta-row { display: flex; gap: 14px; font-size: 12px; color: #94a3b8; margin-top: 6px; flex-wrap: wrap;
                  font-variant-numeric: tabular-nums; }
  .job-meta-row .pct { color: #e5e7eb; font-weight: 600; }
  .job-meta-row .spd { color: #22c55e; }
  .job-meta-row .eta { color: #3b82f6; }
  .job-meta-row .eta.bad { color: #ef4444; }
  .job-meta-row .elap { color: #f59e0b; }
  .job-meta-row .dim { color: #64748b; }
  .job-meta-row .retry-tag { color: #f59e0b; }
  .job-meta-row .prio-tag  { color: #3b82f6; }

  /* lucide icon helper */
  .icon { display: inline-block; vertical-align: middle; flex-shrink: 0; }

  /* hover lifts on interactive elements */
  .btn:hover, .dl-app-btn:hover { transform: translateY(-1px); }
  .stat-card { will-change: transform; }

  /* floating toasts */
  #toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 1000;
                     display: flex; flex-direction: column; gap: 8px; max-width: 360px; }
  .toast { padding: 11px 16px; background: #131825;
           border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #22c55e;
           border-radius: 10px; font-size: 13px; color: #e5e7eb;
           animation: toast-in .35s cubic-bezier(0.16, 1, 0.3, 1);
           box-shadow: 0 10px 30px rgba(0,0,0,0.4); display: flex; align-items: center; gap: 8px; }
  .toast.t-error { border-left-color: #ef4444; }
  .toast.t-info  { border-left-color: #3b82f6; }
  .toast.fade-out { animation: toast-out .25s ease-in forwards; }
  @keyframes toast-in  { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
  @keyframes toast-out { to { opacity: 0; transform: translateX(40px); } }

  /* staged item slide-in */
  .stage-item { animation: stage-in .2s ease-out; }
  @keyframes stage-in { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }

  /* empty states */
  .empty-state { padding: 70px 20px 60px; text-align: center; color: #64748b;
                 display: flex; flex-direction: column; align-items: center; }
  .empty-state .empty-icon { opacity: 0.25; margin-bottom: 16px; color: #94a3b8; }
  .empty-state .empty-title { font-size: 14px; color: #94a3b8; margin-bottom: 4px; font-weight: 500; }
  .empty-state .empty-hint  { font-size: 12px; color: #64748b; }

  /* tab content fade */
  #tab-download, #tab-settings { animation: fade-in .25s ease-out; }
  @keyframes fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

  /* hide old #toast/#settings-toast inline spans (kept in markup for backward compat — moved to floating) */
  #toast, #settings-toast { display: none; }
</style>
</head>
<body>

<header>
  <div class="brand">
    <img class="logo" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAYAAAByDd+UAAABv0lEQVR4nO2WzStEURjGn3NmzCRSPhqhIUbMrFghGXE2s7GlbC1kOanZ2FpQbP0LbJGVj1uUhZRSZqRpsKCYuUJq0P3S3MztuI0xlzuT4lmdznvO87vve99TLwEnT1ObhiIoeX1OsmtiBrGFxIGdMCHi6+XBTjOIP2CHmMmX8tnZDTN7Zlg0+xW5YBX17XBV1gKEoNrXh5qOoBGr6RjQ43UBpscI0a1yKuOdzdQoaS419o7jPr6Pu7Nd+EfnkBYvIT8/QlUkeIMTSKcu4HCVQ1MkNPSMIbYyja+UF/hBmobbozV4ukegSi+4OVpFlbcLYnQb4qmA/pk9vRLQ8jc6zctQJNAyN6jTrWeVim6iLjCM2s5BiCdbxjlCHQXBvsxQjO3APzaP5qFJJI83oLym8XQVhabKUKRn/UxrKIwWNoXLnSUUorzAh4tDHCyGQIgDqvyq70WXw0Y8vj5bEMTSP9QUGRpk2CVqm9NvBTq/c4ktJIy1EPFZuktRYtF/4N/qUsZ1p3mv0G6lVoCfmVp5GtQKMJd5Sd6h8A6xCvtR03wHZgD5maMYYtzMRPkhtRhQxnlmWCUfhI3szGA7xVfxDT+Ds/ZCpq+GAAAAAElFTkSuQmCC" alt="">
    <h1>Ultimate Video Downloader</h1>
    <span class="version-badge">v8.0 &middot; design refresh</span>
  </div>
  <span id="shutdown-banner">&#9888; Shutting down&hellip;</span>
  <div class="stat-cards">
    <div class="stat-card s-active" title="Aktuálně stahuje">
      <svg class="icon stat-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      <div class="stat-num" id="s-active">0</div>
      <div class="stat-cap">stahuje</div>
    </div>
    <div class="stat-card s-queue" title="Ve frontě">
      <svg class="icon stat-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      <div class="stat-num" id="s-queue">0</div>
      <div class="stat-cap">ve frontě</div>
    </div>
    <div class="stat-card s-done" title="Dokončeno">
      <svg class="icon stat-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      <div class="stat-num" id="s-done">0</div>
      <div class="stat-cap">hotovo</div>
    </div>
    <div class="stat-card s-fail" title="Selhalo">
      <svg class="icon stat-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
      <div class="stat-num" id="s-fail">0</div>
      <div class="stat-cap">selhalo</div>
    </div>
  </div>
</header>

<nav class="tabs-nav">
  <button class="tab-btn tab-icon active" data-tab="download" onclick="switchTab('download')" title="Stahov&#225;n&#237;">
    <svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
  </button>
  <button class="tab-btn tab-icon" data-tab="settings" onclick="switchTab('settings')" title="Nastaven&#237;">
    <svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
  </button>
  <div class="tabs-nav-right">
    <div class="workers-disp">
      <span id="workers-val">?</span><span class="stat-lbl">sloty</span>
      <span class="sep">|</span>
      <span id="frags-val">?</span><span id="adapt-badge" style="display:none;font-size:10px;color:#22c55e;padding-left:3px">auto</span><span class="stat-lbl">seg.</span>
    </div>
    <a class="dl-app-btn" href="https://github.com/MikiMaly/py_video_grabber/releases/latest" target="_blank" title="St&aacute;hnout aplikaci (EXE/DMG)">
      <svg class="icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:5px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>St&aacute;hnout aplikaci
    </a>
  </div>
</nav>

<!-- Tab: Stahování -->
<div id="tab-download">
  <div class="staging">
    <div class="stage-input-row">
      <input type="text" id="url-input"
             placeholder="URL nebo domena.com/video &mdash; Enter, P&#345;idat, nebo p&#345;eta&#382;en&#237;m&hellip;"
             autocomplete="off" spellcheck="false">
      <button class="btn" onclick="addToStaging()">+ P&#345;idat</button>
      <span id="toast"></span>
    </div>
    <div class="stage-list" id="stage-list">
      <div class="staged-empty">Žádné URL k odeslání &mdash; vlož odkaz nahoře nebo přetáhni</div>
    </div>
    <div class="stage-footer">
      <button class="btn" id="btn-dl-all" onclick="downloadAll()" disabled>&#9654; Sta&#382;en&#237; (0)</button>
      <label class="audio-chk-label" id="audio-chk-label" title="Sta&#382;en&#237; jen zvuku (MP3 / M4A)">
        <input type="checkbox" id="audio-only-chk" onchange="toggleAudioOnly()"> Jen audio
      </label>
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
        <span style="color:#94a3b8;font-size:12px">Slo&#382;ka:</span>
        <input type="text" id="out-dir-input" class="folder-input" placeholder="&hellip;">
        <button class="btn-sm" onclick="browseFolder()" title="Vybrat slo&#382;ku">&#128193;</button>
        <button class="btn-sm" onclick="changeOutDir()">Zm&#283;nit</button>
      </div>
    </div>
  </div>

  <div class="table-wrap">
    <div id="jobs-list" class="job-list">
      <div class="empty-state">
        <svg class="empty-icon" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
        <div class="empty-title">Žádné joby zatím</div>
        <div class="empty-hint">Přidej URL nahoře a klikni &bdquo;Stažení&ldquo;</div>
      </div>
    </div>
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
        <label>Stahování najednou</label>
        <input type="number" id="cfg-workers" class="settings-input-num" min="1" max="16">
        <span class="settings-hint">1&ndash;16 paraleln&#237;ch stahov&#225;n&#237;</span>
      </div>
      <div class="settings-row">
        <label>Segmenty najednou</label>
        <input type="number" id="cfg-concurrent-fragments" class="settings-input-num" min="1" max="32">
        <span class="settings-hint">&#269;&#225;sti jednoho videa sta&#382;en&#233; paraleln&#283;</span>
      </div>
      <div class="settings-row">
        <label>Auto-adapt segmentů</label>
        <input type="checkbox" id="cfg-adapt-frags" onchange="toggleAdaptBounds()" style="width:18px;height:18px;cursor:pointer;accent-color:#22c55e">
        <span class="settings-hint">automaticky p&#345;izp&#367;sobovat po&#269;et fragment&#367; podle rychlosti</span>
      </div>
      <div class="settings-row" id="adapt-bounds-row">
        <label>Rozsah adapt. (min&nbsp;/&nbsp;max)</label>
        <input type="number" id="cfg-adapt-min" class="settings-input-num" min="1" max="32" style="width:70px">
        <span style="color:#64748b;padding:0 6px">&#8211;</span>
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

// ── drag-and-drop URL ──
const dropZone = document.querySelector('.stage-input-row');
['dragenter','dragover'].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); dropZone.classList.add('drag-over'); })
);
['dragleave','drop'].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); if (ev === 'dragleave' && e.target !== dropZone) return; dropZone.classList.remove('drag-over'); })
);
dropZone.addEventListener('drop', e => {
  const dt = e.dataTransfer;
  if (!dt) return;
  // try URL list first (browser address-bar drag), then plain text
  const raw = dt.getData('text/uri-list') || dt.getData('text/plain') || '';
  if (!raw) return;
  const tokens = raw.split(/[\s,;]+/);
  let added = 0;
  tokens.forEach(t => { const u = normalizeUrl(t); if (u && pushStaged(u)) added++; });
  renderStaging();
  if (added) showToast(added + ' URL přidáno ✓', '#22c55e');
  else showToast('Žádné platné URL');
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
  if (added) showToast(added + ' URL přidáno ✓', '#22c55e');
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
    showToast('Zahájeno: ' + d.added + '/' + d.total + ' ✓', '#22c55e');
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
    showToast('Složka změněna ✓', '#22c55e');
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
  if (d.ok) { inp.value = d.path; showToast('Složka změněna ✓', '#22c55e'); }
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
function showToast(msg, color) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  let cls = 'toast';
  if (color === '#ef4444' || !color) cls += ' t-error';
  else if (color === '#3b82f6') cls += ' t-info';
  // default = green (success)
  t.className = cls;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => {
    t.classList.add('fade-out');
    setTimeout(() => t.remove(), 280);
  }, 2700);
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

// ── render jobs (v8: cards) ──
const ICON_SVG = {
  prio:   '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>',
  cancel: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  retry:  '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>'
};

function iconBtn(type, jid) {
  const cls   = { prio: 'btn-prio',   cancel: 'btn-cancel', retry: 'btn-retry' };
  const fn    = { prio: 'bumpPriority', cancel: 'cancelJob', retry: 'retryJob' };
  const label = { prio: 'Prio',       cancel: 'Zrušit',     retry: 'Retry' };
  return '<button class="'+cls[type]+'" onclick="'+fn[type]+'('+jid+')" title="'+label[type]+'">' +
         ICON_SVG[type] + ' ' + label[type] + '</button>';
}

function renderJob(j) {
  const labels = {downloading:'Stahuje', queued:'Ve frontě', pending:'Čeká', done:'Hotovo', fail:'Chyba'};
  const audioBadge = j.audio_only ? '<span class="audio-badge">MP3</span>' : '';
  const title = j.title || '';
  const titleHtml = title
    ? '<div class="job-title">'+esc(title)+audioBadge+'</div><div class="job-url">'+esc(j.url)+'</div>'
    : '<div class="job-title" style="color:#94a3b8">'+esc(j.url)+audioBadge+'</div>';

  let progHtml = '', actHtml = '';

  if (j.status === 'downloading') {
    const pct = j.progress_pct || 0;
    progHtml =
      '<div class="job-progress">' +
        '<div class="bar-bg"><div class="bar-fill" style="width:'+pct+'%"></div></div>' +
        '<div class="job-meta-row">' +
          '<span class="pct">'+pct.toFixed(1)+'%</span>' +
          '<span>'+fmtSize(j.downloaded)+' / '+j.total_str+'</span>' +
          '<span class="spd">'+j.speed_str+'</span>' +
          '<span class="elap">⏱ '+j.elapsed_str+'</span>' +
          (j.eta_str ? '<span class="eta'+(j.eta_bad?' bad':'')+'">ETA '+j.eta_str+'</span>' : '') +
        '</div>' +
      '</div>';

  } else if (j.status === 'queued') {
    progHtml = '<div class="job-meta-row"><span class="dim">Ve frontě od '+j.enqueued_at+'</span></div>';
    actHtml  = iconBtn('prio', j.jid) + iconBtn('cancel', j.jid);

  } else if (j.status === 'pending') {
    const now = Date.now() / 1000;
    let badge = '';
    if (j.retry_count > 0 && j.retry_after > now) {
      badge = '<span class="retry-tag">retry '+j.retry_count+'/'+j.max_retries+' za '+Math.ceil(j.retry_after-now)+'s</span>';
    } else if (j.retry_count > 0) {
      badge = '<span class="retry-tag">retry '+j.retry_count+'/'+j.max_retries+'</span>';
    } else if (j.priority > 0) {
      badge = '<span class="prio-tag">prio +'+j.priority+'</span>';
    }
    progHtml = '<div class="job-meta-row"><span class="dim">Přidáno '+j.added_at+'</span>' +
               (badge ? '<span class="dim">·</span>'+badge : '') + '</div>';
    actHtml  = iconBtn('prio', j.jid) + iconBtn('cancel', j.jid);

  } else if (j.status === 'done') {
    const fname = j.final_path ? j.final_path.replace(/\\/g,'/').split('/').pop() : '?';
    progHtml =
      '<div class="job-meta-row">' +
        '<span title="'+esc(j.final_path)+'" style="color:#94a3b8">'+esc(fname)+'</span>' +
        '<span>'+j.total_str+'</span>' +
        '<span class="dim">za '+j.elapsed_str+'</span>' +
      '</div>';

  } else if (j.status === 'fail') {
    progHtml = '<div class="job-meta-row" style="color:#ef4444" title="'+esc(j.error)+'">' +
               esc(j.error||'neznámá chyba') + '</div>';
    actHtml  = iconBtn('retry', j.jid);
  }

  return '<div class="job-card j-'+j.status+'">' +
    '<div class="job-head">' +
      '<span class="job-status-pill"><span class="dot"></span>'+(labels[j.status]||j.status)+'</span>' +
      '<span class="job-id">#'+j.jid+'</span>' +
      '<div class="job-actions">'+actHtml+'</div>' +
    '</div>' +
    titleHtml +
    progHtml +
    '</div>';
}

const JOBS_EMPTY_HTML =
  '<div class="empty-state">' +
    '<svg class="empty-icon" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>' +
    '<div class="empty-title">Žádné joby zatím</div>' +
    '<div class="empty-hint">Přidej URL nahoře a klikni „Stažení"</div>' +
  '</div>';

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

    // tab title: show download status when active
    const qtot = s.queued + s.pending;
    document.title = (s.active > 0 || qtot > 0)
      ? '(' + s.active + '↓ ' + qtot + '⏳) Ultimate Video Downloader'
      : 'Ultimate Video Downloader';
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

    const jobsList = document.getElementById('jobs-list');
    if (!d.jobs.length) {
      jobsList.innerHTML = JOBS_EMPTY_HTML;
    } else {
      jobsList.innerHTML = d.jobs.map(renderJob).join('');
    }
    document.getElementById('statusline').textContent =
      s.workers+' slot'+(s.workers===1?'':'y')+' · '+s.concurrent_fragments+' seg.'+(s.auto_adapt?' (auto)':'')+' | Aktualizováno: '+new Date().toLocaleTimeString('cs-CZ');
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
    showSettingsToast('Chyba načítání nastavení', '#ef4444');
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
      showSettingsToast('Nastavení uloženo ✓', '#22c55e');
      settingsLoaded = false;
      if (payload.download_dir) document.getElementById('out-dir-input').value = payload.download_dir;
      const stageFmt = document.getElementById('fmt-select');
      for (let i = 0; i < stageFmt.options.length; i++) {
        if (stageFmt.options[i].value === payload.format) { stageFmt.selectedIndex = i; break; }
      }
      syncAudioCheckbox(payload.format);
    } else {
      showSettingsToast(d.error || 'Chyba', '#ef4444');
    }
  } catch(e) {
    showSettingsToast('Chyba spojení', '#ef4444');
  }
}

async function cfgBrowseFolder() {
  const r = await fetch('/api/browse_folder');
  const d = await r.json();
  if (d.ok) {
    document.getElementById('cfg-download-dir').value = d.path;
    document.getElementById('out-dir-input').value = d.path;
    showSettingsToast('Složka vybrána ✓', '#22c55e');
  } else if (!d.cancelled) {
    showSettingsToast(d.error || 'Chyba', '#ef4444');
  }
}

function toggleAdaptBounds() {
  const on = document.getElementById('cfg-adapt-frags').checked;
  document.getElementById('adapt-bounds-row').style.opacity = on ? '1' : '0.4';
}

// settings toast delegates to unified floating system
function showSettingsToast(msg, color) { showToast(msg, color); }
</script>

<div id="toast-container"></div>

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
