// Minimal NativeAOT-compatible WinForms app.
//
// Demonstrates:
//   1. A real ~5 MB single-file EXE (no .NET runtime required on the target).
//   2. AOT-safe threading: CancellationToken + IProgress<T> + Control.Invoke.
//   3. The <PublishAot>true</PublishAot> csproj flags above that make this work.
//
// Why no `threading_*` template link?  NativeAOT trims aggressively; pulling
// in a generic dispatcher helper would force reflection paths the trimmer
// cannot prove safe. The AOT-safe pattern is to use the framework-provided
// `Control.BeginInvoke` (which is AOT-safe because Control is in the BCL)
// rather than a custom dispatcher abstraction.

using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private readonly Button _start;
    private readonly Button _cancel;
    private readonly ProgressBar _bar;
    private readonly Label _status;
    private CancellationTokenSource? _cts;

    public MainForm()
    {
        Text = "NativeAOT WinForms demo";
        Width = 420;
        Height = 200;
        StartPosition = FormStartPosition.CenterScreen;

        _status = new Label { Text = "idle", Dock = DockStyle.Top, Height = 24, Padding = new Padding(8) };
        _bar = new ProgressBar { Dock = DockStyle.Top, Minimum = 0, Maximum = 100 };
        _start = new Button { Text = "Start 3s job", Dock = DockStyle.Top, Height = 32 };
        _cancel = new Button { Text = "Cancel", Dock = DockStyle.Top, Height = 32 };
        _start.Click += OnStart;
        _cancel.Click += (s, e) => _cts?.Cancel();
        Controls.Add(_start);
        Controls.Add(_bar);
        Controls.Add(_status);
    }

    private void OnStart(object? sender, EventArgs e)
    {
        if (_cts is { IsCancellationRequested: false }) return;
        _start.Enabled = false;
        _status.Text = "started";
        _cts = new CancellationTokenSource();
        var token = _cts.Token;

        // AOT-safe progress: BeginInvoke marshals to the WinForms UI thread.
        var progress = new Progress<int>(p => { _bar.Value = p; _status.Text = $"progress {p}%"; });

        Task.Run(() =>
        {
            try
            {
                for (int i = 1; i <= 100; i++)
                {
                    if (token.IsCancellationRequested) throw new OperationCanceledException(token);
                    Thread.Sleep(30);
                    progress.Report(i);
                }
                BeginInvoke(new Action(() =>
                {
                    _status.Text = "done";
                    _start.Enabled = true;
                }));
            }
            catch (OperationCanceledException)
            {
                BeginInvoke(new Action(() => { _status.Text = "cancelled"; _start.Enabled = true; }));
            }
            catch (Exception ex)
            {
                BeginInvoke(new Action(() => { _status.Text = $"error: {ex.Message}"; _start.Enabled = true; }));
            }
        }, token);
    }
}