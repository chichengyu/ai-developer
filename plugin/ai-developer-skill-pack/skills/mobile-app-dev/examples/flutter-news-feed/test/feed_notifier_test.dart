// test/feed_notifier_test.dart
import 'package:flutter_news_feed/main.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class StubApi implements FeedApi {
  StubApi(this.items);
  final List<FeedItem> items;

  @override
  Future<List<FeedItem>> fetchFeed() async => items;
}

void main() {
  test('FeedNotifier initial load returns stub items', () async {
    final container = ProviderContainer(overrides: [
      feedApiProvider.overrideWithValue(
        StubApi([
          FeedItem(id: '1', title: 'A', summary: 'a'),
          FeedItem(id: '2', title: 'B', summary: 'b'),
        ]),
      ),
    ]);
    addTearDown(container.dispose);

    final items = await container.read(feedProvider.future);
    expect(items, hasLength(2));
    expect(items.first.title, 'A');
  });

  test('FeedNotifier refresh updates state', () async {
    final container = ProviderContainer(overrides: [
      feedApiProvider.overrideWithValue(StubApi([FeedItem(id: '1', title: 'A', summary: 'a')])),
    ]);
    addTearDown(container.dispose);

    expect(await container.read(feedProvider.future), hasLength(1));

    container.read(feedProvider.notifier).refresh();
    await container.read(feedProvider.future);  // wait for refresh
    final state = container.read(feedProvider);
    expect(state, isA<AsyncData<List<FeedItem>>>());
  });
}