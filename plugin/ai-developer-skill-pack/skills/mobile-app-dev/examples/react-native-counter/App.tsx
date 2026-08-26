// react-native-counter/ -- minimal React Native counter demonstrating
// the threading_react_native.tsx pattern with zustand.

import React from 'react';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';

// MARK: - Model

type CounterState = {
  count: number;
  isLoading: boolean;
  increment: () => void;
  reset: () => void;
  loadFromNetwork: () => Promise<void>;
};

const useCounterStore = create<CounterState>((set) => ({
  count: 0,
  isLoading: false,
  increment: () => set((s) => ({ count: s.count + 1 })),
  reset: () => set({ count: 0 }),
  loadFromNetwork: async () => {
    set({ isLoading: true });
    try {
      await new Promise((r) => setTimeout(r, 300));
      set({ count: 42, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },
}));

// MARK: - App entry

export default function App(): React.JSX.Element {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Counter</Text>
      <Counter />
    </View>
  );
}

function Counter(): React.JSX.Element {
  const { count, isLoading, increment, reset, loadFromNetwork } =
    useCounterStore(
      useShallow((s) => ({
        count: s.count,
        isLoading: s.isLoading,
        increment: s.increment,
        reset: s.reset,
        loadFromNetwork: s.loadFromNetwork,
      })),
    );

  useEffect(() => {
    // Subscribe for debugging only; in production, wire to devtools.
  }, []);

  return (
    <View style={styles.counter}>
      <Text style={styles.value} accessibilityLabel={`Count: ${count}`}>
        {count}
      </Text>
      <View style={styles.row}>
        <Text style={styles.button} onPress={reset}>
          Reset
        </Text>
        <Text style={[styles.button, styles.buttonPrimary]} onPress={increment}>
          Increment
        </Text>
      </View>
      <Text
        style={[styles.button, styles.buttonTonal]}
        onPress={isLoading ? undefined : () => void loadFromNetwork()}>
        {isLoading ? <ActivityIndicator color="#fff" /> : 'Load from network'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    paddingTop: 80,
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
    marginBottom: 32,
  },
  counter: {
    alignItems: 'center',
    width: '100%',
  },
  value: {
    fontSize: 96,
    fontWeight: '700',
    marginBottom: 24,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 12,
  },
  button: {
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#777',
    fontSize: 16,
    overflow: 'hidden',
  },
  buttonPrimary: {
    backgroundColor: '#3b82f6',
    color: '#fff',
    borderColor: '#3b82f6',
  },
  buttonTonal: {
    backgroundColor: '#e0e7ff',
    color: '#1e3a8a',
    borderColor: '#c7d2fe',
  },
});