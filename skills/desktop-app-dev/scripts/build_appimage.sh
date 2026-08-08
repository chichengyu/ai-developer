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
#   ./build_appimage.sh [--download] ./myapp MyApp "My Company" "1.0.0" [x86_64|aarch64]
#
# Reference: https://appimage.org/

set -euo pipefail

BIN_PATH="${1:-}"
APP_NAME="${2:-MyApp}"
VENDOR="${3:-MyVendor}"
VERSION="${4:-0.1.0}"
TARGET_ARCH="${5:-$(uname -m)}"

# linuxdeploy download is opt-in; default is check-only.
DOWNLOAD_LINUXDEPLOY=0
if [[ "${1:-}" == "-d" || "${1:-}" == "--download" ]]; then
    DOWNLOAD_LINUXDEPLOY=1
    shift
    BIN_PATH="${1:-}"
    APP_NAME="${2:-MyApp}"
    VENDOR="${3:-MyVendor}"
    VERSION="${4:-0.1.0}"
    TARGET_ARCH="${5:-$(uname -m)}"
fi

if [[ -z "$BIN_PATH" || ! -x "$BIN_PATH" ]]; then
    echo "Usage: $0 [--download] <path-to-elf-binary> <AppName> <Vendor> <Version> [arch]" >&2
    exit 1
fi

case "$TARGET_ARCH" in
    x86_64|amd64) LINUXDEPLOY_ARCH="x86_64"; APPIMAGE_ARCH="x86_64" ;;
    aarch64|arm64) LINUXDEPLOY_ARCH="aarch64"; APPIMAGE_ARCH="aarch64" ;;
    *)
        echo "Unsupported target arch: $TARGET_ARCH (use x86_64 or aarch64)" >&2
        exit 1
        ;;
esac

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

# 2. Download linuxdeploy if absent (only with --download).
LINUXDEPLOY="./linuxdeploy-${LINUXDEPLOY_ARCH}.AppImage"
if [[ ! -x "$LINUXDEPLOY" ]]; then
    if [[ "$DOWNLOAD_LINUXDEPLOY" -ne 1 ]]; then
        echo "linuxdeploy not found. Re-run with --download, or download:" >&2
        echo "  wget https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${LINUXDEPLOY_ARCH}.AppImage -O $LINUXDEPLOY" >&2
        exit 1
    fi
    echo "==> Downloading linuxdeploy (${LINUXDEPLOY_ARCH})"
    wget -q "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${LINUXDEPLOY_ARCH}.AppImage" -O "$LINUXDEPLOY"
    chmod +x "$LINUXDEPLOY"
fi

# 3. Run linuxdeploy to build the AppImage.
echo "==> linuxdeploy --appdir=$APPDIR --output appimage"
ARCH="$APPIMAGE_ARCH" "$LINUXDEPLOY" --appdir="$APPDIR" --output appimage

# 4. Rename to a stable filename.
OUTPUT="${APP_NAME}-${VERSION}-${APPIMAGE_ARCH}.AppImage"
mv -f "${APP_NAME,,}-${APPIMAGE_ARCH}.AppImage" "$OUTPUT" 2>/dev/null || {
    for candidate in *.AppImage; do
        [[ -f "$candidate" && "$candidate" != linuxdeploy-* ]] || continue
        mv -f "$candidate" "$OUTPUT"
        break
    done
}
if [[ ! -f "$OUTPUT" ]]; then
    echo "error: linuxdeploy did not produce an AppImage" >&2
    exit 1
fi
echo "==> Built: $OUTPUT"
echo "Next: distribute. Users chmod +x and run; consider AppImageUpdate for auto-update."
