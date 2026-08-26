// lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  runApp(const ProviderScope(child: NewsFeedApp()));
}

class NewsFeedApp extends StatelessWidget {
  const NewsFeedApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'News Feed',
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.indigo,
      ),
      home: const FeedScreen(),
    );
  }
}

@immutable
class FeedItem {
  const FeedItem({
    required this.id,
    required this.title,
    required this.summary,
  });
  final String id;
  final String title;
  final String summary;

  factory FeedItem.fromJson(Map<String, dynamic> json) => FeedItem(
        id: json['id'] as String,
        title: json['title'] as String,
        summary: json['summary'] as String,
      );
}

abstract class FeedApi {
  Future<List<FeedItem>> fetchFeed();
}

class LiveFeedApi implements FeedApi {
  @override
  Future<List<FeedItem>> fetchFeed() async {
    // Replace with real HTTP call (Dio / http / Retrofit).
    await Future<void>.delayed(const Duration(milliseconds: 200));
    return const [
      FeedItem(id: '1', title: 'First',  summary: 'Hello'),
      FeedItem(id: '2', title: 'Second', summary: 'World'),
    ];
  }
}

final feedApiProvider = Provider<FeedApi>((ref) => LiveFeedApi());

class FeedNotifier extends AsyncNotifier<List<FeedItem>> {
  @override
  Future<List<FeedItem>> build() async {
    return ref.read(feedApiProvider).fetchFeed();
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(feedApiProvider).fetchFeed(),
    );
  }
}

final feedProvider =
    AsyncNotifierProvider<FeedNotifier, List<FeedItem>>(FeedNotifier.new);

class FeedScreen extends ConsumerWidget {
  const FeedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncFeed = ref.watch(feedProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('News Feed'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: () => ref.read(feedProvider.notifier).refresh(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(feedProvider.notifier).refresh(),
        child: asyncFeed.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, st) => Center(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Error: $e'),
            ),
          ),
          data: (items) => ListView.builder(
            itemCount: items.length,
            itemBuilder: (_, i) => _FeedTile(items[i]),
          ),
        ),
      ),
    );
  }
}

class _FeedTile extends StatelessWidget {
  const _FeedTile(this.item);
  final FeedItem item;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(item.title),
      subtitle: Text(item.summary),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
    );
  }
}