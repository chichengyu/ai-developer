using System;
using System.Reflection;
using System.Windows;

namespace MsixSample;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        VersionText.Text = "Version " + Assembly.GetExecutingAssembly().GetName().Version;
        // Package.Identity is exposed only when running under MSIX context.
        try
        {
            var pkg = Windows.ApplicationModel.Package.Current;
            PackageText.Text = $"Package: {pkg.Id.FullName}";
        }
        catch (InvalidOperationException)
        {
            PackageText.Text = "Not running under MSIX (sideload + run msix for full context).";
        }
    }
}
