#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
import shutil
import time
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

if getattr(sys, "frozen", False):
    _base = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    _exe_dir = Path(sys.executable).parent
    # PyInstaller >= 6 collects bundled binaries into _base (_internal/ for
    # onedir builds), not next to the exe — put both on PATH so ffmpeg is found.
    os.environ['PATH'] = os.pathsep.join(
        [str(_base), str(_exe_dir), os.environ.get('PATH', '')]
    )
else:
    _base = Path(__file__).parent
    _exe_dir = Path(__file__).parent

sys.path.insert(0, str(_base))

from grabber import GrabberDaemon, load_config, resolve_ffmpeg, fmt_hhmmss, fmt_size

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
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgdmlld0JveD0iMCAwIDMyIDMyIiBmaWxsPSJub25lIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImEiIHgxPSI0IiB5MT0iMjgiIHgyPSIyOCIgeTI9IjQiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiMyMmM1NWUiLz48c3RvcCBvZmZzZXQ9IjAuNTUiIHN0b3AtY29sb3I9IiMzZWUwYzMiLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM5ZWYwY2MiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB4PSIwLjc1IiB5PSIwLjc1IiB3aWR0aD0iMzAuNSIgaGVpZ2h0PSIzMC41IiByeD0iOSIgZmlsbD0iIzBjMTcxNSIgc3Ryb2tlPSJ1cmwoI2EpIiBzdHJva2Utb3BhY2l0eT0iMC41NSIgc3Ryb2tlLXdpZHRoPSIxLjUiLz48cGF0aCBkPSJNNy41IDIyLjVWMTMuNWEzLjc1IDMuNzUgMCAwIDEgNy41IDB2OU0xNSAxMy41YTMuNzUgMy43NSAwIDAgMSA3LjUgMHY5IiBzdHJva2U9InVybCgjYSkiIHN0cm9rZS13aWR0aD0iMi42IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48Y2lyY2xlIGN4PSIyNi4yNSIgY3k9IjIyLjI1IiByPSIxLjkiIGZpbGw9IiNlODMzNmYiLz48L3N2Zz4=">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  /* ════════════════════════════════════════════════════════════
     mmaly.cz 2.0 — vizuální identita „Skleník" (podle hubu)
     Paleta = src/styles/theme.css v repu MikiMaly/hub, blok „Paleta".
     Hex kódy jsou JEN TADY; zbytek CSS bere tokeny var(--hub-*).
     Při ladění palety v hubu upravit i tady (a icon.svg).
     ════════════════════════════════════════════════════════════ */
  :root {
    --hub-green: #22c55e;       /* značka, primární akce, hotovo */
    --hub-green-deep: #15803d;  /* stisk, tmavší varianta */
    --hub-mint: #9ef0cc;        /* jemné zvýraznění, popisky */
    --hub-aqua: #3ee0c3;        /* akvamarín: stahuje, info, odkazy, focus */
    --hub-raspberry: #e8336f;   /* malina: chyba, rušení, priorita */
    --hub-apricot: #f5a65b;     /* meruňka: čeká, ve frontě, retry */

    --hub-ink: #070e0d;         /* pozadí stránky */
    --hub-ink-2: #0c1715;       /* karta */
    --hub-ink-3: #12211e;       /* inputy, sekundární plocha */
    --hub-ink-4: #1a2e2a;       /* hover, muted */
    --hub-text: #e4f1ec;
    --hub-text-dim: #8ba59d;
    --hub-text-faint: color-mix(in srgb, var(--hub-text-dim) 68%, var(--hub-ink));

    --border: color-mix(in srgb, var(--hub-mint) 9%, transparent);
    --border-strong: color-mix(in srgb, var(--hub-mint) 18%, transparent);
    --hub-aurora: linear-gradient(120deg, var(--hub-green) 0%, var(--hub-aqua) 55%, var(--hub-mint) 100%);

    --font-sans: 'Inter', 'Segoe UI', system-ui, sans-serif;
    --font-display: 'Space Grotesk', 'Inter', system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, Consolas, monospace;
    color-scheme: dark;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--hub-ink); color: var(--hub-text); font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
         font-size: 14px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

  /* ── header ── */
  header { flex-shrink: 0; padding: 8px 20px; background: var(--hub-ink-2); border-bottom: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent);
           display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  header h1 { font-size: 16px; color: var(--hub-text); font-weight: 600; margin-right: auto; }
  .stat { display: flex; flex-direction: column; align-items: center; min-width: 44px; }
  .stat-val { font-size: 17px; font-weight: 700; line-height: 1; }
  .stat-lbl { font-size: 10px; color: var(--hub-text-dim); margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
  .s-active .stat-val { color: var(--hub-aqua); }
  .s-queue  .stat-val { color: var(--hub-apricot); }
  .s-done   .stat-val { color: var(--hub-green); }
  .s-fail   .stat-val { color: var(--hub-raspberry); }
  #shutdown-banner { display: none; color: var(--hub-raspberry); font-size: 12px; font-weight: 600; }

  /* workers display */
  .workers-disp { display: flex; align-items: center; gap: 5px; }
  .workers-disp .sep { color: var(--hub-text-faint); padding: 0 3px; }
  #workers-val, #frags-val { font-size: 15px; font-weight: 700; color: var(--hub-text); min-width: 18px; text-align: center; }

  /* ── tabs nav ── */
  .tabs-nav { flex-shrink: 0; background: var(--hub-ink-2); border-bottom: 2px solid color-mix(in srgb, var(--hub-mint) 9%, transparent);
              display: flex; align-items: center; }
  .tab-btn { background: none; border: none; border-bottom: 3px solid transparent; margin-bottom: -2px;
             padding: 8px 20px; color: var(--hub-text-dim); cursor: pointer; font-size: 13px; font-weight: 500;
             transition: color .15s, border-color .15s; }
  .tab-btn:hover { color: var(--hub-text); }
  .tab-btn.active { color: var(--hub-text); border-bottom-color: var(--hub-green); }
  .tab-btn.tab-icon { padding: 6px 16px; font-size: 18px; line-height: 1; }
  .tabs-nav-right { margin-left: auto; display: flex; align-items: center; gap: 14px; padding: 0 20px; }

  /* ── tab containers ── */
  #tab-download { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
  #tab-settings { flex: 1; overflow-y: auto; }

  /* ── staging ── */
  .staging { flex-shrink: 0; background: var(--hub-ink-2); border-bottom: 2px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); }
  .stage-input-row { display: flex; gap: 10px; align-items: center; padding: 28px 20px; border-bottom: 1px solid var(--hub-ink-3);
                     transition: background .15s; }
  .stage-input-row.drag-over { background: color-mix(in srgb, var(--hub-green) 8%, transparent); }
  .stage-input-row.drag-over input { border-color: var(--hub-green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--hub-green) 18%, transparent); }
  .stage-input-row input { flex: 1; background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 10px;
                            padding: 22px 18px; color: var(--hub-text); font-size: 17px; outline: none;
                            transition: border-color .15s, box-shadow .15s; }
  .stage-input-row input:focus { border-color: var(--hub-green); box-shadow: 0 0 0 2px color-mix(in srgb, var(--hub-green) 15%, transparent); }
  .stage-input-row input::placeholder { color: var(--hub-text-faint); }
  .stage-list { max-height: 40vh; overflow-y: auto; }
  .stage-item { display: flex; align-items: center; gap: 8px; padding: 4px 20px; border-bottom: 1px solid var(--hub-ink-3); }
  .stage-item:last-child { border-bottom: none; }
  .stage-url { flex: 1; font-size: 12px; color: var(--hub-text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .staged-empty { padding: 8px 20px; font-size: 12px; color: var(--hub-text-faint); }
  .stage-footer { display: flex; align-items: center; gap: 10px; padding: 8px 20px; flex-wrap: wrap; }
  .folder-row { display: flex; align-items: center; gap: 6px; margin-left: auto; }
  .folder-input { background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                  padding: 5px 10px; color: var(--hub-text); font-size: 12px; width: 260px; outline: none; transition: border-color .15s; }
  .folder-input:focus { border-color: var(--hub-aqua); }
  .fmt-select { background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                padding: 5px 8px; color: var(--hub-text); font-size: 12px; outline: none; cursor: pointer; }
  .fmt-select:focus { border-color: var(--hub-aqua); }

  /* ── buttons ── */
  .btn { background: var(--hub-green); color: var(--hub-ink); border: none; border-radius: 8px; padding: 7px 16px;
         cursor: pointer; font-size: 14px; font-weight: 600; transition: background .15s; white-space: nowrap; }
  .btn:hover { background: var(--hub-green-deep); }
  .btn:disabled { background: var(--hub-ink-3); color: var(--hub-text-faint); cursor: default; }
  .btn-danger { background: var(--hub-ink-4); }
  .btn-danger:hover { background: var(--hub-text-dim); }
  .btn-sm { background: var(--hub-ink-3); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); color: var(--hub-text); border-radius: 6px;
            padding: 5px 10px; cursor: pointer; font-size: 12px; transition: background .15s; white-space: nowrap; }
  .btn-sm:hover { background: color-mix(in srgb, var(--hub-mint) 9%, transparent); }
  .btn-prio   { background: var(--hub-aqua); padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-prio:hover   { background: var(--hub-mint); }
  .btn-cancel { background: var(--hub-ink-4); padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-cancel:hover { background: var(--hub-text-dim); }
  .btn-retry  { background: var(--hub-mint); padding: 3px 8px; font-size: 11px; border: none; border-radius: 4px; color: #fff; cursor: pointer; white-space: nowrap; }
  .btn-retry:hover  { background: var(--hub-aqua); }
  .btn-remove { background: none; border: none; color: var(--hub-text-faint); cursor: pointer; font-size: 14px; padding: 0 4px; }
  .btn-remove:hover { color: var(--hub-raspberry); }
  #toast { font-size: 12px; min-width: 80px; }

  /* ── table ── */
  .table-wrap { flex: 1; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  colgroup .col-id  { width: 40px; }
  colgroup .col-st  { width: 100px; }
  colgroup .col-ttl { width: auto; }
  colgroup .col-prg { width: 270px; }
  colgroup .col-act { width: 130px; }
  thead th { padding: 6px 10px; text-align: left; font-size: 11px; font-weight: 600; color: var(--hub-text-dim);
             background: var(--hub-ink-2); border-bottom: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); position: sticky; top: 0; z-index: 1;
             text-transform: uppercase; letter-spacing: 0.5px; }
  tbody tr { border-bottom: 1px solid var(--hub-ink-3); transition: background .1s; }
  tbody tr:hover { background: var(--hub-ink-2); }
  td { padding: 6px 10px; vertical-align: middle; overflow: hidden; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .b-downloading { background: color-mix(in srgb, var(--hub-aqua) 15%, transparent); color: var(--hub-aqua); }
  .b-queued      { background: color-mix(in srgb, var(--hub-apricot) 15%, transparent); color: var(--hub-apricot); }
  .b-pending     { background: color-mix(in srgb, var(--hub-apricot) 15%, transparent); color: var(--hub-apricot); }
  .b-done        { background: color-mix(in srgb, var(--hub-green) 15%, transparent); color: var(--hub-green); }
  .b-fail        { background: color-mix(in srgb, var(--hub-raspberry) 15%, transparent); color: var(--hub-raspberry); }
  .t-title { font-weight: 500; color: var(--hub-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-url   { font-size: 11px; color: var(--hub-text-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
  .bar-bg  { background: var(--hub-ink-3); border-radius: 4px; height: 5px; margin-bottom: 4px; }
  .bar-fill{ height: 5px; border-radius: 4px; background: var(--hub-aqua); transition: width 0.6s linear; }
  .prog-row{ display: flex; gap: 8px; font-size: 12px; color: var(--hub-text-dim); flex-wrap: wrap; }
  .pct { color: var(--hub-text); font-weight: 600; }
  .spd { color: var(--hub-green); }
  .eta { color: var(--hub-aqua); }
  .eta.bad { color: var(--hub-raspberry); }
  .elap { color: var(--hub-apricot); }
  .dim { color: var(--hub-text-faint); }
  .retry-tag { color: var(--hub-apricot); font-size: 11px; }
  .prio-tag  { color: var(--hub-aqua); font-size: 11px; }
  .path-txt  { font-size: 11px; color: var(--hub-text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .err-txt   { font-size: 11px; color: var(--hub-raspberry); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .act-btns  { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
  .empty-row td { padding: 40px; text-align: center; color: var(--hub-text-faint); }

  /* ── settings ── */
  .settings-scroll { max-width: 620px; padding: 20px; }
  .settings-section { background: var(--hub-ink-2); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 12px;
                       padding: 16px; margin-bottom: 16px; }
  .settings-section-title { font-size: 11px; font-weight: 600; color: var(--hub-text-dim); text-transform: uppercase;
                              letter-spacing: 0.5px; margin-bottom: 12px; }
  .settings-row { display: flex; align-items: center; gap: 12px; padding: 7px 0;
                  border-bottom: 1px solid var(--hub-ink-3); }
  .settings-row:last-child { border-bottom: none; padding-bottom: 0; }
  .settings-row label { font-size: 13px; color: var(--hub-text); min-width: 175px; flex-shrink: 0; }
  .settings-hint { font-size: 11px; color: var(--hub-text-faint); }
  .settings-input { flex: 1; background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                    padding: 6px 10px; color: var(--hub-text); font-size: 13px; outline: none; }
  .settings-input:focus { border-color: var(--hub-aqua); }
  .settings-input-num { width: 90px; background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                         padding: 6px 10px; color: var(--hub-text); font-size: 13px; outline: none; text-align: right; }
  .settings-input-num:focus { border-color: var(--hub-aqua); }
  .settings-select { background: var(--hub-ink); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                     padding: 6px 8px; color: var(--hub-text); font-size: 13px; outline: none; cursor: pointer; }
  .settings-select:focus { border-color: var(--hub-aqua); }
  .settings-actions { display: flex; align-items: center; gap: 16px; }
  #settings-toast { font-size: 13px; }

  /* ── download app button ── */
  .dl-app-btn { font-size: 12px; color: var(--hub-aqua); border: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); border-radius: 6px;
                padding: 4px 10px; text-decoration: none; white-space: nowrap; }
  .dl-app-btn:hover { background: var(--hub-ink-3); border-color: var(--hub-aqua); }

  /* ── audio checkbox ── */
  .audio-chk-label { display: flex; align-items: center; gap: 5px; font-size: 12px;
                     color: var(--hub-text-dim); cursor: pointer; white-space: nowrap; user-select: none;
                     border-right: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); padding-right: 16px; }
  .audio-chk-label input { accent-color: var(--hub-green); cursor: pointer; width: 14px; height: 14px; }
  .audio-chk-label.active { color: var(--hub-green); }

  /* ── audio badge in queue ── */
  .audio-badge { display: inline-block; padding: 1px 6px; border-radius: 10px; font-size: 10px;
                 font-weight: 700; background: color-mix(in srgb, var(--hub-green) 15%, transparent); color: var(--hub-green); margin-left: 6px;
                 vertical-align: middle; letter-spacing: 0.3px; }

  /* ── statusline ── */
  .statusline { flex-shrink: 0; padding: 3px 20px; font-size: 11px; color: var(--hub-text-faint);
                background: var(--hub-ink-2); border-top: 1px solid color-mix(in srgb, var(--hub-mint) 9%, transparent); }

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
              background: linear-gradient(135deg, var(--hub-green) 0%, var(--hub-aqua) 100%);
              -webkit-background-clip: text; background-clip: text; color: transparent;
              -webkit-text-fill-color: transparent; }

  /* stat cards */
  .stat-cards { display: flex; gap: 10px; }
  .stat-card { position: relative; padding: 10px 16px 10px 14px; min-width: 82px;
               background: var(--hub-ink-3); border: 1px solid color-mix(in srgb, var(--hub-mint) 5.4%, transparent);
               border-radius: 12px; transition: transform .2s ease, border-color .2s, box-shadow .2s; }
  .stat-card:hover { transform: translateY(-2px); }
  .stat-card.s-active:hover { border-color: color-mix(in srgb, var(--hub-aqua) 40%, transparent); box-shadow: 0 6px 20px color-mix(in srgb, var(--hub-aqua) 8%, transparent); }
  .stat-card.s-queue:hover  { border-color: color-mix(in srgb, var(--hub-apricot) 40%, transparent); box-shadow: 0 6px 20px color-mix(in srgb, var(--hub-apricot) 8%, transparent); }
  .stat-card.s-done:hover   { border-color: color-mix(in srgb, var(--hub-green) 40%, transparent);  box-shadow: 0 6px 20px color-mix(in srgb, var(--hub-green) 8%, transparent); }
  .stat-card.s-fail:hover   { border-color: color-mix(in srgb, var(--hub-raspberry) 40%, transparent);  box-shadow: 0 6px 20px color-mix(in srgb, var(--hub-raspberry) 8%, transparent); }
  .stat-card .stat-icon { position: absolute; top: 9px; right: 10px; opacity: 0.5; }
  .stat-card .stat-num  { font-size: 22px; font-weight: 700; line-height: 1; }
  .stat-card .stat-cap  { font-size: 10px; color: var(--hub-text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
  .stat-card.s-active .stat-num { color: var(--hub-aqua); }
  .stat-card.s-queue  .stat-num { color: var(--hub-apricot); }
  .stat-card.s-done   .stat-num { color: var(--hub-green); }
  .stat-card.s-fail   .stat-num { color: var(--hub-raspberry); }

  /* job cards */
  .job-list { padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
  .job-card { position: relative; padding: 14px 18px 14px 22px; background: var(--hub-ink-2);
              border: 1px solid color-mix(in srgb, var(--hub-mint) 7.2%, transparent); border-radius: 12px;
              transition: transform .2s, border-color .2s, box-shadow .2s;
              overflow: hidden; animation: card-in .25s ease-out; }
  .job-card:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--hub-mint) 13.5%, transparent); }
  .job-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
                      background: var(--accent, var(--hub-text-dim)); }
  .job-card.j-downloading { --accent: var(--hub-aqua); }
  .job-card.j-queued      { --accent: var(--hub-apricot); }
  .job-card.j-pending     { --accent: var(--hub-apricot); }
  .job-card.j-done        { --accent: var(--hub-green); }
  .job-card.j-fail        { --accent: var(--hub-raspberry); }
  .job-card.j-downloading::after {
    content: ''; position: absolute; left: -20%; top: -20%; right: -20%; bottom: -20%;
    background: radial-gradient(ellipse at 30% 50%, color-mix(in srgb, var(--hub-aqua) 8%, transparent) 0%, transparent 60%);
    pointer-events: none; animation: pulse-halo 2.5s ease-in-out infinite; z-index: 0; }
  @keyframes pulse-halo { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
  @keyframes card-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  .job-card > * { position: relative; z-index: 1; }

  .job-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
  .job-status-pill { display: inline-flex; align-items: center; gap: 6px;
                     font-size: 11px; font-weight: 600; text-transform: uppercase;
                     letter-spacing: 0.4px; padding: 3px 10px; border-radius: 20px;
                     background: color-mix(in srgb, var(--hub-mint) 3.6%, transparent); color: var(--accent); }
  .job-status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
                          box-shadow: 0 0 6px var(--accent); }
  .job-card.j-downloading .job-status-pill .dot { animation: blink 1.2s ease-in-out infinite; }
  @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
  .job-id { color: var(--hub-text-faint); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .job-actions { margin-left: auto; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .job-title { font-size: 14px; font-weight: 500; color: var(--hub-text);
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
  .job-url { font-size: 11px; color: var(--hub-text-faint);
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .job-progress { margin-top: 10px; }
  .job-progress .bar-bg { background: color-mix(in srgb, var(--hub-mint) 4.5%, transparent); height: 6px; border-radius: 4px; overflow: hidden; }
  .job-progress .bar-fill { height: 6px; border-radius: 4px;
                            background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 60%, white));
                            transition: width 0.6s linear;
                            box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 50%, transparent); }
  .job-meta-row { display: flex; gap: 14px; font-size: 12px; color: var(--hub-text-dim); margin-top: 6px; flex-wrap: wrap;
                  font-variant-numeric: tabular-nums; }
  .job-meta-row .pct { color: var(--hub-text); font-weight: 600; }
  .job-meta-row .spd { color: var(--hub-green); }
  .job-meta-row .eta { color: var(--hub-aqua); }
  .job-meta-row .eta.bad { color: var(--hub-raspberry); }
  .job-meta-row .elap { color: var(--hub-apricot); }
  .job-meta-row .dim { color: var(--hub-text-faint); }
  .job-meta-row .retry-tag { color: var(--hub-apricot); }
  .job-meta-row .prio-tag  { color: var(--hub-aqua); }

  /* lucide icon helper */
  .icon { display: inline-block; vertical-align: middle; flex-shrink: 0; }

  /* hover lifts on interactive elements */
  .btn:hover, .dl-app-btn:hover { transform: translateY(-1px); }
  .stat-card { will-change: transform; }

  /* floating toasts */
  #toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 1000;
                     display: flex; flex-direction: column; gap: 8px; max-width: 360px; }
  .toast { padding: 11px 16px; background: var(--hub-ink-2);
           border: 1px solid color-mix(in srgb, var(--hub-mint) 7.2%, transparent); border-left: 3px solid var(--hub-green);
           border-radius: 10px; font-size: 13px; color: var(--hub-text);
           animation: toast-in .35s cubic-bezier(0.16, 1, 0.3, 1);
           box-shadow: 0 10px 30px rgba(0,0,0,0.4); display: flex; align-items: center; gap: 8px; }
  .toast.t-error { border-left-color: var(--hub-raspberry); }
  .toast.t-info  { border-left-color: var(--hub-aqua); }
  .toast.fade-out { animation: toast-out .25s ease-in forwards; }
  @keyframes toast-in  { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
  @keyframes toast-out { to { opacity: 0; transform: translateX(40px); } }

  /* staged item slide-in */
  .stage-item { animation: stage-in .2s ease-out; }
  @keyframes stage-in { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }

  /* empty states */
  .empty-state { padding: 70px 20px 60px; text-align: center; color: var(--hub-text-faint);
                 display: flex; flex-direction: column; align-items: center; }
  .empty-state .empty-icon { opacity: 0.25; margin-bottom: 16px; color: var(--hub-text-dim); }
  .empty-state .empty-title { font-size: 14px; color: var(--hub-text-dim); margin-bottom: 4px; font-weight: 500; }
  .empty-state .empty-hint  { font-size: 12px; color: var(--hub-text-faint); }

  /* tab content fade */
  #tab-download, #tab-settings { animation: fade-in .25s ease-out; }
  @keyframes fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

  /* hide old #toast/#settings-toast inline spans (kept in markup for backward compat — moved to floating) */
  #toast, #settings-toast { display: none; }

  /* ════════════════════════════════════════════════════════════
     ── v9 Skleník ── přebíjí starší pravidla výše
     ════════════════════════════════════════════════════════════ */

  body { font-family: var(--font-sans); background-color: var(--hub-ink); -webkit-font-smoothing: antialiased;
         isolation: isolate; }
  /* skleněné tabule (mřížka 56 px) + záře zelená / akvamarín / malina */
  body::before { content: ''; position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background-image:
      linear-gradient(color-mix(in srgb, var(--hub-mint) 4.5%, transparent) 1px, transparent 1px),
      linear-gradient(90deg, color-mix(in srgb, var(--hub-mint) 4.5%, transparent) 1px, transparent 1px);
    background-size: 56px 56px;
    -webkit-mask-image: radial-gradient(ellipse 90% 60% at 50% 0%, black 0%, transparent 75%);
            mask-image: radial-gradient(ellipse 90% 60% at 50% 0%, black 0%, transparent 75%); }
  body::after { content: ''; position: fixed; inset: 0; z-index: -2; pointer-events: none;
    background:
      radial-gradient(40rem 26rem at 12% -8%, color-mix(in srgb, var(--hub-green) 14%, transparent), transparent 70%),
      radial-gradient(34rem 22rem at 92% 4%, color-mix(in srgb, var(--hub-aqua) 10%, transparent), transparent 70%),
      radial-gradient(22rem 16rem at 70% 110%, color-mix(in srgb, var(--hub-raspberry) 7%, transparent), transparent 70%); }
  ::selection { background: color-mix(in srgb, var(--hub-aqua) 35%, transparent); color: var(--hub-text); }
  :focus-visible { outline: 2px solid var(--hub-aqua); outline-offset: 2px; }
  select option { background: var(--hub-ink-2); }

  /* lišty jako matné sklo, aby prosvítala mřížka */
  header, .tabs-nav, .staging, .statusline {
    background: color-mix(in srgb, var(--hub-ink) 62%, transparent);
    backdrop-filter: blur(18px) saturate(140%); -webkit-backdrop-filter: blur(18px) saturate(140%);
    border-color: var(--border); }
  .tabs-nav { border-bottom-width: 1px; }
  .staging { border-bottom-width: 1px; }
  .stage-input-row, .stage-item { border-color: var(--border); }

  /* značka: logo hubu, název v aurora přechodu, malinová tečka */
  .brand .logo { width: 34px; height: 34px; }
  .brand h1 { font-family: var(--font-display); font-weight: 700; font-size: 23px; letter-spacing: -0.03em;
              background: var(--hub-aurora); -webkit-background-clip: text; background-clip: text; }
  .brand h1 .dot { color: var(--hub-raspberry); -webkit-text-fill-color: var(--hub-raspberry); }

  /* štítky a popisky: mono, uppercase */
  .stat-lbl, .stat-card .stat-cap, .settings-section-title, .job-status-pill, .job-id {
    font-family: var(--font-mono); letter-spacing: 0.12em; }
  .stat-card .stat-cap, .stat-lbl { font-size: 9.5px; }
  .settings-section-title { color: var(--hub-mint); display: flex; align-items: center; gap: 8px; }
  .settings-section-title::before { content: ''; width: 6px; height: 6px; border-radius: 50%;
                                    background: var(--hub-green); box-shadow: 0 0 10px var(--hub-green); }
  .stat-card .stat-num, #workers-val, #frags-val { font-family: var(--font-display); letter-spacing: -0.02em;
                                                   font-variant-numeric: tabular-nums; }

  /* karty: matné sklo s jemnou horní hranou */
  .stat-card, .job-card, .settings-section, .toast {
    background: linear-gradient(180deg, color-mix(in srgb, var(--hub-mint) 3.5%, transparent), transparent 40%), var(--hub-ink-2);
    border: 1px solid var(--border);
    box-shadow: inset 0 1px 0 color-mix(in srgb, var(--hub-text) 4%, transparent), 0 1px 2px rgba(0,0,0,0.3); }
  .stat-card, .settings-section { border-radius: 14px; }
  .job-card { border-radius: 16px; }
  .job-card:hover, .stat-card:hover { border-color: color-mix(in srgb, var(--hub-aqua) 38%, transparent);
    box-shadow: inset 0 1px 0 color-mix(in srgb, var(--hub-text) 6%, transparent),
                0 12px 40px -18px color-mix(in srgb, var(--hub-aqua) 45%, transparent); }
  .job-title { color: var(--hub-text); }
  .job-status-pill { background: color-mix(in srgb, var(--accent) 13%, transparent); }

  /* tlačítka podle .hub-btn-* */
  .btn { border-radius: 12px; color: #04110a; border: 1px solid transparent;
         box-shadow: 0 6px 24px -10px color-mix(in srgb, var(--hub-green) 70%, transparent), inset 0 1px 0 rgba(255,255,255,0.25);
         transition: background-color .15s, box-shadow .15s, transform .1s; }
  .btn:hover { background: color-mix(in srgb, var(--hub-green) 88%, var(--hub-mint)); }
  .btn:active:not(:disabled) { transform: translateY(1px); }
  .btn:disabled { background: var(--hub-ink-3); color: var(--hub-text-faint); box-shadow: none; border-color: var(--border); }
  .btn-danger, .btn-cancel {
    background: color-mix(in srgb, var(--hub-raspberry) 12%, transparent);
    color: color-mix(in srgb, var(--hub-raspberry) 80%, white);
    border: 1px solid color-mix(in srgb, var(--hub-raspberry) 24%, transparent); box-shadow: none; }
  .btn-danger:hover, .btn-cancel:hover { background: color-mix(in srgb, var(--hub-raspberry) 22%, transparent); }
  .btn-prio, .btn-retry {
    background: color-mix(in srgb, var(--hub-aqua) 12%, transparent); color: var(--hub-aqua);
    border: 1px solid color-mix(in srgb, var(--hub-aqua) 24%, transparent); }
  .btn-prio:hover, .btn-retry:hover { background: color-mix(in srgb, var(--hub-aqua) 20%, transparent); }
  .btn-prio, .btn-retry, .btn-cancel { border-radius: 8px; padding: 4px 9px; font-weight: 600; }
  .btn-sm { background: color-mix(in srgb, var(--hub-ink-3) 70%, transparent); border-color: var(--border); border-radius: 10px; }
  .btn-sm:hover { background: var(--hub-ink-4); border-color: var(--border-strong); }
  .dl-app-btn { color: var(--hub-aqua); background: color-mix(in srgb, var(--hub-aqua) 8%, transparent);
                border: 1px solid color-mix(in srgb, var(--hub-aqua) 24%, transparent); border-radius: 10px; }
  .dl-app-btn:hover { background: color-mix(in srgb, var(--hub-aqua) 16%, transparent); border-color: color-mix(in srgb, var(--hub-aqua) 40%, transparent); }

  /* inputy podle .hub-input: focus kroužek akvamarín */
  .stage-input-row input, .folder-input, .fmt-select, .settings-input, .settings-input-num, .settings-select {
    background: var(--hub-ink-3); border: 1px solid var(--border); }
  .stage-input-row input { border-radius: 14px; }
  .stage-input-row input:hover, .settings-input:hover, .settings-input-num:hover { border-color: var(--border-strong); }
  .stage-input-row input:focus, .folder-input:focus, .fmt-select:focus, .settings-input:focus,
  .settings-input-num:focus, .settings-select:focus {
    border-color: color-mix(in srgb, var(--hub-aqua) 60%, transparent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--hub-aqua) 16%, transparent); outline: none; }
  .stage-input-row input::placeholder { color: color-mix(in srgb, var(--hub-text-dim) 70%, transparent); }

  /* taby */
  .tab-btn.active { border-bottom-color: var(--hub-green); color: var(--hub-mint); }

  /* stavy: stahuje = akvamarín, čeká = meruňka, hotovo = zelená, chyba = malina */
  .job-card.j-downloading::after {
    background: radial-gradient(ellipse at 30% 50%, color-mix(in srgb, var(--hub-aqua) 9%, transparent) 0%, transparent 60%); }
  .job-card.j-downloading .bar-fill { background: var(--hub-aurora); }
  .job-meta-row .prio-tag { color: var(--hub-raspberry); }

  /* toasty podle .hub-toast */
  .toast { border-left: 3px solid var(--hub-green); border-radius: 12px; color: var(--hub-text);
           backdrop-filter: blur(8px); box-shadow: 0 12px 30px -12px rgba(0,0,0,0.6); }
  .toast.t-error { border-left-color: var(--hub-raspberry); }
  .toast.t-info  { border-left-color: var(--hub-aqua); }

  .audio-badge { font-family: var(--font-mono); letter-spacing: 0.06em; }
</style>
</head>
<body>

<header>
  <div class="brand">
    <img class="logo" src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgdmlld0JveD0iMCAwIDMyIDMyIiBmaWxsPSJub25lIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImEiIHgxPSI0IiB5MT0iMjgiIHgyPSIyOCIgeTI9IjQiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiMyMmM1NWUiLz48c3RvcCBvZmZzZXQ9IjAuNTUiIHN0b3AtY29sb3I9IiMzZWUwYzMiLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM5ZWYwY2MiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB4PSIwLjc1IiB5PSIwLjc1IiB3aWR0aD0iMzAuNSIgaGVpZ2h0PSIzMC41IiByeD0iOSIgZmlsbD0iIzBjMTcxNSIgc3Ryb2tlPSJ1cmwoI2EpIiBzdHJva2Utb3BhY2l0eT0iMC41NSIgc3Ryb2tlLXdpZHRoPSIxLjUiLz48cGF0aCBkPSJNNy41IDIyLjVWMTMuNWEzLjc1IDMuNzUgMCAwIDEgNy41IDB2OU0xNSAxMy41YTMuNzUgMy43NSAwIDAgMSA3LjUgMHY5IiBzdHJva2U9InVybCgjYSkiIHN0cm9rZS13aWR0aD0iMi42IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48Y2lyY2xlIGN4PSIyNi4yNSIgY3k9IjIyLjI1IiByPSIxLjkiIGZpbGw9IiNlODMzNmYiLz48L3N2Zz4=" alt="">
    <h1>Ultimate Video Downloader<span class="dot">.</span></h1>
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
      <span id="frags-val">?</span><span id="adapt-badge" style="display:none;font-size:10px;color:var(--hub-green);padding-left:3px">auto</span><span class="stat-lbl">seg.</span>
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
        <span style="color:var(--hub-text-dim);font-size:12px">Slo&#382;ka:</span>
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
        <input type="checkbox" id="cfg-adapt-frags" onchange="toggleAdaptBounds()" style="width:18px;height:18px;cursor:pointer;accent-color:var(--hub-green)">
        <span class="settings-hint">automaticky p&#345;izp&#367;sobovat po&#269;et fragment&#367; podle rychlosti</span>
      </div>
      <div class="settings-row" id="adapt-bounds-row">
        <label>Rozsah adapt. (min&nbsp;/&nbsp;max)</label>
        <input type="number" id="cfg-adapt-min" class="settings-input-num" min="1" max="32" style="width:70px">
        <span style="color:var(--hub-text-faint);padding:0 6px">&#8211;</span>
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
  if (added) showToast(added + ' URL přidáno ✓', 'var(--hub-green)');
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
  if (added) showToast(added + ' URL přidáno ✓', 'var(--hub-green)');
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
    showToast('Zahájeno: ' + d.added + '/' + d.total + ' ✓', 'var(--hub-green)');
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
    showToast('Složka změněna ✓', 'var(--hub-green)');
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
  if (d.ok) { inp.value = d.path; showToast('Složka změněna ✓', 'var(--hub-green)'); }
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
  if (color === 'var(--hub-raspberry)' || !color) cls += ' t-error';
  else if (color === 'var(--hub-aqua)') cls += ' t-info';
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
    : '<div class="job-title" style="color:var(--hub-text-dim)">'+esc(j.url)+audioBadge+'</div>';

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
        '<span title="'+esc(j.final_path)+'" style="color:var(--hub-text-dim)">'+esc(fname)+'</span>' +
        '<span>'+j.total_str+'</span>' +
        '<span class="dim">za '+j.elapsed_str+'</span>' +
      '</div>';

  } else if (j.status === 'fail') {
    progHtml = '<div class="job-meta-row" style="color:var(--hub-raspberry)" title="'+esc(j.error)+'">' +
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
    showSettingsToast('Chyba načítání nastavení', 'var(--hub-raspberry)');
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
      showSettingsToast('Nastavení uloženo ✓', 'var(--hub-green)');
      settingsLoaded = false;
      if (payload.download_dir) document.getElementById('out-dir-input').value = payload.download_dir;
      const stageFmt = document.getElementById('fmt-select');
      for (let i = 0; i < stageFmt.options.length; i++) {
        if (stageFmt.options[i].value === payload.format) { stageFmt.selectedIndex = i; break; }
      }
      syncAudioCheckbox(payload.format);
    } else {
      showSettingsToast(d.error || 'Chyba', 'var(--hub-raspberry)');
    }
  } catch(e) {
    showSettingsToast('Chyba spojení', 'var(--hub-raspberry)');
  }
}

async function cfgBrowseFolder() {
  const r = await fetch('/api/browse_folder');
  const d = await r.json();
  if (d.ok) {
    document.getElementById('cfg-download-dir').value = d.path;
    document.getElementById('out-dir-input').value = d.path;
    showSettingsToast('Složka vybrána ✓', 'var(--hub-green)');
  } else if (!d.cancelled) {
    showSettingsToast(d.error || 'Chyba', 'var(--hub-raspberry)');
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
    top: bool = False

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
    return daemon.add_bulk(req.urls, audio_only=req.audio_only, top=req.top)


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
            import tkinter as tk
            from tkinter import filedialog

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

def _resolve_config(arg: str) -> Path:
    """Locate config.yaml.

    In a frozen build the bundled copy sits in _base, which the user cannot edit
    (and which is a throwaway temp dir for onefile builds), so seed a copy next
    to the executable on first run and use that from then on.
    """
    cfg_name = Path(arg).expanduser()
    if cfg_name.is_absolute() or not getattr(sys, "frozen", False):
        return cfg_name

    user_cfg = _exe_dir / cfg_name
    if user_cfg.is_file():
        return user_cfg

    bundled = _base / cfg_name
    if bundled.is_file():
        try:
            shutil.copyfile(bundled, user_cfg)
            return user_cfg
        except OSError:
            return bundled          # read-only location, e.g. a mounted DMG
    return user_cfg


def _data_dir(config_dir: Path) -> Path:
    """Where the state file and relative download dirs live: next to the app if
    that is writable, otherwise the user's home."""
    base = _exe_dir if getattr(sys, "frozen", False) else config_dir
    probe = base / ".uvd_write_test"
    try:
        probe.touch()
        probe.unlink()
        return base
    except OSError:
        fallback = Path.home() / "UltimateVideoDownloader"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _own_console_window(port: int) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    import subprocess
    from ctypes import wintypes

    k32, u32 = ctypes.WinDLL("kernel32"), ctypes.WinDLL("user32")
    k32.GetConsoleWindow.restype = wintypes.HWND
    u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    hwnd = k32.GetConsoleWindow()
    if not hwnd:
        return

    cls = ctypes.create_unicode_buffer(64)
    u32.GetClassNameW(hwnd, cls, 64)
    launched_alone = k32.GetConsoleProcessList((wintypes.DWORD * 2)(), 2) == 1
    # under Windows Terminal (Win11 default) the taskbar shows Terminal's icon; a classic console shows the exe's own
    if cls.value == "PseudoConsoleWindow" and launched_alone and not os.environ.get("UVD_CONHOST"):
        conhost = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "conhost.exe"
        if conhost.exists():
            argv = [sys.executable] + (sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
            subprocess.Popen([str(conhost), *argv], env={**os.environ, "UVD_CONHOST": "1"})
            sys.exit(0)

    k32.SetConsoleTitleW(f"Ultimate Video Downloader · server :{port}")


def main():
    global daemon

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port",   type=int, default=8080)
    # localhost only by default — the API has no auth; use 0.0.0.0 only on a trusted network
    ap.add_argument("--host",   default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    _own_console_window(args.port)

    cfg_path = _resolve_config(args.config)
    cfg = load_config(str(cfg_path))
    data_dir = _data_dir(cfg_path.resolve().parent)

    # bundled ffmpeg first, then PATH — a stale path from config is discarded
    cfg["ffmpeg_path"] = resolve_ffmpeg(cfg.get("ffmpeg_path", ""), _base, _exe_dir)

    dl_dir = Path(cfg["download_dir"]).expanduser()
    cfg["download_dir"] = str(dl_dir if dl_dir.is_absolute() else data_dir / dl_dir)

    state_path = Path(cfg.get("state_file", "grabber_state.json")).expanduser()
    if not state_path.is_absolute():
        state_path = data_dir / state_path
    state_path = state_path.resolve()

    daemon = GrabberDaemon(cfg, state_path)
    daemon._load_state()
    daemon.start()

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    print(f"Ultimate Video Downloader -> http://localhost:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
