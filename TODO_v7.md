# v7 — plánované změny

## UI

- **Rebrand** — přejmenovat "Video Grabber" na "Ultimate Video Downloader" (název v headeru, title stránky, print v terminálu)

## Nastavení v GUI

- **Concurrent fragments** — přidat slider/input do nastavení; určuje kolik fragmentů jednoho videa se stahuje paralelně (aktuálně jen v config.yaml)

## Logika stahování

- **Lepší adaptivní logika** — např. automatické přizpůsobení počtu workerů nebo fragmentů podle aktuální rychlosti připojení; pokud je rychlost nízká, snížit paralelismus; pokud vysoká, zvýšit

---

## Hotovo v v6.7

- **Barvy fronty** — badge "Ve frontě" změněn na žlutou (sjednoceno s headerem)
- **Elapsed/ETA** — přeuspořádáno: rychlost | čas stahování (elapsed, žlutě) | čas do stažení (ETA, modře)
- **Složka picker** — nativní Windows dialog přes tlačítko 📁
- **Fix velikosti** — celková velikost se nepřepíše per-stream hodnotou u DASH formátů
