# Flutter performance

Every Flutter app has three budgets to hit:

- **Cold start**: 1.5 s on a mid-tier device.
- **Frame rate**: 60 Hz (16.6 ms/frame) baseline; 120 Hz ProMotion
  (8.3 ms/frame) for newer iPhones.
- **Memory**: 150 MB resident for typical apps.

This doc shows the patterns that keep you inside those budgets.

---

## Widget rebuilds

### Use `const` everywhere it compiles

```dart
// Good -- constructed once, cached by the framework.
const Padding(
  padding: EdgeInsets.all(8),
  child: Text('Hello'),
)

// Bad -- new instance every rebuild.
Padding(
  padding: const EdgeInsets.all(8),
  child: const Text('Hello'),
)
```

A `const` constructor + `const` literal means the framework's
element tree shares one instance across all rebuilds.

### Extract sub-widgets

If a widget rebuilds often but only a small part of it depends on
the changing state, extract that part.

```dart
// Bad -- entire tree rebuilds on `count` change.
class Counter extends StatelessWidget {
  final int count;
  const Counter({super.key, required this.count});
  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text('$count'),                                  // changes
      const ExpensiveTree(),                           // also rebuilds!
      const Footer(),
    ]);
  }
}

// Good -- only the changing Text rebuilds.
class Counter extends StatelessWidget {
  final int count;
  const Counter({super.key, required this.count});
  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text('$count'),
      const ExpensiveTree(),
      const Footer(),
    ]);
  }
}
```

The framework already does this when sub-widgets are `const` (see
above), but if the expensive tree is non-`const`, extract it.

### `RepaintBoundary`

Wrap an expensive subtree that paints often but its layout does not
change:

```dart
RepaintBoundary(
  child: AnimatedWave(),
)
```

Now `AnimatedWave`'s painting does not invalidate the rest of the
frame.

## List rendering

### `ListView.builder` (always)

```dart
ListView.builder(
  itemCount: items.length,
  itemBuilder: (_, i) => ItemTile(items[i]),
)
```

`ListView()` (no `.builder`) eagerly builds all children. For 1000+
items, use `.builder` or `.separated`.

### `itemExtent` when known

```dart
ListView.builder(
  itemExtent: 72.0,  // known height per item
  itemCount: items.length,
  itemBuilder: (_, i) => ItemTile(items[i]),
)
```

`itemExtent` skips the layout pass for off-screen items. Big win
when all rows are the same height.

### `prototypeItem` for variable heights

```dart
ListView.builder(
  prototypeItem: const ItemTile(
    title: 'Prototype title that wraps',
    subtitle: 'Prototype subtitle',
  ),
  itemCount: items.length,
  itemBuilder: (_, i) => ItemTile(items[i]),
)
```

Framework measures the prototype once; subsequent items skip
measure.

## Images

### `cached_network_image`

```dart
CachedNetworkImage(
  imageUrl: url,
  placeholder: (_, __) => const Shimmer(),
  errorWidget: (_, __, ___) => const Icon(Icons.error),
  memCacheWidth: 1024,  // downsample; saves RAM
)
```

`memCacheWidth` / `memCacheHeight` downsample before caching.
Critical for lists with photos.

### Avoid `Image.network` in lists

`Image.network` is not cached. Use `cached_network_image` or
`flutter_cache_manager` directly.

## JSON parsing

### `compute()` for large payloads

```dart
final json = await api.fetchRaw();  // String
final parsed = await compute(parseJson, json);  // isolate
```

`compute()` runs in a background isolate. Use for JSON > 50 KB or
parsing > 50 ms.

## Image processing

Heavy image filters (blur, rotation, complex chains) should run
on an isolate via `compute()`. Never on the UI isolate.

## Animations

- Use `AnimatedContainer`, `AnimatedOpacity`, etc. for implicit
  animations (< 300 ms).
- For complex animations, use `AnimationController` + `Tween` +
  `AnimatedBuilder`.
- Use `flutter_animate` for declarative chains.
- Use `rive` for vector animations; `lottie` for AE exports.

## Startup

### Defer non-critical work

```dart
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const App());  // First frame painted ASAP.
  // After first frame:
  WidgetsBinding.instance.addPostFrameCallback((_) {
    _warmUpCaches();
    _initAnalytics();
  });
}
```

### Use deferred imports for rarely-used features

```dart
import 'package:myapp/features/settings/settings.dart' deferred as settings;

void openSettings() async {
  await settings.loadLibrary();
  Navigator.push(context, MaterialPageRoute(builder: (_) => settings.SettingsScreen()));
}
```

The settings code is downloaded on first use, not at startup.

### Profile startup

```bash
flutter run --profile --start-paused
# Open DevTools > Performance > Record
# Resume; stop at first frame.
```

The first-frame time should be < 1.5 s.

## Profiling with DevTools

### Performance tab

- "Frame timing" shows each frame's build / layout / paint / composite.
- "Flutter frames" chart highlights jank (frames > 16 ms).
- Click a frame to see what was being built.

### Memory tab

- "Profile" mode snapshots the heap.
- Look for unexpected growth across snapshots (leak indicator).

### Timeline tab (legacy)

- Show every event on a single timeline.
- Useful for correlating "this frame was slow because the
  ScrollController fired".

## Common jank causes

| Cause                                              | Fix |
|----------------------------------------------------|-----|
| `setState` in `build`                              | Move to event handler. |
| Sync IO in `build`                                 | Move to `initState` + async. |
| `print()` in release                               | Remove; prints have side effects. |
| Eager `ListView(children: [...])`                  | Use `ListView.builder`. |
| `Opacity` widget                                   | Use `AnimatedOpacity` or `FadeTransition`. |
| `Material` wrapping a `TextField`                  | Use `TextField` directly. |
| Long-running `compute()` blocking main isolate    | Use `Isolate.spawn` for long-lived work. |

## Build optimization

### Split-debug-info

```bash
flutter build apk --split-debug-info=build/symbols/
```

The APK no longer contains DWARF info. Upload `build/symbols/` to
Crashlytics / Sentry for post-symbolicate.

### Tree-shake icons

```bash
flutter build apk --tree-shake-icons
```

Strips unused Material / Cupertino icon fonts. Saves ~1 MB.

### App Bundle (Play Store)

```bash
flutter build appbundle --release
```

Generates `.aab` with split-per-ABI. Google Play generates per-ABI
APKs at install time.

## Common mistakes

- **Catching `BuildContext` after async gap without checking
  `context.mounted`.** Use `if (!context.mounted) return;` after
  every await.
- **Forgetting `await` on a Future in a constructor.** The
  constructor returns before the future resolves.
- **Allocating `Map` / `List` in `build`.** Hoist to a constant or
  pre-allocate in `initState`.
- **Not using `select` from Riverpod.** `ref.watch(provider)`
  rebuilds on any state change. `ref.watch(provider.select((s) =>
  s.field))` rebuilds only when `field` changes.