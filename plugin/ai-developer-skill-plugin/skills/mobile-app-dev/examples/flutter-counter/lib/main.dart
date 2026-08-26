// flutter-counter/ -- minimal Flutter counter app demonstrating the
// threading_flutter.dart pattern with riverpod.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// MARK: - State

class CounterState {
  const CounterState({this.count = 0, this.isLoading = false});
  final int count;
  final bool isLoading;

  CounterState copyWith({int? count, bool? isLoading}) =>
      CounterState(
        count: count ?? this.count,
        isLoading: isLoading ?? this.isLoading,
      );
}

class CounterNotifier extends Notifier<CounterState> {
  @override
  CounterState build() => const CounterState();

  void increment() => state = state.copyWith(count: state.count + 1);
  void reset() => state = state.copyWith(count: 0);

  Future<void> loadFromNetwork() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      state = state.copyWith(
        count: 42,
        isLoading: false,
      );
    } catch (_) {
      state = state.copyWith(isLoading: false);
    }
  }
}

final counterProvider =
    NotifierProvider<CounterNotifier, CounterState>(CounterNotifier.new);

// MARK: - App entry

void main() {
  runApp(const ProviderScope(child: CounterApp()));
}

class CounterApp extends StatelessWidget {
  const CounterApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Counter',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.indigo),
      home: const CounterScreen(),
    );
  }
}

class CounterScreen extends ConsumerWidget {
  const CounterScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(counterProvider);
    final notifier = ref.read(counterProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Counter')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              '${state.count}',
              key: const Key('countText'),
              style: Theme.of(context).textTheme.displayLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                OutlinedButton(
                  onPressed: notifier.reset,
                  child: const Text('Reset'),
                ),
                const SizedBox(width: 12),
                FilledButton(
                  onPressed: notifier.increment,
                  child: const Text('Increment'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              onPressed: state.isLoading ? null : notifier.loadFromNetwork,
              icon: state.isLoading
                  ? const SizedBox(
                      width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.cloud_download),
              label: const Text('Load from network'),
            ),
          ],
        ),
      ),
    );
  }
}