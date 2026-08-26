// Flutter Desktop background work with cancellation + progress + safe UI bridge.
//
// The long job runs in a background isolate. Messages cross back through a
// ReceivePort, which is delivered on the UI isolate's event loop, so
// callbacks can safely update widgets.
//
// Usage:
//   final job = await BackgroundJob.start(
//       total: 100,
//       onProgress: (p) => setState(() => progress = p),
//       onDone: (result) => setState(() => status = "done: $result"),
//       onError: (error) => setState(() => status = "error: $error"),
//       onCancel: () => setState(() => status = "cancelled"));
//   // later: job.cancel(); then job.dispose();

import 'dart:async';
import 'dart:isolate';

class BackgroundJob {
  BackgroundJob._(this._port, this._isolate, this._cancelPort);

  final ReceivePort _port;
  final Isolate _isolate;
  final SendPort _cancelPort;

  static Future<BackgroundJob> start(
    int total, {
    void Function(double progress)? onProgress,
    void Function(Object? result)? onDone,
    void Function(Object error)? onError,
    void Function()? onCancel,
  }) async {
    final port = ReceivePort();
    final cancelPort = ReceivePort();
    final isolate = await Isolate.spawn(_entry, {
      'send': port.sendPort,
      'cancel': cancelPort.sendPort,
      'total': total,
    });
    final job = BackgroundJob._(port, isolate, cancelPort.sendPort);

    port.listen((message) {
      final map = Map<dynamic, dynamic>.from(message as Map);
      switch (map['type']) {
        case 'progress':
          onProgress?.call((map['progress'] as num).toDouble());
          break;
        case 'done':
          onDone?.call(map['result']);
          break;
        case 'error':
          onError?.call(map['error'] ?? 'unknown job error');
          break;
        case 'cancelled':
          onCancel?.call();
          break;
      }
    });

    return job;
  }

  void cancel() => _cancelPort.send(null);

  Future<void> dispose() async {
    _port.close();
    _isolate.kill(priority: Isolate.immediate);
  }

  static Future<void> _entry(Map<String, Object?> args) async {
    final send = args['send']! as SendPort;
    final cancel = args['cancel']! as SendPort;
    final total = args['total']! as int;
    var cancelled = false;

    cancel.listen((_) {
      cancelled = true;
    });

    try {
      for (var step = 1; step <= total; step++) {
        if (cancelled) {
          send.send({'type': 'cancelled'});
          return;
        }
        send.send({'type': 'progress', 'progress': step / total});
        await Future<void>.delayed(const Duration(milliseconds: 50));
      }
      send.send({'type': 'done', 'result': total});
    } catch (error) {
      send.send({'type': 'error', 'error': error.toString()});
    }
  }
}
