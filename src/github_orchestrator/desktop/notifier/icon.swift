import AppKit

let arguments = CommandLine.arguments

guard arguments.count == 3, let badge = NSImage(contentsOfFile: arguments[1]) else {
    FileHandle.standardError.write("usage: icon <badge.svg> <out.iconset>\n".data(using: .utf8)!)
    exit(1)
}
let iconset = URL(fileURLWithPath: arguments[2])

func tile(_ pixels: Int) -> Data {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                                  bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                  colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let side = CGFloat(pixels)
    let square = NSRect(x: side * 0.1, y: side * 0.1, width: side * 0.8, height: side * 0.8)
    let outline = NSBezierPath(roundedRect: square, xRadius: side * 0.18, yRadius: side * 0.18)
    NSGradient(starting: NSColor(white: 0.98, alpha: 1), ending: NSColor(white: 0.85, alpha: 1))!
        .draw(in: outline, angle: -70)
    NSColor(white: 0, alpha: 0.08).setStroke()
    outline.lineWidth = max(1, side / 256)
    outline.stroke()
    let inset = side * 0.26
    badge.draw(in: NSRect(x: inset, y: inset, width: side - 2 * inset, height: side - 2 * inset))
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using: .png, properties: [:])!
}

for points in [16, 32, 128, 256, 512] {
    try tile(points).write(to: iconset.appendingPathComponent("icon_\(points)x\(points).png"))
    try tile(points * 2).write(to: iconset.appendingPathComponent("icon_\(points)x\(points)@2x.png"))
}
