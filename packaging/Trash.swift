import Foundation
// Finder와 같은 휴지통 동작을 사용해 외장 볼륨과 복원 정보를 macOS에 맡긴다.
guard CommandLine.arguments.count == 2 else { exit(2) }
var destination: NSURL?
do {
    try FileManager.default.trashItem(at: URL(fileURLWithPath: CommandLine.arguments[1]), resultingItemURL: &destination)
    let data = try JSONSerialization.data(withJSONObject: ["trashed_to": destination?.path ?? "휴지통"])
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8)); exit(1)
}
