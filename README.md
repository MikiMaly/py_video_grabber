# py_video_grabber v6.8

Webový grabber videí postavený na yt-dlp s jednoduchým prohlížečovým UI.

## Jak to funguje

Spustíš `webapp.py`, automaticky se otevře prohlížeč na `http://localhost:8080`. Vložíš URL (nebo víc najednou oddělených mezerou), klikneš **Přidat** — URL se zobrazí ve frontě. Pak klikneš **Stažení** a všechna videa se začnou stahovat paralelně. Stav každého stahování (progress, rychlost, ETA) se aktualizuje každou sekundu. Dokončené soubory se ukládají do složky nastavitelné přímo v UI.

Každý job má auto-retry s exponenciálním backoffem, metadata se prefetchují na pozadí, stav fronty přežije restart (obnoví se z `grabber_state.json` — tento soubor není součástí repozitáře).

## Spuštění

```bash
pip install yt-dlp fastapi uvicorn pydantic PyYAML
python webapp.py
```

Otevře se `http://localhost:8080`. Port a config lze změnit přes argumenty:

```bash
python webapp.py --port 9000 --config config.yaml
```

## Co umí

- Webové UI — fronta, progress bary, ETA, rychlost
- Stahování ve více vláknech (nastavitelné v UI)
- Auto-retry s backoffem při chybě
- Výběr formátu (nejlepší kvalita / 1080p / 720p / …)
- Změna výstupní složky za běhu
- Prioritizace jobů (tlačítko ↑ Prio)
- Zrušení čekajících jobů, ruční retry failů
- URL bez `https://` — stačí zadat `youtube.com/…`

## Konfigurace

Viz [config.yaml](config.yaml) — download složka, počet workerů, formát, timeouty.

## Changelog

### v6.8
- Rebrand na "Ultimate Video Downloader"
- Nový tab Nastavení se všemi config.yaml hodnotami (workers, fragments, retries, timeouty, ffmpeg, user-agent)
- Header: workers +/- tlačítka nahrazena statickým displayem workers | frags

### v6.7
- Badge "Ve frontě" změněn na žlutou (sjednoceno s headerem)
- Elapsed/ETA přeuspořádáno: rychlost | elapsed (žlutě) | ETA (modře)
- Nativní Windows dialog pro výběr složky (tlačítko 📁)
- Fix: celková velikost se nepřepíše per-stream hodnotou u DASH formátů

### v6.6
- Web UI rewrite, priority fix, URL normalizace

### v6.5
- Meaningful filenames, auto-retry s backoffem, persistentní stav, graceful shutdown, prioritní fronta
