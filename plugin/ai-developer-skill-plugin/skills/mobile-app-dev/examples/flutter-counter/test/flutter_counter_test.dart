// flutter_counter_test.dart -- run with `flutter test`.

import 'package:flutter/material.dart';
import 'package:flutter_counter/main.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Counter increments', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: CounterApp()));
    expect(find.text('0'), findsOneWidget);
    await tester.tap(find.text('Increment'));
    await tester.pump();
    expect(find.text('1'), findsOneWidget);
  });
}