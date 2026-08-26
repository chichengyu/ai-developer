# React Native deep dive (New Architecture + state management)

Read this when Step 1.5 has picked React Native and you need
platform-specific patterns. For the workflow + framework comparison,
see the main SKILL.md.

This file consolidates two sub-topics:

1. New Architecture (Fabric + TurboModules + JSI).
2. State management (zustand / Redux Toolkit / Jotai).

---
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

---

# React Native state management

Four viable options for production RN apps: zustand, Redux Toolkit,
Jotai, MobX. Plus the always-present React Context + useReducer for
the smallest apps.

---

## Zustand (recommended for most apps)

### Why zustand

- Tiny (~1 KB gzipped).
- No `<Provider>` needed; create store once, import anywhere.
- Hooks-first; works with `useShallow` to prevent re-render thrash.
- Easy to add devtools (`zustand/middleware`).

### Code

```typescript
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';

type FeedItem = { id: string; title: string; summary: string };

type FeedStore = {
  items: FeedItem[];
  isLoading: boolean;
  error: string | null;
  load: () => Promise<void>;
  refresh: () => Promise<void>;
};

export const useFeedStore = create<FeedStore>((set) => ({
  items: [],
  isLoading: false,
  error: null,
  load: async () => {
    set({ isLoading: true, error: null });
    try {
      const items = await api.fetchFeed();
      set({ items, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },
  refresh: async () => {
    set({ isLoading: true });
    try {
      const items = await api.fetchFeed();
      set({ items, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },
}));

export function FeedScreen() {
  const { items, isLoading, error, load } = useFeedStore(
    useShallow((s) => ({
      items: s.items,
      isLoading: s.isLoading,
      error: s.error,
      load: s.load,
    })),
  );

  useEffect(() => { load(); }, [load]);

  if (isLoading && items.length === 0) return <ActivityIndicator />;
  if (error) return <ErrorView message={error} />;

  return (
    <FlatList
      data={items}
      keyExtractor={(i) => i.id}
      renderItem={({ item }) => <ItemTile item={item} />}
      refreshControl={
        <RefreshControl
          refreshing={isLoading}
          onRefresh={() => useFeedStore.getState().refresh()}
        />
      }
    />
  );
}
```

### Patterns

- **`useShallow`**: when selecting multiple fields; prevents re-render
  when an unrelated field changes.
- **`useFeedStore.getState()`**: access state outside React (e.g.,
  in callbacks, event handlers).
- **Selectors for derived state**:
  ```typescript
  const itemCount = useFeedStore((s) => s.items.length);
  ```

### Tests

```typescript
import { useFeedStore } from './feedStore';

beforeEach(() => useFeedStore.setState({ items: [], isLoading: false }));

test('load updates items', async () => {
  await useFeedStore.getState().load();
  expect(useFeedStore.getState().items.length).toBeGreaterThan(0);
});
```

## Redux Toolkit

### When to pick

- Large app with multiple devs; explicit patterns help.
- Time-travel debugging needed in dev.
- Existing Redux code to maintain.
- Strict action / state types required.

### Code

```typescript
import { createSlice, configureStore, PayloadAction } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

type Item = { id: string; title: string; summary: string };

type FeedState = {
  items: Item[];
  isLoading: boolean;
  error: string | null;
};

const initialState: FeedState = { items: [], isLoading: false, error: null };

const feedSlice = createSlice({
  name: 'feed',
  initialState,
  reducers: {
    loadStart(state) {
      state.isLoading = true;
      state.error = null;
    },
    loadSuccess(state, action: PayloadAction<Item[]>) {
      state.items = action.payload;
      state.isLoading = false;
    },
    loadFailure(state, action: PayloadAction<string>) {
      state.error = action.payload;
      state.isLoading = false;
    },
  },
});

export const { loadStart, loadSuccess, loadFailure } = feedSlice.actions;
export const feedReducer = feedSlice.reducer;

export const store = configureStore({ reducer: { feed: feedReducer } });

// Typed hooks (avoid manual RootState typing in every component).
type RootState = ReturnType<typeof store.getState>;
type AppDispatch = typeof store.dispatch;
export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
```

### Component

```typescript
export function FeedScreen() {
  const dispatch = useAppDispatch();
  const { items, isLoading, error } = useAppSelector((s) => s.feed);

  useEffect(() => {
    dispatch(loadStart());
    api.fetchFeed().then(
      (items) => dispatch(loadSuccess(items)),
      (e) => dispatch(loadFailure(String(e))),
    );
  }, [dispatch]);

  if (isLoading) return <ActivityIndicator />;
  if (error) return <ErrorView message={error} />;

  return <FlatList data={items} ... />;
}
```

## Jotai

### When to pick

- Fine-grained reactivity; only the components reading changed atoms
  re-render.
- Less boilerplate than Redux.
- Async atoms (Suspense-friendly).

### Code

```typescript
import { atom, useAtom } from 'jotai';

const itemsAtom = atom<Item[]>([]);
const isLoadingAtom = atom(false);
const errorAtom = atom<string | null>(null);

const loadAtom = atom(null, async (_get, set) => {
  set(isLoadingAtom, true);
  set(errorAtom, null);
  try {
    const items = await api.fetchFeed();
    set(itemsAtom, items);
  } catch (e) {
    set(errorAtom, String(e));
  } finally {
    set(isLoadingAtom, false);
  }
});

export function FeedScreen() {
  const [items] = useAtom(itemsAtom);
  const [isLoading] = useAtom(isLoadingAtom);
  const [, load] = useAtom(loadAtom);

  useEffect(() => { load(); }, [load]);
  // ...
}
```

## Context + useReducer (for small apps only)

```typescript
type State = { items: Item[]; isLoading: boolean };
type Action = { type: 'loadStart' } | { type: 'loadSuccess'; items: Item[] };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'loadStart': return { ...state, isLoading: true };
    case 'loadSuccess': return { items: action.items, isLoading: false };
  }
}

const FeedContext = createContext<{
  state: State;
  dispatch: Dispatch<Action>;
} | null>(null);

export function FeedProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(reducer, { items: [], isLoading: false });
  return <FeedContext.Provider value={{ state, dispatch }}>{children}</FeedContext.Provider>;
}

export function useFeed() {
  const ctx = useContext(FeedContext);
  if (!ctx) throw new Error('useFeed must be inside FeedProvider');
  return ctx;
}
```

Only use this for apps with < 5 state slices and < 10 screens.

## Server state with React Query

Server state is best separated from UI state. Use `@tanstack/react-query`:

```typescript
import { useQuery } from '@tanstack/react-query';

export function useFeed() {
  return useQuery({
    queryKey: ['feed'],
    queryFn: () => api.fetchFeed(),
    staleTime: 30_000,
  });
}

// In component:
const { data, isLoading, error, refetch } = useFeed();
```

This replaces ~50% of your Redux state -- queries own the data,
mutations own the writes, zustand/Redux owns UI state (selected tab,
modal open, etc.).

## Anti-patterns

- **One global store for everything.** Each concern in its own store
  / slice.
- **Multiple sources of truth.** UI state in Redux + server state in
  zustand for the same entity? Pick one.
- **`useEffect` to sync props to state.** Compute derived values
  inline; use `useMemo` for expensive ones.
- **`setState` inside `render`.** Use `useEffect` or compute inline.
- **Mixing 4 state libraries.** Pick one.
- **Storing functions in state for re-render optimization.** Use
  `useCallback`.