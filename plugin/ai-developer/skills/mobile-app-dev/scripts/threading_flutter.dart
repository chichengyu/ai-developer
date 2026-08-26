// threading_flutter.dart -- canonical async + UI bridge for Flutter.
//
// Use riverpod + AsyncNotifier; the @riverpod codegen provides typed
// providers and the AsyncValue<T> wrapper handles loading / data / error.

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// A simple item model.
@immutable
class Item {
  const Item({required this.id, required this.title, required this.summary});
  final String id;
  final String title;
  final String summary;
}

/// API surface -- replace with Dio / http / your real client.
abstract class FeedApi {
  Future<List<Item>> fetchFeed();
}

class LiveFeedApi implements FeedApi {
  @override
  Future<List<Item>> fetchFeed() async {
    await Future<void>.delayed(const Duration(milliseconds: 10));
    return const [
      Item(id: '1', title: 'First', summary: 'Hello'),
      Item(id: '2', title: 'Second', summary: 'World'),
    ];
  }
}

final _feedApiProvider = Provider<FeedApi>((ref) => LiveFeedApi());

/// AsyncNotifier exposes loading / data / error uniformly.
class FeedNotifier extends AsyncNotifier<List<Item>> {
  @override
  Future<List<Item>> build() async {
    return ref.read(_feedApiProvider).fetchFeed();
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(_feedApiProvider).fetchFeed());
  }
}

final feedProvider = AsyncNotifierProvider<FeedNotifier, List<Item>>(FeedNotifier.new);

/// View (ConsumerWidget watches the provider).
class FeedView extends ConsumerWidget {
  const FeedView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncFeed = ref.watch(feedProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Feed'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(feedProvider.notifier).refresh(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(feedProvider.notifier).refresh(),
        child: asyncFeed.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, st) => Center(child: Text('Error: $e')),
          data: (items) => ListView.builder(
            itemCount: items.length,
            itemBuilder: (_, i) => ListTile(
              title: Text(items[i].title),
              subtitle: Text(items[i].summary),
            ),
          ),
        ),
      ),
    );
  }
}

/// CPU-bound work runs on a separate isolate via `compute`.
Future<int> countOccurrences(String haystack, String needle) async {
  return compute(_countOccurrencesIsolate, _CountArgs(haystack, needle));
}

class _CountArgs {
  const _CountArgs(this.haystack, this.needle);
  final String haystack;
  final String needle;
}

int _countOccurrencesIsolate(_CountArgs args) {
  if (args.needle.isEmpty) return 0;
  var count = 0;
  var index = 0;
  while (true) {
    final found = args.haystack.indexOf(args.needle, index);
    if (found < 0) break;
    count++;
    index = found + args.needle.length;
  }
  return count;
}

/// Smoke test (run with `dart test`).
Future<void> main() async {
  // Verify compute works:
  final n = await countOccurrences('hello world hello', 'hello');
  assert(n == 2, 'expected 2, got \$n');
  // Verify API stub works:
  final api = LiveFeedApi();
  final items = await api.fetchFeed();
  assert(items.length == 2);
  print('[OK] threading_flutter smoke');
}