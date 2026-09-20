# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# site_resolvers needs curl_cffi for TLS impersonation; it ships a compiled
# libcurl and has no hook in pyinstaller-hooks-contrib, so collect it by hand.
_cc_datas, _cc_binaries, _cc_hidden = collect_all('curl_cffi')

a = Analysis(
    ['webapp.py'],
    pathex=[],
    binaries=[
        ('ffmpeg/ffmpeg.exe', '.'),
        ('ffmpeg/ffprobe.exe', '.'),
    ] + _cc_binaries,
    datas=[
        ('config.yaml', '.'),
        ('icon.ico', '.'),
    ] + _cc_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.extractor.lazy_extractors',
    ] + _cc_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='UltimateVideoDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UltimateVideoDownloader',
)
