#!/usr/bin/env bash
# Build CombinePro.app and a drag-to-install CombinePro.dmg.
#
#   ./installer/build_macos.sh
#
# Optional signing (needs an Apple Developer ID):
#   CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" ./installer/build_macos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_NAME="CombinePro"
VERSION="1.0.4"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
DIST="$ROOT/installer/dist"
WORK="$ROOT/installer/work"
DMG="$DIST/${APP_NAME}-${VERSION}-macOS.dmg"

echo "==> Checking toolchain"
[ -x "$PY" ] || { echo "No Python at $PY (set PYTHON=...)"; exit 1; }
"$PY" -c "import PyInstaller" 2>/dev/null || { echo "Installing PyInstaller"; "$PY" -m pip install -q pyinstaller; }

echo "==> Installing sidecar dependencies (bundled into the app)"
if command -v npm >/dev/null 2>&1; then
  (cd "$ROOT/sidecar" && npm install --omit=dev --silent)
else
  echo "!! npm not found — the sidecar will ship without node_modules."
  echo "   Delta Memory will be disabled in the built app."
fi

echo "==> Generating icons"
QT_QPA_PLATFORM=offscreen "$PY" "$ROOT/installer/make_icons.py"

echo "==> Building app bundle"
rm -rf "$DIST" "$WORK"
"$PY" -m PyInstaller "$ROOT/installer/${APP_NAME}.spec" \
  --noconfirm --distpath "$DIST" --workpath "$WORK"

APP="$DIST/${APP_NAME}.app"
[ -d "$APP" ] || { echo "Build failed: $APP missing"; exit 1; }

echo "==> Self-testing the bundle"
if ! QT_QPA_PLATFORM=offscreen "$APP/Contents/MacOS/${APP_NAME}" --selftest; then
  echo "!! Bundle self-test FAILED — not packaging a broken app."
  exit 1
fi

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  echo "==> Code signing"
  codesign --deep --force --options runtime --timestamp \
    --sign "$CODESIGN_IDENTITY" "$APP"
  codesign --verify --strict --verbose=2 "$APP"
else
  echo "==> Skipping code signing (set CODESIGN_IDENTITY to sign)"
  echo "   Unsigned apps trigger Gatekeeper; users must right-click > Open once."
fi

echo "==> Building DMG"
STAGE="$WORK/dmg"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install target
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  codesign --force --sign "$CODESIGN_IDENTITY" "$DMG"
fi

echo
echo "✓ App:  $APP"
echo "✓ DMG:  $DMG  ($(du -h "$DMG" | cut -f1))"
echo
echo "Install: open the DMG and drag CombinePro to Applications."
if [ -z "${CODESIGN_IDENTITY:-}" ]; then
  echo "Note: unsigned build — first launch needs right-click > Open."
fi
