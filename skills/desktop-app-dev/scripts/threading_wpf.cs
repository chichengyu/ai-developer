// C# WPF / WinUI 3 background work with cancellation + progress + safe UI bridge.
// Drop-in usage from a ViewModel or code-behind:
//
//   var worker = new BackgroundTask(token => LongJob(token, progress),
//                                   onProgress: UpdateProgress,
//                                   onDone:     r => Status = $"done: {r}",
//                                   onError:    e => Status = $"error: {e.Message}");
//   worker.Start();
//   // later: worker.Cancel();
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;        // WPF. For WinUI 3: using Microsoft.UI.Dispatching;

public sealed class BackgroundTask
{
    private readonly Func<CancellationToken, IProgress<object>, object> _job;
    private readonly Action<object> _onDone;
    private readonly Action<Exception> _onError;
    private readonly Action<object> _onProgress;

    public BackgroundTask(
        Func<CancellationToken, IProgress<object>, object> job,
        Action<object> onDone,
        Action<Exception> onError,
        Action<object> onProgress)
    {
        _job = job; _onDone = onDone; _onError = onError; _onProgress = onProgress;
    }

    private CancellationTokenSource? _cts;

    public void Start()
    {
        if (_cts != null) throw new InvalidOperationException("already running");
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        var dispatcher = Application.Current?.Dispatcher;  // WPF. WinUI: DispatcherQueue.GetForCurrentThread()
        var progress = new Progress<object>(p => dispatcher?.Invoke(() => _onProgress(p)));

        Task.Run(() =>
        {
            try { var result = _job(token, progress); dispatcher?.Invoke(() => _onDone(result)); }
            catch (OperationCanceledException) { /* expected on cancel */ }
            catch (Exception ex) { dispatcher?.Invoke(() => _onError(ex)); }
        }, token);
    }

    public void Cancel() => _cts?.Cancel();

    public bool IsRunning => _cts != null && !_cts.IsCancellationRequested;
}
