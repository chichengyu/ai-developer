// swiftui-counter/ -- minimal SwiftUI counter app demonstrating the
// threading_swiftui.swift pattern. Drop into a fresh Xcode project as
// the entry point.

import SwiftUI

@main
struct CounterApp: App {
    var body: some Scene {
        WindowGroup {
            CounterView()
        }
    }
}

@MainActor
@Observable
final class CounterModel {
    var count: Int = 0
    var isLoading: Bool = false

    func increment() {
        count += 1
    }

    func reset() {
        count = 0
    }

    func loadFromNetwork() async {
        isLoading = true
        defer { isLoading = false }
        try? await Task.sleep(nanoseconds: 300_000_000)  // 300ms
        count = Int.random(in: 1...100)
    }
}

struct CounterView: View {
    @State private var model = CounterModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text("\(model.count)")
                    .font(.system(size: 96, weight: .bold, design: .rounded))
                    .accessibilityLabel("Count: \(model.count)")

                HStack(spacing: 12) {
                    Button("Reset", systemImage: "arrow.counterclockwise") {
                        model.reset()
                    }
                    .buttonStyle(.bordered)

                    Button("Increment", systemImage: "plus") {
                        model.increment()
                    }
                    .buttonStyle(.borderedProminent)
                }

                Button {
                    Task { await model.loadFromNetwork() }
                } label: {
                    if model.isLoading {
                        ProgressView()
                    } else {
                        Label("Load from network", systemImage: "network")
                    }
                }
                .disabled(model.isLoading)
            }
            .padding()
            .navigationTitle("Counter")
        }
    }
}