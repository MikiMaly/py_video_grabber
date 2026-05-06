# v7 — plánované změny

*(vše hotovo)*

---

## Hotovo v v6.9

- **Adaptivní fragmenty** — hill-climbing algoritmus každých 12s měří celkovou rychlost a +1/-1 upravuje `concurrent_fragments`; při poklesu rychlosti >10 % otočí směr; toggle + rozsah (min/max) v nastavení; v hlavičce badge "auto"

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
