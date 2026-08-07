# .NET MAUI deep dive

Read this when Step 1.5 has picked .NET MAUI and you need
platform-specific patterns. For the workflow + framework comparison,
see the main `SKILL.md`.

---

## When MAUI is the right pick

- Team is .NET-first (existing C# / XAML / WPF / Xamarin codebase).
- Both iOS + Android delivery is required.
- Performance budget is moderate (not animation-heavy).
- The app is a productivity / LOB / line-of-business tool.

If the app is animation-heavy or needs deep custom drawing, prefer
Flutter or native.

## Project structure

```
MyApp/
  MyApp.csproj                  (.NET 8 MAUI project file)
  MauiProgram.cs                DI bootstrap
  App.xaml + App.xaml.cs        App-level XAML
  AppShell.xaml + .cs           Shell navigation root
  Resources/
    AppIcon/
    Splash/
    Fonts/
    Images/
    Styles/
      Colors.xaml
      Styles.xaml
  Platforms/
    Android/
      AndroidManifest.xml
      MainActivity.cs
    iOS/
      AppDelegate.cs
      Info.plist
      Program.cs
  Features/
    Feed/
      FeedPage.xaml + .cs
      FeedViewModel.cs
      FeedModel.cs
    Settings/
      ...
```

## ViewModel + CommunityToolkit.Mvvm

```csharp
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

public partial class FeedViewModel : ObservableObject
{
    private readonly IFeedRepository _repo;

    [ObservableProperty]
    private FeedItem[] items = Array.Empty<FeedItem>();

    [ObservableProperty]
    private bool isLoading;

    public FeedViewModel(IFeedRepository repo)
    {
        _repo = repo;
    }

    [RelayCommand]
    private async Task RefreshAsync()
    {
        IsLoading = true;
        try
        {
            Items = await _repo.FetchAsync();
        }
        finally
        {
            IsLoading = false;
        }
    }
}
```

`[ObservableProperty]` generates the `OnPropertyChanged` plumbing.
`[RelayCommand]` generates an `IRelayCommand`. This is the MAUI /
CommunityToolkit equivalent of Compose's `StateFlow` or SwiftUI's
`@Observable`.

## XAML

```xml
<?xml version="1.0" encoding="utf-8" ?>
<ContentPage xmlns="http://schemas.microsoft.com/dotnet/2021/maui"
             xmlns:x="http://schemas.microsoft.com/winfx/2009/xaml"
             xmlns:vm="clr-namespace:MyApp.Features.Feed"
             x:Class="MyApp.Features.Feed.FeedPage"
             x:DataType="vm:FeedViewModel"
             Title="Feed">
    <RefreshView IsRefreshing="{Binding IsLoading}"
                 Command="{Binding RefreshCommand}">
        <CollectionView ItemsSource="{Binding Items}">
            <CollectionView.ItemTemplate>
                <DataTemplate x:DataType="vm:FeedItem">
                    <VerticalStackLayout Padding="12">
                        <Label Text="{Binding Title}" FontSize="16" FontAttributes="Bold" />
                        <Label Text="{Binding Summary}" FontSize="14" />
                    </VerticalStackLayout>
                </DataTemplate>
            </CollectionView.ItemTemplate>
        </CollectionView>
    </RefreshView>
</ContentPage>
```

`x:DataType` enables compiled bindings (faster, type-safe at
compile time).

## Shell navigation

```xml
<Shell
    xmlns="http://schemas.microsoft.com/dotnet/2021/maui"
    xmlns:x="http://schemas.microsoft.com/winfx/2009/xaml"
    FlyoutBehavior="Disabled">
    <TabBar>
        <ShellContent Title="Feed" Route="feed" ContentTemplate="{DataTemplate local:FeedPage}" />
        <ShellContent Title="Settings" Route="settings" ContentTemplate="{DataTemplate local:SettingsPage}" />
    </TabBar>
</Shell>
```

Navigate from code:

```csharp
await Shell.Current.GoToAsync("//settings");
```

## DI / configuration

`MauiProgram.cs`:

```csharp
public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder
            .UseMauiApp<App>()
            .ConfigureFonts(fonts =>
            {
                fonts.AddFont("OpenSans-Regular.ttf", "OpenSans");
            });

        builder.Services.AddSingleton<IFeedRepository, LiveFeedRepository>();
        builder.Services.AddTransient<FeedViewModel>();
        builder.Services.AddTransient<FeedPage>();

        return builder.Build();
    }
}
```

Then in `FeedPage.xaml.cs`:

```csharp
public partial class FeedPage : ContentPage
{
    public FeedPage(FeedViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = viewModel;
    }
}
```

## Persistence (Preferences + FileSystem)

```csharp
// Preferences (typed key-value, backed by NSUserDefaults / SharedPreferences).
Preferences.Default.Set("lastSync", DateTime.UtcNow.ToString("o"));
var last = Preferences.Default.Get("lastSync", string.Empty);

// FileSystem helpers for app-private dir.
var filePath = Path.Combine(FileSystem.AppDataDirectory, "cache.json");
await File.WriteAllTextAsync(filePath, json);
```

## Networking (HttpClient)

```csharp
public class LiveFeedRepository : IFeedRepository
{
    private readonly HttpClient _http;

    public LiveFeedRepository(HttpClient http)
    {
        _http = http;
    }

    public async Task<FeedItem[]> FetchAsync()
    {
        var response = await _http.GetAsync("https://api.example.com/feed");
        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<FeedItem[]>(json, JsonOpts.Default) ?? Array.Empty<FeedItem>();
    }
}

// Registration:
builder.Services.AddHttpClient<IFeedRepository, LiveFeedRepository>(client =>
{
    client.BaseAddress = new Uri("https://api.example.com/");
    client.DefaultRequestHeaders.Add("User-Agent", "MyApp/1.0");
});
```

## Lifecycle

```csharp
public partial class FeedPage : ContentPage
{
    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (BindingContext is FeedViewModel vm)
            vm.RefreshCommand.Execute(null);
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        // Pause animations, save draft state.
    }
}
```

## Testing

```csharp
public class FeedViewModelTest
{
    [Fact]
    public async Task Refresh_PopulatesItems()
    {
        var repo = new StubRepo(items: new[] { new FeedItem("1", "First", "Hello") });
        var vm = new FeedViewModel(repo);
        await vm.RefreshCommand.ExecuteAsync(null);
        Assert.Single(vm.Items);
        Assert.Equal("First", vm.Items[0].Title);
    }
}
```

UI tests via Appium / XCUITest / Espresso (slower, run on device).

## Build + ship

```bash
dotnet build -f net8.0-android -c Release
dotnet build -f net8.0-ios -c Release

dotnet publish -f net8.0-android -c Release -p:RuntimeIdentifier=android-arm64
dotnet publish -f net8.0-ios -c Release -p:RuntimeIdentifier=ios-arm64
```

For App Store / Play Store upload, use Fastlane with the
`references/distribution_playbook.md` patterns.

## Limitations vs Flutter / RN

- **Smaller ecosystem** for mobile-specific packages (especially
  custom UI / animation).
- **iOS build requires macOS** (same as Xcode).
- **Build times** are longer than Flutter (XAML compilation + MSBuild).
- **Less community momentum** compared to Flutter / RN.

## When to leave MAUI

If the app needs:
- Heavy custom animation / canvas (use Flutter).
- AR / VR / camera pipeline (use native).
- Live Activities / Widgets (use native).

## Resources

- [.NET MAUI docs](https://learn.microsoft.com/en-us/dotnet/maui/)
- [CommunityToolkit.Mvvm](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/mvvm)
- [MAUI samples](https://github.com/dotnet/maui-samples)
