import Foundation
import FluidAudio
import Darwin

struct Request: Decodable { let audio: String; let cache: String; let output: String; let speakers: Int }
struct Turn: Encodable { let start_ms: Int; let end_ms: Int; let speaker: Int }
struct Result: Encodable { let turns: [Turn]; let engine: String; let elapsed_seconds: Double }
struct Progress: Encodable { let phase: String; let completed: Int; let total: Int }

@main struct Runner {
    static func main() async throws {
        if CommandLine.arguments.dropFirst() == ["--speaker-tool-check"] {
            print("CHIDA_SPEAKER_TOOL:1:fluid")
            return
        }
        let request = try JSONDecoder().decode(Request.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        let parent = getppid()
        Task.detached {
            while true {
                try await Task.sleep(for: .seconds(1))
                if getppid() != parent { exit(1) }
            }
        }
        // 추론 중 다운로드나 모델 캐시 삭제를 허용하지 않는다.
        ModelHub.offlineMode = true
        let began = Date()
        let models = try await OfflineDiarizerModels.load(from: URL(fileURLWithPath: request.cache))
        var config = OfflineDiarizerConfig()
        config.exclusiveSegments = false
        if request.speakers > 0 { config = config.withSpeakers(exactly: request.speakers) }
        let manager = OfflineDiarizerManager(config: config)
        await manager.initialize(models: models)
        let progressFile = URL(fileURLWithPath: request.output).deletingLastPathComponent().appendingPathComponent("progress.json")
        let result = try await manager.process(URL(fileURLWithPath: request.audio)) { done, total in
            if let data = try? JSONEncoder().encode(Progress(phase: "음성 구간 탐지 · 이후 화자 연결", completed: done, total: total)) {
                try? data.write(to: progressFile, options: .atomic)
            }
        }
        let segments = result.segments.sorted { $0.startTimeSeconds < $1.startTimeSeconds }
        var ids: [String: Int] = [:]
        let turns = segments.compactMap { segment -> Turn? in
            let id = String(describing: segment.speakerId)
            if ids[id] == nil { ids[id] = ids.count }
            let start = Int((segment.startTimeSeconds * 1000).rounded())
            let end = Int((segment.endTimeSeconds * 1000).rounded())
            return end > start ? Turn(start_ms: start, end_ms: end, speaker: ids[id]!) : nil
        }
        let output = Result(turns: turns, engine: "FluidAudio 224de0f · CoreML offline VBx", elapsed_seconds: Date().timeIntervalSince(began))
        try JSONEncoder().encode(output).write(to: URL(fileURLWithPath: request.output), options: .atomic)
    }
}
