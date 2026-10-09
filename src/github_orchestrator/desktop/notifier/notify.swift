import AppKit
import UserNotifications

let arguments = CommandLine.arguments

func argument(_ flag: String) -> String {
    guard let index = arguments.firstIndex(of: flag), index + 1 < arguments.count else { return "" }
    return arguments[index + 1]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write("\(message)\n".data(using: .utf8)!)
    exit(1)
}

let linkKey = "link"
let clickWait: TimeInterval = 10

final class Poster: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard arguments.contains("--id") else {
            DispatchQueue.main.asyncAfter(deadline: .now() + clickWait) { exit(0) }
            return
        }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, error in
            guard granted else { fail("not authorised: \(error?.localizedDescription ?? "denied")") }
            let identifier = argument("--id")
            center.getDeliveredNotifications { delivered in
                if delivered.contains(where: { $0.request.identifier == identifier }) { exit(0) }
                let content = UNMutableNotificationContent()
                content.title = argument("--title")
                content.body = argument("--body")
                if arguments.contains("--open") { content.userInfo = [linkKey: argument("--open")] }
                let request = UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
                center.add(request) { error in
                    if let error { fail("\(error)") }
                    exit(0)
                }
            }
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if response.actionIdentifier == UNNotificationDefaultActionIdentifier,
           let link = response.notification.request.content.userInfo[linkKey] as? String,
           let url = URL(string: link) {
            NSWorkspace.shared.open(url)
        }
        completionHandler()
        exit(0)
    }
}

let application = NSApplication.shared
let poster = Poster()
application.delegate = poster
application.setActivationPolicy(.accessory)
application.run()
