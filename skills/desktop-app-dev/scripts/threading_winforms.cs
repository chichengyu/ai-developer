#nullable enable
// C# WinForms background work with cancellation + progress + safe UI bridge.
//
// Usage:
//   var worker = new BackgroundTask(
//       owner: this,
//       job: (token, progress) => LongJob(token, progress),
//       onProgress: p => progressBar.Value = Convert.ToInt32(p),
//       onDone: r => statusLabel.Text = $"done: {r}",
//       onError: e => statusLabel.Text = $"error: {e.Message}",
//       onCancel: () => statusLabel.Text = "cancelled");
//   worker.Start();
//   // later: worker.Cancel();
//
// `Control.BeginInvoke` posts the callback to the control's owning UI
// thread, so the worker never touches a control directly.

using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

public sealed class BackgroundTask
{
    private readonly Control _owner;
    private readonly Func<CancellationToken, IProgress<object>, object> _job;
    private readonly Action<object>? _onDone;
    private readonly Action<Exception>? _onError;
    private readonly Action<object>? _onProgress;
    private readonly Action? _onCancel;
    private CancellationTokenSource? _cts;

    public BackgroundTask(
        Control owner,
        Func<CancellationToken, IProgress<object>, object> job,
        Action<object>? onDone = null,
        Action<Exception>? onError = null,
        Action<object>? onProgress = null,
        Action? onCancel = null)
    {
        _owner = owner;
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

    private void Post(Action action)
    {
        if (_owner.IsDisposed || !_owner.IsHandleCreated) return;
        if (_owner.InvokeRequired) _owner.BeginInvoke(action);
        else action();
    }
}
