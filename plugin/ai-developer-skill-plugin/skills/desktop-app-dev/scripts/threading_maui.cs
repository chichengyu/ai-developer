#nullable enable
// .NET MAUI background work with cancellation + progress + safe UI bridge.
//
// `MainThread.BeginInvokeOnMainThread` is the canonical way to hop back to
// the UI thread from a background task. All callbacks in this wrapper run
// on the UI thread.
//
// Usage:
//   var worker = new BackgroundTask(
//       job: (token, progress) => LongJob(token, progress),
//       onProgress: p => ProgressBar.Progress = Convert.ToDouble(p),
//       onDone: r => StatusLabel.Text = $"done: {r}",
//       onError: e => StatusLabel.Text = $"error: {e.Message}",
//       onCancel: () => StatusLabel.Text = "cancelled");
//   worker.Start();
//   // later: worker.Cancel();

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Maui.ApplicationModel;

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
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        var progress = new Progress<object>(p => Post(() => _onProgress?.Invoke(p)));

        Task.Run(() =>
        {
            try
            {
                var result = _job(token, progress);
                Post(() => _onDone?.Invoke(result));
            }
            catch (OperationCanceledException)
            {
                Post(() => _onCancel?.Invoke());
            }
            catch (Exception ex)
            {
                Post(() => _onError?.Invoke(ex));
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

    private static void Post(Action action)
    {
        if (MainThread.IsMainThread) action();
        else MainThread.BeginInvokeOnMainThread(action);
    }
}
