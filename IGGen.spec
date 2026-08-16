# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project = Path(SPECPATH)

optional_datas = []
optional_binaries = []
optional_hiddenimports = []
for package in ('faster_whisper', 'whisper', 'uiautomator2', 'adbutils', 'playwright'):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package)
    except Exception:
        continue
    optional_datas += package_datas
    optional_binaries += package_binaries
    optional_hiddenimports += package_hiddenimports

a = Analysis(
    [str(project / 'app.py')],
    pathex=[str(project)],
    binaries=optional_binaries,
    datas=[
        (str(project / 'data'), 'data'),
        (str(project / 'assets'), 'assets'),
        (str(project / 'tools' / 'adb'), 'tools/adb'),
        (str(project / 'tools' / 'scrcpy'), 'tools/scrcpy'),
        (str(project / 'tools' / 'ffmpeg'), 'tools/ffmpeg'),
        (str(project / 'requirements-whisper.txt'), '.'),
    ] + optional_datas,
    hiddenimports=[
        'tools.audio_capture',
        'tools.runtime_variables',
        'tools.whisper_engine',
    ] + optional_hiddenimports,
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
    name='iggents',
    icon=str(project / 'assets' / 'iggents.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='iggents',
)
