# Changelog

## v7.3
- URL input pole 2× větší (font 17px, padding 22px) + drag-and-drop linků z prohlížeče i textu
- Fronta (stage-list) se rozšiřuje s počtem položek až do 40vh místo fixních 130px
- Zelený focus glow na URL inputu

## v7.2
- Přejmenování UI termínů: Workers → "Stahování najednou" / "sloty", Concurrent fragments → "Segmenty najednou" / "seg.", fail → "selhalo"
- "Jen audio" checkbox přesunut z headeru přímo k tlačítku Stáhnout
- Status line dole zjednodušená: `2 sloty · 3 seg.`
- Zelený rebrand UVD ikony (modrá → zelená, všechny velikosti 16–512px + .ico)

## v7.1
- macOS build job v GitHub Actions (DMG) + Windows build běží paralelně
- Stabilní release filenames (`UltimateVideoDownloader-win64.zip`, `-macos.dmg`) pro přímé download linky
- "Stáhnout aplikaci" tlačítko v headeru míří na `/releases/latest`

## v7.0
- PyInstaller spec — single-file EXE build
- GitHub Actions CI — automatický build při push tagu `v*`
- Vlastní ikona (UVD logo) + favicon

## v6.9
- Adaptivní fragmenty — hill-climbing algoritmus každých 12s měří celkovou rychlost a ±1 upravuje `concurrent_fragments`; při poklesu rychlosti >10 % otočí směr; toggle + rozsah (min/max) v nastavení; badge "auto" v hlavičce
- Per-job audio mode — checkbox "Jen audio" v headeru; každý job má vlastní příznak; stahuje audio odděleně
- FFmpeg fallback — auto-detekce FFmpeg; pokud je dostupný: MP3 192 kbps; jinak M4A nativně
- Queue badges — zelený "MP3" badge u audio jobů v tabulce fronty
- Header UX — audio checkbox přesunut do headeru vlevo od čítačů; "auto" badge u workers/frags

## v6.8
- Rebrand na "Ultimate Video Downloader" (header, title, terminál)
- Nový tab ⚙ Nastavení se všemi hodnotami z config.yaml (složka, workers, fragments, formát, timeouty, retries, user-agent, ffmpeg)
- Header: workers +/− tlačítka nahrazena statickým displayem workers | frags
- Folder picker: macOS nativní dialog (osascript), Windows tkinter

## v6.7
- Badge "Ve frontě" změněn na žlutou (sjednoceno s headerem)
- Elapsed/ETA přeuspořádáno: rychlost | elapsed (žlutě) | ETA (modře)
- Nativní dialog pro výběr složky (tlačítko 📁)
- Fix: celková velikost se nepřepíše per-stream hodnotou u DASH formátů

## v6.6
- Web UI rewrite (FastAPI + embedded HTML/CSS/JS)
- Priority fix, URL normalizace
- Refaktor na grabber.py (daemon) + webapp.py (web UI)

## v6.5
- Meaningful filenames pomocí `%(title)s` v yt-dlp outtmpl
- Auto-retry s exponenciálním backoffem
- Persistentní stav fronty (grabber_state.json)
- Graceful shutdown — čeká na dokončení aktivních stahování
- Prioritní fronta (tlačítko ↑ Prio)
