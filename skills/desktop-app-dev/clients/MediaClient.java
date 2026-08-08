import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public final class MediaClient {
    private final HttpClient http;
    private final String baseUrl;
    private final String token;
    private final ObjectMapper mapper = new ObjectMapper();

    public MediaClient(String baseUrl, String token) {
        this.http = HttpClient.newHttpClient();
        this.baseUrl = baseUrl;
        this.token = token;
    }

    private HttpRequest.Builder auth(HttpRequest.Builder builder) {
        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        return builder;
    }

    public String enqueue(String kind, Map<String, Object> payload, String dedupeKey)
            throws Exception {
        String body = mapper.writeValueAsString(
                Map.of("kind", kind, "payload", payload, "dedupe_key", dedupeKey));
        HttpRequest request = auth(HttpRequest.newBuilder())
                .uri(URI.create(baseUrl + "/tasks"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String task(long id) throws Exception {
        HttpRequest request = auth(HttpRequest.newBuilder())
                .uri(URI.create(baseUrl + "/tasks/" + id))
                .GET()
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String depsProgress() throws Exception {
        HttpRequest request = auth(HttpRequest.newBuilder())
                .uri(URI.create(baseUrl + "/deps/progress"))
                .GET()
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String depsStatus() throws Exception {
        HttpRequest request = auth(HttpRequest.newBuilder())
                .uri(URI.create(baseUrl + "/deps/status"))
                .GET()
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String installDeps() throws Exception {
        HttpRequest request = auth(HttpRequest.newBuilder())
                .uri(URI.create(baseUrl + "/deps/install"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }
}
