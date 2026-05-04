@echo off
echo ============================================
echo  Video Grabber - build .exe (PyInstaller)
echo ============================================
echo.

echo [1/2] Instaluji PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo CHYBA: pip selhal. Je Python v PATH?
    pause & exit /b 1
)

echo.
echo [2/2] Buildim VideoGrabber.exe ...
pyinstaller --onefile ^
  --name VideoGrabber ^
  --collect-all yt_dlp ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.http.h11_impl ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.main ^
  webapp.py

if errorlevel 1 (
    echo.
    echo CHYBA: build selhal. Viz vystup vyse.
    pause & exit /b 1
)

echo.
echo ============================================
echo  Hotovo!  dist\VideoGrabber.exe
echo ============================================
echo.
echo Zkopiruj do stejne slozky:
echo   - config.yaml
echo   (ffmpeg neni nutny, ale doporuceny)
echo.
pause
