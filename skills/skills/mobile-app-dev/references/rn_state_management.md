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