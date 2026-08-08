// WinUI 3 / WinRT background work with cancellation + progress + safe UI bridge.
//
// Drop-in usage from a ViewModel or code-behind (WinUI 3 / Windows App SDK):
//
//   var worker = new BackgroundTask(token => LongJob(token, progress),
//                                   onProgress: UpdateProgress,
//                                   onDone:     r => Status = `$"done: {r}"`,
//                                   onError:    e => Status = `$"error: {e.Message}"`,
//                                   onCancel:   () => Status = "cancelled");
//   worker.Start(DispatcherQueue.GetForCurrentThread());
//   // later: worker.Cancel();
//
// Why a separate template from `threading_wpf.cs`?
//   * WinUI 3 uses `Microsoft.UI.Dispatching.DispatcherQueue`, not WPF's
//     `System.Windows.Threading.Dispatcher`. The API is similar (TryEnqueue
//     vs Invoke) but the type lives in a different assembly.
//   * WinUI 3's `Window.DispatcherQueue` is the canonical handle; there is
//     no `Application.Current.Dispatcher` global.
//   * WinUI 3 is single-threaded: every UI touch must happen on the
//     DispatcherQueue thread, including setting `TextBlock.Text`,
//     `ProgressBar.Value`, and `Button.IsEnabled`.

#nullable enable
using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;

public sealed class BackgroundTask
{
    private readonly Func<CancellationToken, IProgress<object>, object> _job;
    private readonly Action<object>? _onDone;
    private readonly Action<Exception>? _onError;
    private readonly Action<object>? _onProgress;
    private readonly Action? _onCancel;

    public BackgroundTask(
        Func<CancellationToken, IProgress<object>, object> job,
        Action<object>? onDone = null,
        Action<Exception>? onError = null,
        Action<object>? onProgress = null,
        Action? onCancel = null)
    {
        _job = job; _onDone = onDone; _onError = onError; _onProgress = onProgress;
        _onCancel = onCancel;
    }

    private CancellationTokenSource? _cts;
    private DispatcherQueue? _dispatcher;

    /// <summary>Start the worker. Capture the UI dispatcher first.</summary>
    public void Start(DispatcherQueue uiDispatcher)
    {
        if (_cts != null) throw new InvalidOperationException("already running");
        if (uiDispatcher is null) throw new ArgumentNullException(nameof(uiDispatcher));
        _dispatcher = uiDispatcher;
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        var progress = new Progress<object>(p => _dispatcher.TryEnqueue(() => _onProgress?.Invoke(p)));

        Task.Run(() =>
        {
            try
            {
                var result = _job(token, progress);
                _dispatcher.TryEnqueue(() => _onDone?.Invoke(result));
            }
            catch (OperationCanceledException)
            {
                _dispatcher.TryEnqueue(() => _onCancel?.Invoke());
            }
            catch (Exception ex)
            {
                _dispatcher.TryEnqueue(() => _onError?.Invoke(ex));
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
