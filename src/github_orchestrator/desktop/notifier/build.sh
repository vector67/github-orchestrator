#!/bin/sh
set -eu

if [ "$(uname -s)" != Darwin ]; then
    echo "skipped the notification apps: desktop notifications are macOS only"
    exit 0
fi
if ! xcode-select -p >/dev/null 2>&1; then
    cat >&2 <<MISSING
skipped the notification apps: building them needs the Xcode Command Line Tools
(swiftc, iconutil, codesign). Without them you get no desktop notifications;
everything else works. Install them, then build the apps:

    xcode-select --install
    sh $0
MISSING
    exit 0
fi

here=$(cd "$(dirname "$0")" && pwd)
apps=${1:-"$HOME/Applications"}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

build() {
    badge=$1 name=$2
    app="$apps/$name.app"
    if [ -d "$app" ] && [ -z "$(find "$here" -newer "$app/Contents/Info.plist" -type f)" ]; then
        echo "$name is up to date"
        return
    fi
    [ -x "$work/notify" ] || swiftc -O -o "$work/notify" "$here/notify.swift"
    [ -x "$work/icon" ] || swiftc -O -o "$work/icon" "$here/icon.swift"
    rm -rf "$app" "$work/$badge.iconset"
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$work/$badge.iconset"
    "$work/icon" "$here/badges/$badge.svg" "$work/$badge.iconset"
    iconutil -c icns -o "$app/Contents/Resources/AppIcon.icns" "$work/$badge.iconset"
    cp "$work/notify" "$app/Contents/MacOS/notify"
    cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.vector67.github-orchestrator.$badge</string>
<key>CFBundleName</key><string>$name</string>
<key>CFBundleExecutable</key><string>notify</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
    codesign --force --sign - "$app"
    echo "built $app"
}

mkdir -p "$apps"
build ready "GHO Ready"
build failed "GHO Failed"
build needs-you "GHO Needs You"
build info "GHO Info"
build comments "GHO Comments"
