// C# WPF background work with cancellation + progress + safe UI bridge.
// Drop-in usage from a ViewModel or code-behind:
//
//   var worker = new BackgroundTask(token => LongJob(token, progress),
//                                   onProgress: UpdateProgress,
//                                   onDone:     r => Status = $"done: {r}",
//                                   onError:    e => Status = $"error: {e.Message}",
//                                   onCancel:   () => Status = "cancelled");
//   worker.Start();
//   // later: worker.Cancel();
#nullable enable
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

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

    public void Start()
    {
        if (_cts != null) throw new InvalidOperationException("already running");
        var dispatcher = Application.Current?.Dispatcher
            ?? throw new InvalidOperationException("no WPF dispatcher available");
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        var progress = new Progress<object>(p => dispatcher.Invoke(() => _onProgress?.Invoke(p)));

        Task.Run(() =>
        {
            try
            {
                var result = _job(token, progress);
                dispatcher.Invoke(() => _onDone?.Invoke(result));
            }
            catch (OperationCanceledException)
            {
                dispatcher.Invoke(() => _onCancel?.Invoke());
            }
            catch (Exception ex)
            {
                dispatcher.Invoke(() => _onError?.Invoke(ex));
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
