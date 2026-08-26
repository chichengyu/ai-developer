# AppImage auto-update (AppImageUpdate + zsync)

AppImage has a built-in auto-update story via `zsync` (binary delta
downloads) and the `AppImageUpdate` tool. The flow:

1. Build your `MyApp-1.0.0-x86_64.AppImage` (use `scripts/build_appimage.sh`).
2. Upload it to a static HTTPS server (S3, GitHub Releases, your own
   nginx, etc.). The URL must end in `.AppImage` for zsync to find it.
3. On subsequent builds, upload `MyApp-1.0.1-x86_64.AppImage` to the same
   location; AppImageUpdate will compute and apply the delta.

## Embed the update information

Embed `UPDATE_INFORMATION` into the AppImage at build time:

```bash
# Either: gh-releases-zsync|owner|repo|MyApp|latest|MyApp-*x86_64.AppImage
# Or:    zsync|https://updates.example.com/myapp/MyApp-latest-x86_64.AppImage
./linuxdeploy-x86_64.AppImage \
  --appdir=AppDir \
  --output appimage \
  --custom-apprun=AppRun \
  -e myapp \
  --updateinformation "zsync|https://updates.example.com/myapp/MyApp-latest-x86_64.AppImage"
```

## Wire into your app

Call AppImageUpdate when the user requests "Check for Updates...":

```bash
APPIMAGE_LAUNCHED_FROM_PATH=$(echo "$APPIMAGE" | sed 's|/MyApp.*||')
MyApp-x86_64.AppImage --appimage-updateinformation
# Prints the URL; if not set, no auto-update.
```

Or programmatically, spawn `appimageupdatetool` from your app:

```cpp
#include <cstdlib>
int main() {
    // Update the running AppImage in place.
    return system("appimageupdatetool --force-update");
}
```

## Build tooling

| Tool            | Install                                            |
|-----------------|----------------------------------------------------|
| appimagetool    | `wget https://github.com/AppImageCommunity/AppImageKit/releases` |
| AppImageUpdate  | `wget https://github.com/AppImageCommunity/AppImageUpdate/releases` |
| zsync           | `apt install zsync`                                |

## When NOT to use AppImageUpdate

- Distributing via Snap / Flatpak -- they have their own update mechanism.
- Distributing via deb / rpm -- the system package manager updates the app.
- Air-gapped / locked-down corporate environments -- ship a new DMG /
  MSI; do not auto-update from the internet.

See `references/restricted_network_playbook.md` for the offline-equivalent
distribution patterns.