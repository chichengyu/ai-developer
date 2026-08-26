# watchos-starter

Minimal watchOS SwiftUI starter. Create an Xcode watchOS app with a
paired iOS host, then add these source files.

Key points:

- `@main` App entry with `WKApplicationDelegateAdaptor` when needed.
- Complications are separate targets and must stay lightweight.
- Use `WatchConnectivity` to sync data instead of fetching directly
  from the watch.
