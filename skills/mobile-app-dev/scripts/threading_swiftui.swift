// threading_swiftui.swift -- canonical async + UI bridge for SwiftUI.
//
// Use this as the pattern for every screen that loads data. All IO
// happens off the main thread; UI updates happen on the main actor
// automatically via @MainActor / Observable.

import Foundation
import SwiftUI

// MARK: - ViewModel (iOS 17+ Observation)

@MainActor
@Observable
final class FeedViewModel {
    enum State {
        case idle
        case loading
        case loaded([Item])
        case failed(String)
    }

    private(set) var state: State = .idle

    private let api: FeedAPI
    private var loadTask: Task<Void, Never>?

    init(api: FeedAPI = .live) {
        self.api = api
    }

    func load() async {
        loadTask?.cancel()
        loadTask = Task { [weak self] in
            await self?.performLoad()
        }
    }

    private func performLoad() async {
        state = .loading
        do {
            let items = try await api.fetchFeed()
            guard !Task.isCancelled else { return }
            state = .loaded(items)
        } catch is CancellationError {
            // ignore
        } catch {
            guard !Task.isCancelled else { return }
            state = .failed(error.localizedDescription)
        }
    }

    func cancel() {
        loadTask?.cancel()
        loadTask = nil
    }

    deinit {
        loadTask?.cancel()
    }
}

// MARK: - View

struct FeedView: View {
    @State private var model = FeedViewModel()

    var body: some View {
        content
            .task {
                await model.load()
            }
            .refreshable {
                await model.load()
            }
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case .idle, .loading:
            ProgressView()
        case .loaded(let items):
            List(items) { item in
                FeedRow(item: item)
            }
        case .failed(let message):
            ContentUnavailableView(
                "Couldn't load feed",
                systemImage: "wifi.exclamationmark",
                description: Text(message)
            )
        }
    }
}

// MARK: - API

protocol FeedAPI: Sendable {
    func fetchFeed() async throws -> [Item]
}

extension FeedAPI {
    static var live: FeedAPI { LiveFeedAPI() }
}

struct Item: Identifiable, Codable, Hashable, Sendable {
    let id: UUID
    let title: String
    let summary: String
}

struct LiveFeedAPI: FeedAPI {
    func fetchFeed() async throws -> [Item] {
        // HTTP call off the main thread; URLSession runs on its own queue.
        let url = URL(string: "https://api.example.com/feed")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([Item].self, from: data)
    }
}

// MARK: - Smoke test

@main
struct ThreadingSwiftUISmoke {
    static func main() async {
        // No real network call; just verify the model can be instantiated.
        let model = await FeedViewModel(api: StubFeedAPI())
        await model.load()
        switch await model.state {
        case .loaded(let items):
            assert(items.count == 2, "expected 2 stub items")
        default:
            assertionFailure("expected .loaded")
        }
        print("[OK] threading_swiftui smoke")
    }
}

struct StubFeedAPI: FeedAPI {
    func fetchFeed() async throws -> [Item] {
        try? await Task.sleep(nanoseconds: 10_000_000)  // 10ms
        return [
            Item(id: UUID(), title: "First", summary: "Hello"),
            Item(id: UUID(), title: "Second", summary: "World"),
        ]
    }
}