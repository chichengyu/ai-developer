#!/usr/bin/env bash
# build_dmg.sh -- Package a macOS .app bundle into a distributable DMG.
#
# Run on macOS with hdiutil available (built-in). Performs:
#   1. codesign --deep --force --options runtime --sign "Developer ID Application: ..."
#   2. codesign --verify --deep --strict --verbose=2 <App>.app
#   3. xcrun notarytool submit ... --wait  (Apple notarization)
#   4. xcrun stapler staple <App>.app
#   5. hdiutil create <App>.dmg -srcfolder <App>.app -ov -format UDZO
#
# Usage:
#   ./build_dmg.sh path/to/MyApp.app "Developer ID Application: ACME (TEAMID)"
#   ./build_dmg.sh path/to/MyApp.app ""   # skip signing (dev only)

set -euo pipefail

APP_PATH="${1:-}"
SIGN_ID="${2:-}"

if [[ -z "$APP_PATH" || ! -d "$APP_PATH" ]]; then
    echo "Usage: $0 <App.app> ['Developer ID Application: ...']" >&2
    exit 1
fi

APP_BASENAME=$(basename "$APP_PATH" .app)
WORKDIR="$(cd "$(dirname "$APP_PATH")" && pwd)"

# 1. Code-sign (if a Developer ID was supplied)
if [[ -n "$SIGN_ID" ]]; then
    echo "==> codesign --deep --force --options runtime --sign '$SIGN_ID' '$APP_PATH'"
    codesign --deep --force --options runtime --sign "$SIGN_ID" "$APP_PATH"
    echo "==> codesign --verify --deep --strict --verbose=2"
    codesign --verify --deep --strict --verbose=2 "$APP_PATH"
fi

# 2. Notarize (only if signed). Requires AC_NOTARY_PROFILE or KEYCHAIN_PROFILE_NAME.
if [[ -n "$SIGN_ID" && -n "${AC_NOTARY_PROFILE:-}" ]]; then
    echo "==> xcrun notarytool submit --wait"
    ZIP="$WORKDIR/${APP_BASENAME}.zip"
    ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP"
    xcrun notarytool submit "$ZIP" --keychain-profile "$AC_NOTARY_PROFILE" --wait
    rm -f "$ZIP"
    echo "==> xcrun stapler staple"
    xcrun stapler staple "$APP_PATH"
    xcrun stapler validate "$APP_PATH"
fi

# 3. Build the DMG
DMG_PATH="${WORKDIR}/${APP_BASENAME}.dmg"
echo "==> hdiutil create '$DMG_PATH'"
hdiutil create "$DMG_PATH" -srcfolder "$APP_PATH" -ov -format UDZO

echo ""
echo "==> Built: $DMG_PATH"
echo "Next: distribute via Sparkle feed, your website, or the Mac App Store."
