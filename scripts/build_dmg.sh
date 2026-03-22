#!/bin/bash
set -euo pipefail

APP_NAME="DiskAnalyzer"
VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"
DMG_DIR="$BUILD_DIR/dmg"
DMG_PATH="$DIST_DIR/${APP_NAME}-${VERSION}.dmg"

echo "==> Building ${APP_NAME} v${VERSION}"

# Clean previous builds
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$DMG_DIR"

# Check dependencies
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Install pyinstaller if needed
if ! python3 -m PyInstaller --version &>/dev/null; then
    echo "==> Installing PyInstaller..."
    pip3 install pyinstaller
fi

# Build the .app bundle with PyInstaller
echo "==> Running PyInstaller..."
ICON_FILE="$PROJECT_DIR/resources/icons/AppIcon.icns"

python3 -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --icon "$ICON_FILE" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pyinstaller" \
    --specpath "$BUILD_DIR" \
    --add-data "$PROJECT_DIR/disk_analyzer:disk_analyzer" \
    "$PROJECT_DIR/main.py"

APP_BUNDLE="$DIST_DIR/${APP_NAME}.app"
if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: .app bundle not found at $APP_BUNDLE"
    exit 1
fi

echo "==> Creating DMG..."

# Prepare DMG staging area
mkdir -p "$DMG_DIR"
cp -R "$APP_BUNDLE" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

# Create DMG
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_DIR" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "$DMG_PATH"

# Clean up staging
rm -rf "$DMG_DIR"

echo ""
echo "==> Done! DMG created at:"
echo "    $DMG_PATH"
echo ""
echo "    Size: $(du -h "$DMG_PATH" | cut -f1)"
