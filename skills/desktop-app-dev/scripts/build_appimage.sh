#!/usr/bin/env bash
# build_appimage.sh -- Package a Linux ELF binary into an AppImage.
#
# AppImage is a single-file portable Linux binary that runs on most
# distros without installation. This script downloads linuxdeploy
# and uses it to bundle the binary into a working AppImage.
#
# Run on Linux. Requires wget, file, and the ELF binary to bundle.
#
# Usage:
#   ./build_appimage.sh ./myapp MyApp "My Company" "1.0.0"
#
# Reference: https://appimage.org/

set -euo pipefail

BIN_PATH="${1:-}"
APP_NAME="${2:-MyApp}"
VENDOR="${3:-MyVendor}"
VERSION="${4:-0.1.0}"

if [[ -z "$BIN_PATH" || ! -x "$BIN_PATH" ]]; then
    echo "Usage: $0 <path-to-elf-binary> <AppName> <Vendor> <Version>" >&2
    exit 1
fi

# 1. Stage the AppDir layout expected by linuxdeploy.
APPDIR="AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BIN_PATH" "$APPDIR/usr/bin/${APP_NAME,,}"
chmod +x "$APPDIR/usr/bin/${APP_NAME,,}"

cat > "$APPDIR/usr/share/applications/${APP_NAME,,}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=${APP_NAME,,} %u
Icon=${APP_NAME,,}
Categories=Utility;
Terminal=false
EOF

# Caller must supply a 256x256 PNG named ${APP_NAME,,}.png in cwd.
if [[ -f "${APP_NAME,,}.png" ]]; then
    cp "${APP_NAME,,}.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
fi

# 2. Download linuxdeploy if absent.
LINUXDEPLOY="./linuxdeploy-x86_64.AppImage"
if [[ ! -x "$LINUXDEPLOY" ]]; then
    echo "==> Downloading linuxdeploy"
    wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage -O "$LINUXDEPLOY"
    chmod +x "$LINUXDEPLOY"
fi

# 3. Run linuxdeploy to build the AppImage.
echo "==> linuxdeploy --appdir=$APPDIR --output appimage"
ARCH=x86_64 "$LINUXDEPLOY" --appdir="$APPDIR" --output appimage

# 4. Rename to a stable filename.
OUTPUT="${APP_NAME}-${VERSION}-x86_64.AppImage"
mv -f "${APP_NAME,,}-x86_64.AppImage" "$OUTPUT" 2>/dev/null || mv -f *.AppImage "$OUTPUT"
echo "==> Built: $OUTPUT"
echo "Next: distribute. Users chmod +x and run; consider AppImageUpdate for auto-update."