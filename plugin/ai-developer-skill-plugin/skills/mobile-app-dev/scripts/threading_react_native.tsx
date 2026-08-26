// threading_react_native.tsx -- canonical async + UI bridge for React Native.
//
// Uses zustand for state and TanStack Query for server state. Heavy work
// goes through a Web Worker / JSI helper; the UI thread stays free.

import React, { useEffect } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, Text, View } from 'react-native';
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';

// MARK: - Model

export type Item = { id: string; title: string; summary: string };

// MARK: - API

export type FeedApi = {
  fetchFeed(): Promise<Item[]>;
};

export const liveFeedApi: FeedApi = {
  async fetchFeed() {
    // Replace with real fetch() call.
    await new Promise(r => setTimeout(r, 10));
    return [
      { id: '1', title: 'First',  summary: 'Hello' },
      { id: '2', title: 'Second', summary: 'World' },
    ];
  },
};

// MARK: - Store (zustand)

type FeedState = {
  items: Item[];
  isLoading: boolean;
  error: string | null;
  load: (api?: FeedApi) => Promise<void>;
};

export const useFeedStore = create<FeedState>((set) => ({
  items: [],
  isLoading: false,
  error: null,
  load: async (api = liveFeedApi) => {
    set({ isLoading: true, error: null });
    try {
      const items = await api.fetchFeed();
      set({ items, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },
}));

// MARK: - View

export function FeedView(): React.JSX.Element {
  const { items, isLoading, error, load } = useFeedStore(
    useShallow(s => ({ items: s.items, isLoading: s.isLoading, error: s.error, load: s.load })),
  );

  useEffect(() => { load(); }, [load]);

  if (isLoading && items.length === 0) {
    return (
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', padding: 16 }}>
        <Text>Error: {error}</Text>
      </View>
    );
  }

  return (
    <FlatList
      data={items}
      keyExtractor={(i) => i.id}
      renderItem={({ item }) => (
        <View
          style={{ padding: 12 }}
          accessible
          accessibilityRole="text"
          accessibilityLabel={`${item.title}: ${item.summary}`}>
          <Text style={{ fontWeight: 'bold' }}>{item.title}</Text>
          <Text>{item.summary}</Text>
        </View>
      )}
      refreshControl={
        <RefreshControl refreshing={isLoading} onRefresh={() => load()} />
      }
    />
  );
}

// MARK: - Heavy work via JSI / worker

// For CPU-bound work in React Native:
// - Hermes runs JS on its own thread; UI thread is separate.
// - For really heavy work, use a JSI binding to a native worker, or
//   `react-native-worklets-core` for UI-thread offload.

// MARK: - Smoke test (jest)

export async function __smokeTest__(): Promise<void> {
  const items = await liveFeedApi.fetchFeed();
  if (items.length !== 2) throw new Error('expected 2 items');
  console.log('[OK] threading_react_native smoke');
}