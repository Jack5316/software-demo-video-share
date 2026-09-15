import Foundation
import AppKit
import ScreenCaptureKit
import AVFoundation

func emit(_ data: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: data, options: [.sortedKeys]), let s = String(data: d, encoding: .utf8) { print(s); fflush(stdout) }
}
struct Failure: Error { let reason: String }
final class State: @unchecked Sendable {
    private let lock = NSLock()
    private var started = false
    private var finished = false
    private var failed = false
    func start() { lock.withLock { started = true } }
    func finish() { lock.withLock { finished = true } }
    func fail() { lock.withLock { failed = true } }
    func snapshot() -> (Bool, Bool, Bool) { lock.withLock { (started, finished, failed) } }
}
final class Delegate: NSObject, SCRecordingOutputDelegate, SCStreamDelegate, @unchecked Sendable {
    let state = State()
    func recordingOutputDidStartRecording(_ recordingOutput: SCRecordingOutput) {
        state.start()
        emit(["event": "READY", "utc_epoch": Date().timeIntervalSince1970, "monotonic_seconds": ProcessInfo.processInfo.systemUptime, "capture_scope": "single-window"])
    }
    func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) { state.fail(); emit(["event": "RECORDING_ERROR"]) }
    func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) { state.finish() }
    func stream(_ stream: SCStream, didStopWithError error: Error) { state.fail(); emit(["event": "STREAM_ERROR"]) }
}
final class Watchdog {
    private var timer: DispatchSourceTimer?
    func arm(_ seconds: Double, phase: String) {
        timer?.cancel()
        let t = DispatchSource.makeTimerSource(queue: .global())
        t.schedule(deadline: .now() + seconds)
        t.setEventHandler { emit(["event": "FAILED", "reason": "timeout", "phase": phase, "partial_retained": true]); exit(124) }
        timer = t; t.resume()
    }
    func cancel() { timer?.cancel(); timer = nil }
}
struct Options {
    var values: [String: String] = [:]
    init(_ args: [String]) throws {
        guard args.count % 2 == 0 else { throw Failure(reason: "arguments-must-be-flag-value-pairs") }
        let allowed: Set<String> = ["--output", "--stop-file", "--title", "--window-id", "--bundle", "--max-seconds", "--fps"]
        for i in stride(from: 0, to: args.count, by: 2) {
            guard allowed.contains(args[i]), values[args[i]] == nil else { throw Failure(reason: "unknown-or-duplicate-argument") }
            values[args[i]] = args[i+1]
        }
        guard values["--bundle"]?.isEmpty == false, values["--output"] != nil, values["--stop-file"] != nil, (values["--title"] != nil) != (values["--window-id"] != nil) else { throw Failure(reason: "bundle-output-stop-file-and-one-window-selector-required") }
        if let title = values["--title"], title.trimmingCharacters(in: .whitespaces).isEmpty { throw Failure(reason: "empty-title-selector") }
        if let id = values["--window-id"], UInt32(id) == nil { throw Failure(reason: "invalid-window-id") }
    }
}
@main struct Main {
    @MainActor static func run() async throws {
        _ = NSApplication.shared // Required before CG/SC initialization in a command-line binary.
        let args = Array(CommandLine.arguments.dropFirst())
        if args == ["--help"] {
            print("WindowRecorder --output VIDEO.mp4 --stop-file PATH (--title SUBSTRING | --window-id ID) --bundle APP_BUNDLE_ID [--max-seconds 1200] [--fps 30]")
            return
        }
        let o = try Options(args); let v = o.values
        guard let limit = Double(v["--max-seconds"] ?? "1200"), limit >= 1, limit <= 7200, let fps = Int32(v["--fps"] ?? "30"), fps >= 1, fps <= 60 else { throw Failure(reason: "invalid-duration-or-fps") }
        let fm = FileManager.default
        let output = URL(fileURLWithPath: v["--output"]!).standardizedFileURL
        let partial = output.deletingPathExtension().appendingPathExtension("partial.mp4")
        let stop = URL(fileURLWithPath: v["--stop-file"]!).standardizedFileURL
        guard output.pathExtension.lowercased() == "mp4", output != stop, partial != stop else { throw Failure(reason: "invalid-output-path") }
        guard !fm.fileExists(atPath: output.path), !fm.fileExists(atPath: partial.path), !fm.fileExists(atPath: stop.path) else { throw Failure(reason: "output-partial-or-stop-file-already-exists") }
        try fm.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
        let watchdog = Watchdog(); watchdog.arm(15, phase: "window-discovery")
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        let candidates = content.windows.filter { w in
            w.owningApplication?.bundleIdentifier == v["--bundle"]! && w.frame.width > 100 && w.frame.height > 100 &&
            (v["--title"].map { title in (w.title ?? "").contains(title) } ?? (w.windowID == UInt32(v["--window-id"]!)))
        }
        // Never guess by largest window: an ambiguous selector can expose the wrong app window.
        guard candidates.count == 1, let window = candidates.first else { watchdog.cancel(); throw Failure(reason: candidates.isEmpty ? "no-window-match" : "ambiguous-window-match") }
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let config = SCStreamConfiguration()
        config.width = max(2, Int(window.frame.width * 2) / 2 * 2)
        config.height = max(2, Int(window.frame.height * 2) / 2 * 2)
        config.minimumFrameInterval = CMTime(value: 1, timescale: fps)
        config.capturesAudio = false; config.showsCursor = true
        config.ignoreShadowsSingleWindow = true; config.queueDepth = 6
        let delegate = Delegate()
        let recordingConfig = SCRecordingOutputConfiguration()
        recordingConfig.outputURL = partial; recordingConfig.videoCodecType = .h264; recordingConfig.outputFileType = .mp4
        let recording = SCRecordingOutput(configuration: recordingConfig, delegate: delegate)
        let stream = SCStream(filter: filter, configuration: config, delegate: delegate)
        try stream.addRecordingOutput(recording)
        emit(["event": "TARGET", "window_id": window.windowID, "width": config.width, "height": config.height, "fps": fps, "capture_scope": "single-window"])
        watchdog.arm(15, phase: "start-and-ready")
        try await stream.startCapture()
        while !delegate.state.snapshot().0 && !delegate.state.snapshot().2 { try await Task.sleep(for: .milliseconds(100)) }
        guard !delegate.state.snapshot().2 else { watchdog.cancel(); throw Failure(reason: "recording-failed-before-ready") }
        watchdog.arm(limit + 10, phase: "recording")
        let start = ProcessInfo.processInfo.systemUptime
        var reason = "duration-limit"
        while ProcessInfo.processInfo.systemUptime - start < limit && !delegate.state.snapshot().2 {
            if fm.fileExists(atPath: stop.path) { reason = "stop-file"; break }
            try await Task.sleep(for: .milliseconds(100))
        }
        watchdog.arm(20, phase: "stop-and-finalize")
        try await stream.stopCapture()
        while !delegate.state.snapshot().1 && !delegate.state.snapshot().2 { try await Task.sleep(for: .milliseconds(100)) }
        watchdog.cancel()
        let state = delegate.state.snapshot()
        guard state.0 && state.1 && !state.2, (try? partial.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) ?? 0 > 0 else { throw Failure(reason: "incomplete-recording") }
        try fm.moveItem(at: partial, to: output)
        emit(["event": "COMPLETED", "stop_reason": reason, "elapsed": ProcessInfo.processInfo.systemUptime - start, "utc_epoch": Date().timeIntervalSince1970, "capture_scope": "single-window"])
    }
    @MainActor static func main() async {
        do { try await run() }
        catch let f as Failure { emit(["event": "FAILED", "reason": f.reason, "partial_retained_if_present": true]); exit(2) }
        catch { emit(["event": "FAILED", "reason": "capture-api-or-filesystem-error", "partial_retained_if_present": true]); exit(3) }
    }
}
