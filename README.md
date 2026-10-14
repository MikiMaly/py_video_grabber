# py_video_grabber v6.9

Webový grabber videí postavený na yt-dlp s jednoduchým prohlížečovým UI.

## Jak to funguje

Spustíš `webapp.py`, automaticky se otevře prohlížeč na `http://localhost:8080`. Vložíš URL (nebo víc najednou oddělených mezerou), klikneš **Přidat** — URL se zobrazí ve frontě. Pak klikneš **Stažení** a všechna videa se začnou stahovat paralelně. Stav každého stahování (progress, rychlost, ETA) se aktualizuje každou sekundu. Dokončené soubory se ukládají do složky nastavitelné přímo v UI.

Každý job má auto-retry s exponenciálním backoffem, metadata se prefetchují na pozadí, stav fronty přežije restart (obnoví se z `grabber_state.json` — tento soubor není součástí repozitáře).

## Spuštění

```bash
pip install yt-dlp fastapi uvicorn pydantic PyYAML "curl_cffi>=0.10,<0.15"
python webapp.py
```

`curl_cffi` je volitelný, ale doporučený — bez něj nefunguje fallback resolver pro stránky, které yt-dlp neumí extrahovat přímo (viz `site_resolvers.py`).

Otevře se `http://localhost:8080`. Port a config lze změnit přes argumenty:

```bash
python webapp.py --port 9000 --config config.yaml
```

Server poslouchá jen na `127.0.0.1` (API nemá přihlášení). Přístup z jiných zařízení v síti povolíš přes `--host 0.0.0.0` — jen v důvěryhodné síti.

## Rozšíření do prohlížeče (pravé tlačítko → stáhnout)

Ve složce [`browser_extension/`](browser_extension) je rozšíření pro Chrome, Edge, Brave i Firefox. Na odkazu (nebo kdekoliv na stránce s videem) dáš pravé tlačítko → **Video Grabber** a vybereš:

- **Přidat do fronty** — zařadí se na konec
- **Stáhnout jako další (nahoru)** — přeskočí čekající videa; běžící stahování se nepřeruší. Když už odkaz ve frontě je, jen se posune nahoru
- **Přidat jako MP3** — stáhne jen zvuk

Klik na ikonu rozšíření v liště otevře UI grabberu. Grabber musí běžet (klidně s `--no-browser` na pozadí).

**Instalace (Chrome / Edge / Brave):** `chrome://extensions` (v Edge `edge://extensions`) → zapnout *Režim pro vývojáře* → *Načíst rozbalené* → vybrat složku `browser_extension`.

**Instalace (Firefox):** `about:debugging#/runtime/this-firefox` → *Načíst dočasný doplněk* → vybrat `browser_extension/manifest.json`. Dočasný doplněk vydrží jen do restartu Firefoxu; trvalá instalace vyžaduje podepsání přes addons.mozilla.org.

Pokud grabber běží na jiném portu, adresa se mění v nastavení rozšíření (pravý klik na ikonu → *Možnosti*).

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

Viz [CHANGELOG.md](CHANGELOG.md) — aktuálně v6.9: adaptivní fragmenty, per-job audio mode, FFmpeg fallback, MP3 badges.
