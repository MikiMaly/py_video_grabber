#!/usr/bin/env bash
set -e

APP_NAME="UltimateVideoDownloader"
VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "dev")

echo "============================================"
echo " Video Grabber — build macOS DMG"
echo " Version: $VERSION"
echo "============================================"
echo

echo "[1/3] Instaluji PyInstaller..."
pip3 install pyinstaller

echo
echo "[2/3] Buildím ${APP_NAME}..."
PYINSTALLER="$HOME/Library/Python/3.9/bin/pyinstaller"
"$PYINSTALLER" --onefile \
  --name "$APP_NAME" \
  --collect-all yt_dlp \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.main \
  webapp.py

echo
echo "[3/3] Vytvářím DMG..."
DMG_DIR="$(pwd)/dist/dmg_tmp"
DMG_OUT="dist/${APP_NAME}-${VERSION}-macos.dmg"

rm -rf "$DMG_DIR"
mkdir -p "$DMG_DIR"
cp "dist/$APP_NAME" "$DMG_DIR/"
cp config.yaml "$DMG_DIR/config.yaml"
cat > "$DMG_DIR/SPUŠTĚNÍ.txt" <<'README'
Jak spustit:
1. Přesuň UltimateVideoDownloader a config.yaml do stejné složky
2. V Terminálu spusť: chmod +x UltimateVideoDownloader && ./UltimateVideoDownloader
3. Prohlížeč se otevře automaticky na http://localhost:8080
README

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_DIR" \
  -ov -format UDZO \
  "$DMG_OUT"

rm -rf "$DMG_DIR"

echo
echo "============================================"
echo " Hotovo! → $DMG_OUT"
echo "============================================"
