#nullable enable
// Avalonia background work with cancellation + progress + safe UI bridge.
//
// Avalonia's UI is owned by `Dispatcher.UIThread`. `Post` is asynchronous
// and safe to call from any worker thread; the worker itself never touches
// controls.
//
// Usage:
//   var worker = new BackgroundTask(
//       job: (token, progress) => LongJob(token, progress),
//       onProgress: p => ProgressBar.Value = Convert.ToDouble(p),
//       onDone: r => Status = $"done: {r}",
//       onError: e => Status = $"error: {e.Message}",
//       onCancel: () => Status = "cancelled");
//   worker.Start();
//   // later: worker.Cancel();

using System;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Threading;

public sealed class BackgroundTask
{
    private readonly Func<CancellationToken, IProgress<object>, object> _job;
    private readonly Action<object>? _onDone;
    private readonly Action<Exception>? _onError;
    private readonly Action<object>? _onProgress;
    private readonly Action? _onCancel;
    private CancellationTokenSource? _cts;

    public BackgroundTask(
        Func<CancellationToken, IProgress<object>, object> job,
        Action<object>? onDone = null,
        Action<Exception>? onError = null,
        Action<object>? onProgress = null,
        Action? onCancel = null)
    {
        _job = job;
        _onDone = onDone;
        _onError = onError;
        _onProgress = onProgress;
        _onCancel = onCancel;
    }

    public void Start()
    {
        if (_cts != null) throw new InvalidOperationException("already running");
        var dispatcher = Dispatcher.UIThread;
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        var progress = new Progress<object>(p => dispatcher.Post(() => _onProgress?.Invoke(p)));

        Task.Run(() =>
        {
            try
            {
                var result = _job(token, progress);
                dispatcher.Post(() => _onDone?.Invoke(result));
            }
            catch (OperationCanceledException)
            {
                dispatcher.Post(() => _onCancel?.Invoke());
            }
            catch (Exception ex)
            {
                dispatcher.Post(() => _onError?.Invoke(ex));
            }
            finally
            {
                _cts?.Dispose();
                _cts = null;
            }
        }, token);
    }

    public void Cancel() => _cts?.Cancel();

    public bool IsRunning => _cts != null && !_cts.IsCancellationRequested;
}
