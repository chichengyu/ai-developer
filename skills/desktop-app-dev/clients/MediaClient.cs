using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

public sealed class MediaClient
{
    private readonly HttpClient _http;

    public MediaClient(string baseUrl = "http://127.0.0.1:8765", string? token = null)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl) };
        if (!string.IsNullOrEmpty(token))
        {
            _http.DefaultRequestHeaders.Authorization =
                new AuthenticationHeaderValue("Bearer", token);
        }
    }

    public async Task<JsonElement> EnqueueAsync(
        string kind,
        object payload,
        string? dedupeKey = null,
        int priority = 0)
    {
        var body = new { kind, payload, dedupe_key = dedupeKey, priority };
        var response = await _http.PostAsJsonAsync("/tasks", body);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    public async Task<JsonElement> TaskAsync(long id)
    {
        var response = await _http.GetAsync($"/tasks/{id}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    public async Task<JsonElement> DepsProgressAsync()
    {
        var response = await _http.GetAsync("/deps/progress");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    public async Task<JsonElement> DepsStatusAsync()
    {
        var response = await _http.GetAsync("/deps/status");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    public async Task<JsonElement> InstallDepsAsync()
    {
        var response = await _http.PostAsync("/deps/install", null);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }
}
