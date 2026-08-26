# React Native New Architecture (Fabric + TurboModules + JSI)

The New Architecture is RN 0.76+'s default. It removes the legacy
async bridge in favor of three coordinated systems:

- **JSI** (JavaScript Interface): C++ host objects directly exposed
  to JS. No serialization to JSON; calls are synchronous from JS.
- **TurboModules**: native modules that load on demand and expose
  type-safe APIs via codegen.
- **Fabric**: the new renderer. Synchronous layout, concurrent React,
  no more "JS bridge roundtrip per frame".

---

## Why it matters

The legacy architecture had three bottlenecks that the New
Architecture solves:

1. **Bridge serialization**: every native call serialized args +
   return as JSON, async across the bridge. TurboModules skip
   serialization via JSI.
2. **Eager native module loading**: legacy modules loaded at startup,
   even if never used. TurboModules load lazily.
3. **Async-only native calls**: legacy modules were async-only.
   JSI allows synchronous calls when appropriate (e.g., MMKV storage).

## TurboModule spec (codegen-driven)

### 1. Define the TS spec

```typescript
// src/native/NativeMyModule.ts
import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export interface Spec extends TurboModule {
  // Synchronous JSI call -- no Promise return.
  getValueSync(key: string): string;
  // Async call -- returns Promise.
  setValue(key: string, value: string): Promise<void>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('MyModule');
```

### 2. Codegen runs at build time

`react-native codegen` reads the spec and generates:
- `ios/NativeMyModule.h` (Obj-C interface)
- `android/NativeMyModule.java` (Kotlin/Java interface)
- `src/native/NativeMyModule.ts` (typed wrapper)

### 3. Implement on iOS (Swift)

```swift
// ios/MyModule.swift
import Foundation

@objc(MyModule)
class MyModule: NSObject {
  @objc func getValueSync(_ key: String) -> String {
    return UserDefaults.standard.string(forKey: key) ?? ""
  }

  @objc func setValue(_ key: String, value: String, resolver resolve: @escaping RCTPromiseResolveBlock, rejecter reject: @escaping RCTPromiseRejectBlock) {
    UserDefaults.standard.set(value, forKey: key)
    resolve(nil)
  }

  @objc static func requiresMainQueueSetup() -> Bool {
    return false
  }
}
```

### 4. Implement on Android (Kotlin)

```kotlin
// android/app/src/main/java/com/example/myapp/MyModule.kt
package com.example.myapp

import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.module.annotations.ReactModule

@ReactModule(name = "MyModule")
class MyModule(reactContext: ReactApplicationContext) :
    NativeMyModuleSpec(reactContext) {

  override fun getName() = "MyModule"

  override fun getValueSync(key: String): String {
    return reactApplicationContext
        .getSharedPreferences("myapp", Context.MODE_PRIVATE)
        .getString(key, "") ?: ""
  }

  override fun setValue(key: String, value: String, promise: Promise) {
    reactApplicationContext
        .getSharedPreferences("myapp", Context.MODE_PRIVATE)
        .edit()
        .putString(key, value)
        .apply()
    promise.resolve(null)
  }
}
```

### 5. Wire into the app

```typescript
import MyModule from './native/NativeMyModule';

MyModule.setValue('lastSync', new Date().toISOString());
const last = MyModule.getValueSync('lastSync');
```

---

## Fabric

Fabric is the renderer; you mostly don't interact with it directly.
What you do notice:

- **Concurrent React**: `startTransition`, `useDeferredValue`.
- **Synchronous layout**: no "UI thread jumped ahead" race when
  measuring scrollable content.
- **Better TypeScript**: many props that were `any` are now typed.

```typescript
import { useDeferredValue, startTransition } from 'react';

function SearchScreen() {
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);

  // The list re-renders only when deferredQuery changes, not on
  // every keystroke.
  return (
    <>
      <TextInput value={query} onChangeText={setQuery} />
      <SearchResults query={deferredQuery} />
    </>
  );
}
```

---

## JSI

JSI exposes C++ objects directly to JS. Libraries that benefit
most:

- **react-native-mmkv**: sync storage, ~30x faster than AsyncStorage.
- **react-native-reanimated 3**: worklets run on UI thread via JSI.
- **react-native-skia**: GPU-accelerated drawing.
- **react-native-vision-camera**: frame processors on a worker thread.

```typescript
import { MMKV } from 'react-native-mmkv';

const storage = new MMKV();

// Synchronous -- no await needed!
storage.set('user.name', 'Ada');
const name = storage.getString('user.name') ?? '';
```

---

## Migration tips

### From legacy to New Architecture

1. Bump RN to 0.76+.
2. Enable in `android/gradle.properties`:
   ```
   newArchEnabled=true
   ```
3. Enable in `ios/Podfile`:
   ```ruby
   :fabric_enabled => true
   ```
4. Audit libraries for compatibility:
   - Most maintained libs are New Arch compatible by 0.76.
   - Older libs may need community forks.
5. Migrate custom native modules:
   - Convert to TurboModule spec + codegen.
   - Test on both platforms; JSI synchronous calls can deadlock if
     called from JS thread that holds a lock.
6. Use the new dev menu: "Toggle Fabric / TurboModules" diagnostics.

### Common blockers

- **Library not yet New Arch compatible.** Check the library's
  README for "New Architecture" or "Fabric" mention. If absent, use
  the last legacy version or find an alternative.
- **Synchronous calls hanging.** A sync JSI call from JS thread
  that needs to wait on UI thread deadlocks. Wrap in
  `runOnJS` / `runOnUI` (Reanimated).
- **Codegen errors.** Specs must be exact; mismatched types between
  TS and native cause build failures. Run `npx react-native
  codegen-ios` / `codegen-android` to see exact errors.

---

## Performance comparison

| Operation                      | Legacy bridge | New Architecture (JSI) |
|--------------------------------|---------------|--------------------------|
| `setItem` (1 KB string)        | ~5 ms (async) | ~0.1 ms (sync)           |
| Read 100 items from MMKV       | ~50 ms        | ~2 ms                    |
| Call native module              | 1-2 ms        | 0.01-0.1 ms              |
| Animation frame (Reanimated 2) | 16 ms (async) | 8 ms (UI thread)         |
| Hermes cold start (RN 0.74)    | ~700 ms       | ~500 ms                  |

The win is biggest for tight loops and synchronous workflows (storage,
animation). The win is smaller for one-shot async calls.

## Debugging

- **Flipper** is deprecated for New Arch. Use **React Native DevTools**
  (Chrome DevTools replacement).
- **React Profiler** works as before.
- **JSI debugging**: `global.__jsiExecutorDescription` in the
  console.
- **TurboModule logging**: increase native log verbosity via
  `RCTSetLogThreshold` in iOS, `ReactNativeLogger` in Android.

## Anti-patterns

- **Mixing legacy and new architecture.** Pick one; do not run
  half-Fabric.
- **Calling TurboModule sync methods that do IO.** The JS thread
  blocks; UI freezes. Make them async.
- **Reimplementing TurboModule patterns manually.** Use codegen.
- **Bypassing Fabric with direct native views.** Add the view via
  ShadowNode spec, not by reaching into the renderer.