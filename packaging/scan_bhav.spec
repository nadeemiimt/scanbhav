# PyInstaller spec — Scan Bhav desktop bundle
# Build: pyinstaller packaging/scan_bhav.spec --clean --noconfirm

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

block_cipher = None

hiddenimports = collect_submodules("routes")
hiddenimports += collect_submodules("trading")
hiddenimports += collect_submodules("quant_layer")
hiddenimports += collect_submodules("brokers")
hiddenimports += collect_submodules("analysis")
hiddenimports += [
    "api",
    "runtime_paths",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.importer",
    "uvicorn.main",
    "fastapi",
    "starlette.routing",
    "pydantic",
    "multipart",
    "pandas",
    "numpy",
    "yfinance",
    "chromadb",
    "chromadb.api",
    "chromadb.config",
    "pypdf",
    "dotenv",
    "jwt",
    "requests",
    "ollama",
]

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "packaging" / "bundle_data"), "bundle_data"),
    (str(ROOT / ".env.example"), "."),
]

for pkg in ("chromadb", "fastapi", "uvicorn", "pydantic", "certifi"):
    try:
        tmp_datas, tmp_binaries, tmp_hidden = collect_all(pkg)
        datas += tmp_datas
        hiddenimports += tmp_hidden
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScanBhav",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ScanBhav",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ScanBhav.app",
        icon=None,
        bundle_identifier="com.scanbhav.desktop",
        info_plist={
            "CFBundleName": "Scan Bhav",
            "CFBundleDisplayName": "Scan Bhav",
            "CFBundleVersion": "0.6.0",
            "CFBundleShortVersionString": "0.6.0",
            "NSHighResolutionCapable": True,
        },
    )
