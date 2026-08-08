import Foundation

struct MediaClient {
    let baseURL: URL
    let token: String?

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!, token: String? = nil) {
        self.baseURL = baseURL
        self.token = token
    }

    private func authorize(_ request: inout URLRequest) {
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
    }

    func enqueue(
        kind: String,
        payload: [String: Any],
        dedupeKey: String? = nil
    ) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent("tasks"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request)
        var body: [String: Any] = ["kind": kind, "payload": payload]
        if let dedupeKey {
            body["dedupe_key"] = dedupeKey
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }

    func task(id: Int) async throws -> Data {
        let url = baseURL.appendingPathComponent("tasks/\(id)")
        var request = URLRequest(url: url)
        authorize(&request)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }

    func depsProgress() async throws -> Data {
        let url = baseURL.appendingPathComponent("deps/progress")
        var request = URLRequest(url: url)
        authorize(&request)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }

    func depsStatus() async throws -> Data {
        let url = baseURL.appendingPathComponent("deps/status")
        var request = URLRequest(url: url)
        authorize(&request)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }

    func installDeps() async throws -> Data {
        let url = baseURL.appendingPathComponent("deps/install")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        authorize(&request)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }
}
