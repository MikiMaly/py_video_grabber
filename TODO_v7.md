# v7 — plánované změny

## Logika stahování

- **Lepší adaptivní logika** — např. automatické přizpůsobení počtu workerů nebo fragmentů podle aktuální rychlosti připojení; pokud je rychlost nízká, snížit paralelismus; pokud vysoká, zvýšit

---

## Hotovo v v6.8

- **Rebrand** — přejmenovat na "Ultimate Video Downloader" (header, title, terminál)
- **Settings tab** — nový tab ⚙ Nastavení se všemi hodnotami z config.yaml (složka, workers, fragments, formát, timeouty, retries, user-agent, ffmpeg)
- **Workers display** — header místo +/- tlačítek zobrazuje jen aktuální počet workers | frags
- **Terminál** — jen startup řádek, žádné další výstupy

## Hotovo v v6.7

- **Barvy fronty** — badge "Ve frontě" změněn na žlutou (sjednoceno s headerem)
- **Elapsed/ETA** — přeuspořádáno: rychlost | čas stahování (elapsed, žlutě) | čas do stažení (ETA, modře)
- **Složka picker** — nativní Windows dialog přes tlačítko 📁
- **Fix velikosti** — celková velikost se nepřepíše per-stream hodnotou u DASH formátů
