# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CombinePro (macOS .app / Windows folder+exe).

Build with:  pyinstaller packaging/CombinePro.spec --noconfirm
The platform build scripts call this; run it directly only for debugging.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# --------------------------------------------------------------------- data
# Read-only assets copied into the bundle's resource root (app.paths.resource_dir()).
datas = [
    (str(ROOT / "AppIcons"), "AppIcons"),
    (str(ROOT / ".env.example"), "."),
]

# The Node memory sidecar: its source plus installed dependencies. Node itself
# is NOT bundled (it links a tree of shared libraries that does not relocate
# cleanly); app/memory/sidecar_process.py uses the system Node when present.
sidecar = ROOT / "sidecar"
for name in ("server.js", "package.json"):
    if (sidecar / name).is_file():
        datas.append((str(sidecar / name), "sidecar"))
if (sidecar / "node_modules").is_dir():
    datas.append((str(sidecar / "node_modules"), "sidecar/node_modules"))

# tree-sitter ships compiled grammars as package data; without this the AST
# skeleton engine silently produces nothing in a bundle.
datas += collect_data_files("tree_sitter_language_pack")
datas += collect_data_files("tree_sitter")

# Provider SDKs load bundled certs/JSON at runtime.
for pkg in ("anthropic", "openai", "google.genai", "certifi"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# ------------------------------------------------------------------ imports
hiddenimports = [
    "app.agents.claude_agent",
    "app.agents.openai_agent",
    "app.agents.gemini_agent",
    "app.agents.stub_agent",
]
# Grammar modules are imported by name at runtime, so PyInstaller can't see them.
hiddenimports += collect_submodules("tree_sitter_language_pack")

# Qt modules the app never touches — dropping them saves well over 100 MB.
excludes = [
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQml", "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender", "PyQt6.QtCharts", "PyQt6.QtDataVisualization",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtBluetooth",
    "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtLocation", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtWebSockets", "PyQt6.QtWebChannel",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtSql",
    "tkinter", "unittest", "pydoc_data", "pytest",
]

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

icon_file = None
if IS_MAC and (SPEC_DIR / "build" / "CombinePro.icns").is_file():
    icon_file = str(SPEC_DIR / "build" / "CombinePro.icns")
elif IS_WIN and (SPEC_DIR / "build" / "CombinePro.ico").is_file():
    icon_file = str(SPEC_DIR / "build" / "CombinePro.ico")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CombinePro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app: no terminal window
    disable_windowed_traceback=False,
    argv_emulation=IS_MAC,  # let macOS "open with" pass file arguments
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CombinePro",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="CombinePro.app",
        icon=icon_file,
        bundle_identifier="ai.combinepro.app",
        version="1.0.4",
        info_plist={
            "CFBundleName": "CombinePro",
            "CFBundleDisplayName": "CombinePro",
            "CFBundleShortVersionString": "1.0.4",
            "CFBundleVersion": "1.0.4",
            "NSHighResolutionCapable": True,
            # Qt draws its own dark chrome; keep macOS from re-tinting it.
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.developer-tools",
        },
    )
