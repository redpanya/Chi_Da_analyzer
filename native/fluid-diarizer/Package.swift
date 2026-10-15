// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "ArchiveDiarizer", platforms: [.macOS(.v14)],
    dependencies: [.package(path: "../FluidAudio", traits: ["Diarizer"])],
    targets: [.executableTarget(name: "archive-fluid-diarizer",
        dependencies: [.product(name: "FluidAudio", package: "FluidAudio")])])
