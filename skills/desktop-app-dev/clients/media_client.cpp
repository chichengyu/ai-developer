#include <string>
#include <utility>

#include <curl/curl.h>

class MediaClient {
public:
    explicit MediaClient(
        std::string baseUrl = "http://127.0.0.1:8765",
        std::string token = "")
        : baseUrl_(std::move(baseUrl)), token_(std::move(token)) {}

    std::string enqueue(const std::string& jsonBody) const {
        return post("/tasks", jsonBody);
    }

    std::string task(long id) const {
        return get("/tasks/" + std::to_string(id));
    }

    std::string depsProgress() const {
        return get("/deps/progress");
    }

    std::string depsStatus() const {
        return get("/deps/status");
    }

    std::string installDeps() const {
        return post("/deps/install", "{}");
    }

private:
    std::string baseUrl_;
    std::string token_;

    static size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp) {
        auto* output = static_cast<std::string*>(userp);
        output->append(static_cast<char*>(contents), size * nmemb);
        return size * nmemb;
    }

    std::string request(const std::string& path, const std::string& body, bool isPost) const {
        std::string url = baseUrl_ + path;
        std::string result;
        CURL* curl = curl_easy_init();
        if (!curl) {
            return result;
        }
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &result);
        curl_slist* headers = nullptr;
        if (!token_.empty()) {
            std::string auth = "Authorization: Bearer " + token_;
            headers = curl_slist_append(headers, auth.c_str());
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        }
        if (isPost) {
            curl_easy_setopt(curl, CURLOPT_POST, 1L);
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
        }
        curl_easy_perform(curl);
        if (headers) {
            curl_slist_free_all(headers);
        }
        curl_easy_cleanup(curl);
        return result;
    }

    std::string get(const std::string& path) const {
        return request(path, "", false);
    }

    std::string post(const std::string& path, const std::string& body) const {
        return request(path, body, true);
    }
};
