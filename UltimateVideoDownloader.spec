# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['webapp.py'],
    pathex=[],
    binaries=[
        ('ffmpeg/ffmpeg.exe', '.'),
        ('ffmpeg/ffprobe.exe', '.'),
    ],
    datas=[
        ('config.yaml', '.'),
        ('icon.ico', '.'),
    ],
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
    ],
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
