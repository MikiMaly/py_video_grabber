# v7 — plánované změny

## UI

- **Barvy fronty** — položky ve frontě jsou šedé a counter „queue" v headeru je žlutý; sjednotit oboje na žlutou
- **Elapsed pod progress barem** — vedle ETA zobrazit i ELAP (jak dlouho se video už stahuje)

## Nastavení v GUI

- **Concurrent fragments** — přidat slider/input do nastavení; určuje kolik fragmentů jednoho videa se stahuje paralelně (aktuálně jen v config.yaml)

## Logika stahování

- **Lepší adaptivní logika** — např. automatické přizpůsobení počtu workerů nebo fragmentů podle aktuální rychlosti připojení; pokud je rychlost nízká, snížit paralelismus; pokud vysoká, zvýšit
