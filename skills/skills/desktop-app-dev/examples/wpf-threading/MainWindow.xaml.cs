using System;
using System.Threading;
using System.Windows;

namespace WpfThreadingDemo;

public partial class MainWindow : Window
{
    private BackgroundTask? _worker;
    public MainWindow() { InitializeComponent(); }

    private void OnStart(object sender, RoutedEventArgs e)
    {
        if (_worker is { IsRunning: true }) return;
        StartButton.IsEnabled = false;
        StatusText.Text = "started";
        _worker = new BackgroundTask(
            job: (token, progress) => LongJob(token, progress),
            onProgress: p => { ProgressBar.Value = (double)p; StatusText.Text = $"progress {p}%"; },
            onDone:    r => { StatusText.Text = $"done: {r}"; StartButton.IsEnabled = true; },
            onError:   e => { StatusText.Text = $"error: {e.Message}"; StartButton.IsEnabled = true; });
        _worker.Start();
    }

    private void OnCancel(object sender, RoutedEventArgs e) => _worker?.Cancel();

    private static object LongJob(CancellationToken token, IProgress<object> progress)
    {
        for (int i = 1; i <= 100; i++)
        {
            if (token.IsCancellationRequested) throw new OperationCanceledException(token);
            Thread.Sleep(30);
            progress.Report(i);
        }
        return "ok";
    }
}
