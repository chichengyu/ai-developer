// App.tsx -- React Native + zustand news feed
import React, { useEffect } from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';

export type FeedItem = {
  id: string;
  title: string;
  summary: string;
};

type FeedStore = {
  items: FeedItem[];
  isLoading: boolean;
  error: string | null;
  load: () => Promise<void>;
  refresh: () => Promise<void>;
};

type FeedApi = {
  fetchFeed: () => Promise<FeedItem[]>;
};

export const liveFeedApi: FeedApi = {
  async fetchFeed() {
    await new Promise((r) => setTimeout(r, 200));
    return [
      { id: '1', title: 'First',  summary: 'Hello' },
      { id: '2', title: 'Second', summary: 'World' },
    ];
  },
};

export const useFeedStore = create<FeedStore>((set) => ({
  items: [],
  isLoading: false,
  error: null,
  load: async () => {
    set({ isLoading: true, error: null });
    try {
      const items = await liveFeedApi.fetchFeed();
      set({ items, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },
  refresh: async () => {
    set({ isLoading: true });
    try {
      const items = await liveFeedApi.fetchFeed();
      set({ items, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },
}));

export default function App(): React.JSX.Element {
  const { items, isLoading, error, load } = useFeedStore(
    useShallow((s) => ({
      items: s.items,
      isLoading: s.isLoading,
      error: s.error,
      load: s.load,
    })),
  );

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.title}>News Feed</Text>
      </View>
      {isLoading && items.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator accessibilityLabel="Loading" />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorTitle}>Couldn't load feed</Text>
          <Text style={styles.errorBody}>{error}</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.id}
          renderItem={({ item }) => (
            <View style={styles.tile} accessible>
              <Text style={styles.tileTitle}>{item.title}</Text>
              <Text style={styles.tileSummary}>{item.summary}</Text>
            </View>
          )}
          refreshControl={
            <RefreshControl
              refreshing={isLoading}
              onRefresh={() => void useFeedStore.getState().refresh()}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  header: { padding: 16, borderBottomWidth: 1, borderBottomColor: '#eee' },
  title: { fontSize: 24, fontWeight: '600' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 16 },
  errorTitle: { fontSize: 18, fontWeight: '600', marginBottom: 8 },
  errorBody: { color: '#666', textAlign: 'center' },
  tile: { padding: 16, borderBottomWidth: 1, borderBottomColor: '#eee' },
  tileTitle: { fontSize: 16, fontWeight: '600', marginBottom: 4 },
  tileSummary: { fontSize: 14, color: '#666' },
});