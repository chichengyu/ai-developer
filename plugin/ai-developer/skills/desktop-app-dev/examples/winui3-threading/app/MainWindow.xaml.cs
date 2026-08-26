using System;
using System.Threading;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace WinUIThreadingDemo;

public sealed partial class MainWindow : Window
{
    private BackgroundTask? _worker;

    public MainWindow()
    {
        this.InitializeComponent();
        this.Title = "WinUI 3 BackgroundTask demo";
    }

    private void OnStart(object sender, RoutedEventArgs e)
    {
        if (_worker is { IsRunning: true }) return;
        StartButton.IsEnabled = false;
        StatusText.Text = "started";
        // Capture the UI thread dispatcher. WinUI 3 has no Application.Current.
        var dq = DispatcherQueue.GetForCurrentThread();
        _worker = new BackgroundTask(
            job:        (token, progress) => LongJob(token, progress),
            onProgress: p => { ProgressBar.Value = (double)p; StatusText.Text = $"progress {p}%"; },
            onDone:     r => { StatusText.Text = $"done: {r}"; StartButton.IsEnabled = true; },
            onError:    ex => { StatusText.Text = $"error: {ex.Message}"; StartButton.IsEnabled = true; });
        _worker.Start(dq);
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