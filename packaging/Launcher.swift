import AppKit

// 브라우저를 닫아도 작업을 유지하고, 앱 종료 때는 서버가 자료를 정리할 때까지 기다린다.
final class Launcher: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var status = NSTextField(wrappingLabelWithString: "보관함을 준비하고 있습니다…")
    var openButton = NSButton(title: "보관함 화면 열기", target: nil, action: nil)
    var process: Process?
    var timer: Timer?
    var address: URL?
    var session: URL?
    var quitting = false
    let noBrowser = CommandLine.arguments.contains("--no-browser")
    let logs = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/치지직 보관함")

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu(), item = NSMenuItem(), appMenu = NSMenu()
        appMenu.addItem(withTitle: "치(지직) 다(시보기) 분석기 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu; menu.addItem(item); NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 260), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "치(지직) 다(시보기) 분석기"; window.isReleasedWhenClosed = false
        let name = "치(지직) 다(시보기) 분석기"
        let title = NSTextField(labelWithString: name)
        let styledName = NSMutableAttributedString(string: name, attributes: [.font: NSFont.boldSystemFont(ofSize: 23), .foregroundColor: NSColor.labelColor])
        for detail in ["(지직)", "(시보기)"] {
            styledName.addAttributes([.font: NSFont.systemFont(ofSize: 11), .foregroundColor: NSColor.secondaryLabelColor], range: (name as NSString).range(of: detail))
        }
        title.attributedStringValue = styledName
        let hint = NSTextField(wrappingLabelWithString: "영상·채팅·음성·문맥 분석은 브라우저에서 진행합니다.\n브라우저를 닫아도 작업은 계속됩니다.\n이 앱을 종료하면 진행 중 자료를 보존한 뒤 멈춥니다.")
        openButton.target = self; openButton.action = #selector(openPage); openButton.bezelStyle = .rounded
        let logButton = NSButton(title: "진단 로그 열기", target: self, action: #selector(openLogs))
        let quit = NSButton(title: "작업 정리 후 종료", target: NSApp, action: #selector(NSApplication.terminate(_:)))
        let buttons = NSStackView(views: [openButton, logButton, quit]); buttons.spacing = 8
        let stack = NSStackView(views: [title, hint, status, buttons]); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 22),stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -22),stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 25)])
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        start()
    }
    func start() {
        guard process == nil else { return }
        do {
            let fm = FileManager.default
            let support = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/치지직 보관함")
            let folder = support.appendingPathComponent("실행-" + UUID().uuidString)
            try fm.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            try fm.createDirectory(at: logs, withIntermediateDirectories: true)
            session = folder; address = nil
            let log = logs.appendingPathComponent(folder.lastPathComponent + ".log")
            fm.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600])
            let handle = try FileHandle(forWritingTo: log)
            let child = Process()
            child.executableURL = Bundle.main.resourceURL!.appendingPathComponent("backend/archive-backend")
            child.currentDirectoryURL = fm.homeDirectoryForCurrentUser
            child.arguments = ["--no-open", "--ready-file", folder.appendingPathComponent("ready.json").path, "--parent-pid", String(getpid())]
            if let index = CommandLine.arguments.firstIndex(of: "--library"), index+1 < CommandLine.arguments.count {
                child.arguments! += ["--library", CommandLine.arguments[index+1]]
            }
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"; env.removeValue(forKey: "PYTHONHOME"); env.removeValue(forKey: "PYTHONPATH")
            child.environment = env; child.standardOutput = handle; child.standardError = handle
            child.terminationHandler = { [weak self] task in
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.timer?.invalidate(); self.timer = nil; self.process = nil; self.address = nil
                    try? handle.close(); try? fm.removeItem(at: folder)
                    if self.quitting { NSApp.reply(toApplicationShouldTerminate: true) }
                    else { self.status.stringValue = "실행기가 종료되었습니다 (\(task.terminationStatus)). 로그를 확인하거나 화면 열기로 다시 시작하세요."; self.openButton.isEnabled = true }
                }
            }
            process = child; openButton.isEnabled = false; status.stringValue = "보관함을 준비하고 있습니다…"
            try child.run()
            timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
                guard let self, let data = try? Data(contentsOf: folder.appendingPathComponent("ready.json")),
                      let value = try? JSONSerialization.jsonObject(with: data) as? [String:Any],
                      let text = value["url"] as? String, let url = URL(string: text), url.host == "127.0.0.1",
                      value["pid"] as? Int == Int(child.processIdentifier) else { return }
                self.address = url; self.timer?.invalidate(); self.timer = nil; self.openButton.isEnabled = true
                self.status.stringValue = "실행 중 · 원본과 분석 자료는 앱 밖에 보관합니다."
                if !self.noBrowser { NSWorkspace.shared.open(url) }
            }
        } catch {
            process = nil; openButton.isEnabled = true; status.stringValue = "실행하지 못했습니다: \(error.localizedDescription)"
        }
    }
    @objc func openPage() { if let address { NSWorkspace.shared.open(address) } else { start() } }
    @objc func openLogs() { NSWorkspace.shared.open(logs) }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); if !noBrowser { openPage() }; return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let child = process, child.isRunning else { return .terminateNow }
        quitting = true; openButton.isEnabled = false
        status.stringValue = "진행 중 작업을 정리하고 있습니다. 완료 자료는 유지됩니다."
        child.terminate(); return .terminateLater
    }
}
let app = NSApplication.shared
let delegate = Launcher()
app.delegate = delegate; app.setActivationPolicy(.regular); app.run()
