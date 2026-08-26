import SwiftUI
import RealityKit

@main
struct ImmersiveApp: App {
    var body: some Scene {
        WindowGroup {
            Text("Hello visionOS")
                .padding()
        }
        ImmersiveSpace(id: "Space") {
            RealityView { content in
                let box = ModelEntity(
                    mesh: .generateBox(size: 0.2),
                    materials: [SimpleMaterial(color: .blue, isMetallic: false)]
                )
                content.add(box)
            }
        }
    }
}
