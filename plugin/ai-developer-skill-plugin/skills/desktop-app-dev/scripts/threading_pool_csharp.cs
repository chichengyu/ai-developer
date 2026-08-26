// C# bounded worker pool with aggregate progress, retry, and cancellation.
//
// Framework-agnostic: pass the owning UI's marshaller so every callback
// crosses to the UI thread through the right bridge.
//
//   var runner = new ParallelJobRunner<int, string>(
//       async (input, progress, ct) => await DownloadAsync(input, progress, ct),
//       maxConcurrency: 4,
//       maxAttempts: 3,
//       uiMarshaler: action => Dispatcher.InvokeAsync(action),   // WPF
//       onProgress: p => Status = $"{p.Percent:P0}",
//       onError: item => Log.Error(item.Error, "item {Index} failed", item.Index),
//       onDone: items => Finish(items));
//   await runner.StartAsync(urls);
//   // later: runner.Cancel();
//
// WinUI 3: uiMarshaler: action => DispatcherQueue.TryEnqueue(() => action())
// WinForms: uiMarshaler: action => Control.BeginInvoke(action)
// MAUI:    uiMarshaler: action => MainThread.BeginInvokeOnMainThread(action)

#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

public sealed record PoolItem<TInput, TResult>(
    int Index,
    TInput Input,
    TResult? Result,
    Exception? Error,
    int Attempts,
    string Status);

public sealed record PoolItemProgress(int Index, double Percent);

public sealed record PoolProgress(
    int Completed,
    int Total,
    int Succeeded,
    int Failed,
    double Percent);

public sealed class ParallelJobRunner<TInput, TResult>
    where TInput : notnull
{
    private readonly Func<TInput, IProgress<PoolItemProgress>, CancellationToken, Task<TResult>> _job;
    private readonly int _maxConcurrency;
    private readonly int _maxAttempts;
    private readonly TimeSpan _retryDelay;
    private readonly bool _failFast;
    private readonly Action<Action>? _ui;
    private readonly Action<PoolProgress>? _onProgress;
    private readonly Action<PoolItemProgress>? _onItemProgress;
    private readonly Action<PoolItem<TInput, TResult>>? _onError;
    private readonly Action<IReadOnlyList<PoolItem<TInput, TResult>>>? _onDone;
    private readonly Action? _onCancel;

    private CancellationTokenSource? _cts;

    public ParallelJobRunner(
        Func<TInput, IProgress<PoolItemProgress>, CancellationToken, Task<TResult>> job,
        int maxConcurrency = 4,
        int maxAttempts = 1,
        TimeSpan? retryDelay = null,
        bool failFast = false,
        Action<Action>? uiMarshaler = null,
        Action<PoolProgress>? onProgress = null,
        Action<PoolItemProgress>? onItemProgress = null,
        Action<PoolItem<TInput, TResult>>? onError = null,
        Action<IReadOnlyList<PoolItem<TInput, TResult>>>? onDone = null,
        Action? onCancel = null)
    {
        _job = job;
        _maxConcurrency = Math.Max(1, maxConcurrency);
        _maxAttempts = Math.Max(1, maxAttempts);
        _retryDelay = retryDelay ?? TimeSpan.FromMilliseconds(100);
        _failFast = failFast;
        _ui = uiMarshaler;
        _onProgress = onProgress;
        _onItemProgress = onItemProgress;
        _onError = onError;
        _onDone = onDone;
        _onCancel = onCancel;
    }

    public bool IsRunning => _cts != null;

    public void Cancel() => _cts?.Cancel();

    public async Task StartAsync(IReadOnlyList<TInput> inputs)
    {
        if (_cts != null)
            throw new InvalidOperationException("ParallelJobRunner is already running");

        var cts = new CancellationTokenSource();
        _cts = cts;
        var token = cts.Token;
        int total = inputs.Count;
        var results = new PoolItem<TInput, TResult>[total];
        int completed = 0;
        int succeeded = 0;
        int failed = 0;
        var itemProgress = new Progress<PoolItemProgress>(
            p => _ui?.Invoke(() => _onItemProgress?.Invoke(p)));

        void ReportAggregate()
        {
            int c = Volatile.Read(ref completed);
            int s = Volatile.Read(ref succeeded);
            int f = Volatile.Read(ref failed);
            var snapshot = new PoolProgress(
                c,
                total,
                s,
                f,
                total == 0 ? 1.0 : (double)c / total);
            if (_ui != null)
                _ui(() => _onProgress?.Invoke(snapshot));
            else
                _onProgress?.Invoke(snapshot);
        }

        try
        {
            if (total == 0)
            {
                _ui?.Invoke(() => _onDone?.Invoke(results));
                return;
            }

            var options = new ParallelOptions
            {
                MaxDegreeOfParallelism = _maxConcurrency,
                CancellationToken = token,
            };

            await Parallel.ForEachAsync(
                inputs.Select((input, index) => (input, index)),
                options,
                async (pair, ct) =>
                {
                    int index = pair.index;
                    var item = new PoolItem<TInput, TResult>(
                        index,
                        pair.input,
                        default,
                        null,
                        0,
                        "running");

                    for (int attempt = 1; attempt <= _maxAttempts; attempt++)
                    {
                        try
                        {
                            var result = await _job(pair.input, itemProgress, ct);
                            results[index] = item with
                            {
                                Result = result,
                                Attempts = attempt,
                                Status = "succeeded",
                            };
                            Interlocked.Increment(ref succeeded);
                            Interlocked.Increment(ref completed);
                            ReportAggregate();
                            return;
                        }
                        catch (OperationCanceledException) when (ct.IsCancellationRequested)
                        {
                            results[index] = item with
                            {
                                Error = new OperationCanceledException("cancelled", ct),
                                Attempts = attempt,
                                Status = "cancelled",
                            };
                            Interlocked.Increment(ref failed);
                            Interlocked.Increment(ref completed);
                            ReportAggregate();
                            return;
                        }
                        catch (Exception ex) when (attempt < _maxAttempts)
                        {
                            await Task.Delay(_retryDelay, ct);
                        }
                        catch (Exception ex)
                        {
                            results[index] = item with
                            {
                                Error = ex,
                                Attempts = attempt,
                                Status = "failed",
                            };
                            Interlocked.Increment(ref failed);
                            Interlocked.Increment(ref completed);
                            ReportAggregate();
                            _ui?.Invoke(() => _onError?.Invoke(results[index]));
                            if (_failFast)
                                cts.Cancel();
                            return;
                        }
                    }
                });

            _ui?.Invoke(() => _onDone?.Invoke(results));
        }
        catch (OperationCanceledException)
        {
            for (int i = 0; i < total; i++)
            {
                if (results[i] is null)
                {
                    results[i] = new PoolItem<TInput, TResult>(
                        i,
                        inputs[i],
                        default,
                        new OperationCanceledException("cancelled"),
                        0,
                        "cancelled");
                }
            }
            _ui?.Invoke(() => _onCancel?.Invoke());
            _ui?.Invoke(() => _onDone?.Invoke(results));
        }
        finally
        {
            _cts = null;
            cts.Dispose();
        }
    }
}
