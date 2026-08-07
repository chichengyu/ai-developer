#!/usr/bin/env bash
# build_deb.sh -- Package a Linux ELF binary into a Debian .deb package.
#
# Run on a Debian/Ubuntu host. Requires dpkg-deb (built-in) and fakeroot.
#
# Usage:
#   ./build_deb.sh ./myapp myapp "1.0.0" "My Company" "optional description"

set -euo pipefail

BIN_PATH="${1:-}"
PKG_NAME="${2:-myapp}"
VERSION="${3:-0.1.0}"
VENDOR="${4:-Vendor}"
DESCRIPTION="${5:-Cross-platform desktop app}"

if [[ -z "$BIN_PATH" || ! -x "$BIN_PATH" ]]; then
    echo "Usage: $0 <elf-binary> <pkg-name> <version> <vendor> [description]" >&2
    exit 1
fi

STAGE="stage_${PKG_NAME}_${VERSION}"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/applications"

cp "$BIN_PATH" "$STAGE/usr/bin/${PKG_NAME}"
chmod 755 "$STAGE/usr/bin/${PKG_NAME}"

cat > "$STAGE/usr/share/applications/${PKG_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${PKG_NAME}
Exec=${PKG_NAME} %u
Icon=${PKG_NAME}
Categories=Utility;
Terminal=false
EOF

# Control file
SIZE=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ${VENDOR}
Description: ${DESCRIPTION}
Installed-Size: ${SIZE}
EOF

OUT="${PKG_NAME}_${VERSION}_amd64.deb"
echo "==> dpkg-deb --build $STAGE $OUT"
fakeroot dpkg-deb --build "$STAGE" "$OUT"
rm -rf "$STAGE"

echo "==> Built: $OUT"
echo "Next: optionally sign with debsigs; upload to a Debian repo, or distribute directly."