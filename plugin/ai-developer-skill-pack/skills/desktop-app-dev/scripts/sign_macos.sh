#!/usr/bin/env bash
# sign_macos.sh -- codesign + notarize a macOS .app bundle.
#
# Usage:
#   bash scripts/sign_macos.sh path/to/MyApp.app "Developer ID Application: Example"
#   bash scripts/sign_macos.sh path/to/MyApp.app "Developer ID Application: Example" MyNotaryProfile
set -euo pipefail

APP_PATH="${1:?usage: sign_macos.sh <app> <identity> [notary-profile]}"
IDENTITY="${2:?usage: sign_macos.sh <app> <identity> [notary-profile]}"
NOTARY_PROFILE="${3:-}"

if [[ ! -d "$APP_PATH" ]]; then
    echo "error: .app bundle not found: $APP_PATH" >&2
    exit 1
fi

codesign --force --options runtime --timestamp --deep --sign "$IDENTITY" "$APP_PATH"
echo "==> Signed: $APP_PATH"

if [[ -n "$NOTARY_PROFILE" ]]; then
    xcrun notarytool submit "$APP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$APP_PATH"
    echo "==> Notarized + stapled: $APP_PATH"
fi
