#!/bin/sh
set -u

REPO="vector67/github-orchestrator"
RELEASES_API="https://api.github.com/repos/$REPO/releases"
UV_INSTALLER="https://astral.sh/uv/install.sh"
CLAUDE_INSTALLER="https://claude.ai/install.sh"
CODEX_APP="/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
CODEX_INSTALL="npm install -g @openai/codex"
GH_RELEASES="https://github.com/cli/cli/releases"
TOOL_PYTHON="3.12"
BIN="$HOME/.local/bin"
CONFIG_FOLDER="$HOME/.config/github-orchestrator"
LABEL="com.github-orchestrator.watcher"
DEFAULT_PORT=8720

YES=${GITHUB_ORCHESTRATOR_YES:-}
NOTIFIER=${GITHUB_ORCHESTRATOR_NOTIFIER:-}
VERSION=${GITHUB_ORCHESTRATOR_VERSION:-}
NO_PATH=${GITHUB_ORCHESTRATOR_NO_PATH:-}
NO_OPEN=${GITHUB_ORCHESTRATOR_NO_OPEN:-}
WHEEL=${GITHUB_ORCHESTRATOR_WHEEL:-}
LINGER=${GITHUB_ORCHESTRATOR_LINGER:-}
SKILL=${GITHUB_ORCHESTRATOR_SKILL:-}
AGENT=${GITHUB_ORCHESTRATOR_AGENT:-}

usage() {
    cat <<'USAGE'
github-orchestrator installer

Usage: install.sh [options]

  -y, --yes          answer yes to every install question; notifications stay off
  --agent claude|codex
                     the agent that works on your pull requests: claude (Claude
                     Code, the default) or codex (the Codex CLI)
  --notifier         build the macOS notification apps without asking
  --linger           keep the watcher running after you log out (Linux)
  --skill            install the rebase-on-main skill for the agent without asking
  --no-skill         leave the rebase-on-main skill out
  --version X        install release X, not the newest
  --no-modify-path   never edit shell profiles; print the line to add
  --no-open          start the service but do not open the browser
  --wheel URL|PATH   install this wheel instead of a release's
  -h, --help         show this help

Each option has an environment twin: GITHUB_ORCHESTRATOR_YES=1,
GITHUB_ORCHESTRATOR_NOTIFIER=1, GITHUB_ORCHESTRATOR_LINGER=1,
GITHUB_ORCHESTRATOR_VERSION=X, GITHUB_ORCHESTRATOR_NO_PATH=1,
GITHUB_ORCHESTRATOR_NO_OPEN=1, GITHUB_ORCHESTRATOR_WHEEL=...,
GITHUB_ORCHESTRATOR_AGENT=claude|codex and GITHUB_ORCHESTRATOR_SKILL=yes|no.
Under -y the agent is claude unless chosen, the skill is installed when it is
missing, and one that differs from this version's is left alone.
GITHUB_ORCHESTRATOR_GITHUB_TOKEN, when set, is sent with the requests that
download the release.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        -y | --yes) YES=1 ;;
        --notifier) NOTIFIER=1 ;;
        --linger) LINGER=1 ;;
        --skill) SKILL=yes ;;
        --agent)
            [ $# -gt 1 ] || { echo "--agent needs claude or codex" >&2; exit 2; }
            AGENT=$2
            shift
            ;;
        --agent=*) AGENT=${1#--agent=} ;;
        --no-skill) SKILL=no ;;
        --version)
            [ $# -gt 1 ] || { echo "--version needs a version, such as 0.1.0" >&2; exit 2; }
            VERSION=$2
            shift
            ;;
        --version=*) VERSION=${1#--version=} ;;
        --no-modify-path) NO_PATH=1 ;;
        --no-open) NO_OPEN=1 ;;
        --wheel)
            [ $# -gt 1 ] || { echo "--wheel needs a URL or a path" >&2; exit 2; }
            WHEEL=$2
            shift
            ;;
        --wheel=*) WHEEL=${1#--wheel=} ;;
        -h | --help) usage; exit 0 ;;
        *) echo "unknown option: $1 (install.sh --help lists them)" >&2; exit 2 ;;
    esac
    shift
done
VERSION=${VERSION#v}
case "$SKILL" in
    "" | yes | no) ;;
    *) echo "GITHUB_ORCHESTRATOR_SKILL is yes or no, not $SKILL" >&2; exit 2 ;;
esac
case "$AGENT" in
    "" | claude | codex) ;;
    *) echo "the agent is claude or codex, not $AGENT" >&2; exit 2 ;;
esac

say() { printf '%s\n' "$*"; }
step() { printf '==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
fail() { printf '%s\n' "$*" >&2; exit 1; }

if (: </dev/tty) 2>/dev/null; then TTY=1; else TTY=; fi
WORK=$(mktemp -d 2>/dev/null || mktemp -d -t github-orchestrator)
trap 'rm -rf "$WORK"' EXIT
ORIGINAL_PATH=$PATH
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) PATH="$PATH:$BIN"; export PATH ;;
esac

asked() {
    question=$1
    default=$2
    if [ -z "$TTY" ]; then
        return 1
    fi
    printf '%s ' "$question" >/dev/tty
    IFS= read -r answer </dev/tty || answer=
    case "$answer" in
        "") [ "$default" = y ] ;;
        [Yy] | [Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

agreed() {
    if [ -n "$YES" ]; then
        return 0
    fi
    asked "$1 [Y/n]" y
}

on_path() {
    case ":$ORIGINAL_PATH:" in
        *":$1:"*) return 0 ;;
        *) return 1 ;;
    esac
}

use_bin() {
    mkdir -p "$BIN"
    case ":$PATH:" in
        *":$BIN:"*) ;;
        *) PATH="$BIN:$PATH"; export PATH ;;
    esac
}

token() {
    if [ -n "${GITHUB_ORCHESTRATOR_GITHUB_TOKEN:-}" ]; then
        printf '%s' "$GITHUB_ORCHESTRATOR_GITHUB_TOKEN"
    elif [ -n "${GH_TOKEN:-}" ]; then
        printf '%s' "$GH_TOKEN"
    elif command -v gh >/dev/null 2>&1; then
        gh auth token 2>/dev/null
    fi
}

api_get() {
    url=$1
    out=$2
    accept=$3
    secret=$(token)
    if [ -n "$secret" ]; then
        printf 'header = "Authorization: Bearer %s"\n' "$secret" >"$WORK/auth"
        curl -fsSL --retry 3 -H "Accept: $accept" -H "X-GitHub-Api-Version: 2022-11-28" \
            -K "$WORK/auth" -o "$out" "$url"
        got=$?
        rm -f "$WORK/auth"
        return $got
    fi
    curl -fsSL --retry 3 -H "Accept: $accept" -H "X-GitHub-Api-Version: 2022-11-28" \
        -o "$out" "$url"
}

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d ' ' -f 1
    else
        sha256sum "$1" | cut -d ' ' -f 1
    fi
}

say "github-orchestrator installer"
say ""
OS=$(uname -s)
ARCH=$(uname -m)
case "$OS/$ARCH" in
    Darwin/arm64 | Darwin/x86_64) PLATFORM=macos ;;
    Linux/x86_64 | Linux/aarch64 | Linux/arm64) PLATFORM=linux ;;
    *) fail "github-orchestrator runs on macOS (arm64, x86_64) and Linux (x86_64, aarch64), not $OS on $ARCH." ;;
esac
if [ "$PLATFORM" = linux ] && ! systemctl --user show-environment >/dev/null 2>&1; then
    fail "systemctl --user cannot reach a user manager here, so the watcher cannot run as a
service on this machine. Log in to a desktop session (or one with XDG_RUNTIME_DIR set) and
run the installer again, or install by hand and run the watcher in a terminal with
github-orchestrator start --foreground."
fi

CONFIG="$CONFIG_FOLDER/config.toml"

configured_command() {
    [ -f "$CONFIG" ] || return 0
    sed -En 's/^(agent|claude)_command *= *"([^" ]*).*/\2/p' "$CONFIG" | head -n 1
}

configured_agent() {
    [ -f "$CONFIG" ] || return 0
    sed -En 's/^agent *= *"([^"]*)".*/\1/p' "$CONFIG" | head -n 1
}

chosen_agent() {
    if [ -n "$YES" ] || [ -z "$TTY" ]; then
        echo claude
        return
    fi
    while :; do
        printf '%s ' "Which agent works on your pull requests: claude (Claude Code) or codex (the Codex CLI)? [claude]" >/dev/tty
        IFS= read -r answer </dev/tty || answer=
        case "$answer" in
            "" | claude) echo claude; return ;;
            codex) echo codex; return ;;
        esac
    done
}

CONFIGURED_AGENT=$(configured_agent)
if [ -z "$AGENT" ]; then
    AGENT=${CONFIGURED_AGENT:-$(chosen_agent)}
fi
case "$AGENT" in
    codex) AGENT_NAME="Codex"; SKILLS_DIR="~/.agents/skills" ;;
    *) AGENT_NAME="Claude Code"; SKILLS_DIR="~/.claude/skills" ;;
esac
AGENT_COMMAND=$(configured_command)
MISSING=
WANTS_CLT=
row() { printf '  %-8s %s\n' "$1" "$2"; }

if [ "$PLATFORM" = macos ]; then
    say "Checking this Mac:"
    row ok "macOS $(sw_vers -productVersion 2>/dev/null) ($ARCH)"
    if xcode-select -p >/dev/null 2>&1; then
        row ok "$(git --version 2>/dev/null | sed 's/^git version /git /') (Command Line Tools)"
    else
        row missing "git         commits and worktrees; Apple's Command Line Tools (xcode-select --install)"
        MISSING="$MISSING clt"
        WANTS_CLT=1
    fi
else
    DISTRO=$(sed -n 's/^PRETTY_NAME="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /etc/os-release 2>/dev/null)
    say "Checking this machine:"
    row ok "${DISTRO:-Linux} ($ARCH)"
    if command -v git >/dev/null 2>&1; then
        row ok "$(git --version | sed 's/^git version /git /')"
    else
        row missing "git         commits and worktrees"
        say ""
        say "git comes from your distribution, and installing it needs sudo, which this"
        say "installer never uses. Install it, then run this installer again:"
        if command -v apt-get >/dev/null 2>&1; then note "sudo apt install git"
        elif command -v dnf >/dev/null 2>&1; then note "sudo dnf install git"
        elif command -v pacman >/dev/null 2>&1; then note "sudo pacman -S git"
        elif command -v zypper >/dev/null 2>&1; then note "sudo zypper install git"
        else note "your package manager's git package"
        fi
        exit 1
    fi
fi
if command -v uv >/dev/null 2>&1; then
    row ok "$(uv --version 2>/dev/null)"
else
    row missing "uv          runs the install; from astral.sh"
    MISSING="$MISSING uv"
fi
if command -v gh >/dev/null 2>&1; then
    row ok "$(gh --version 2>/dev/null | head -n 1 | sed 's/^gh version \([^ ]*\).*/gh \1/')"
else
    row missing "gh          talks to GitHub; from github.com/cli/cli releases"
    MISSING="$MISSING gh"
fi
if [ "$AGENT" = codex ]; then
    if [ -z "$AGENT_COMMAND" ]; then
        if command -v codex >/dev/null 2>&1; then
            AGENT_COMMAND=codex
        elif [ -x "$CODEX_APP" ]; then
            AGENT_COMMAND=$CODEX_APP
        fi
    fi
    if [ -n "$AGENT_COMMAND" ] && command -v "$AGENT_COMMAND" >/dev/null 2>&1; then
        row ok "$("$AGENT_COMMAND" --version 2>/dev/null | head -n 1) ($AGENT_COMMAND)"
    else
        row missing "codex       runs the agents; this installer does not install it"
        say ""
        say "Install codex, then run this installer again. Either of these brings it:"
        note "the ChatGPT app for macOS, which carries codex at $CODEX_APP"
        note "$CODEX_INSTALL"
        exit 1
    fi
else
    CLAUDE=${AGENT_COMMAND:-claude}
    if command -v "$CLAUDE" >/dev/null 2>&1; then
        row ok "$CLAUDE $("$CLAUDE" --version 2>/dev/null | head -n 1 | cut -d ' ' -f 1)"
    elif [ "$CLAUDE" = claude ]; then
        row missing "claude      runs the agents; Anthropic's installer"
        MISSING="$MISSING claude"
    else
        row missing "$CLAUDE  your agent_command; install it, then run this installer again"
        exit 1
    fi
fi
if [ "$PLATFORM" = linux ]; then
    if command -v notify-send >/dev/null 2>&1; then
        row ok "notify-send (desktop notifications)"
    else
        row optional "notify-send desktop notifications; your distribution's libnotify package (libnotify-bin on Debian and Ubuntu)"
    fi
fi
say ""

by_hand() {
    for item in $MISSING; do
        case "$item" in
            clt) note "xcode-select --install" ;;
            uv) note "curl -LsSf $UV_INSTALLER | sh" ;;
            gh)
                if [ "$PLATFORM" = macos ]; then
                    note "download the macOS zip from $GH_RELEASES/latest and put its bin/gh in ~/.local/bin"
                else
                    note "download the linux_amd64 or linux_arm64 tarball from $GH_RELEASES/latest and put its bin/gh in ~/.local/bin"
                fi
                ;;
            claude) note "curl -fsSL $CLAUDE_INSTALLER | bash" ;;
        esac
    done
}

names=
for item in $MISSING; do
    case "$item" in clt) item="the Command Line Tools" ;; esac
    if [ -z "$names" ]; then names=$item; else names="$names, $item"; fi
done
names=$(printf '%s' "$names" | sed 's/\(.*\), /\1 and /')
if [ -z "$YES" ] && [ -z "$TTY" ]; then
    say "With no terminal to ask on, nothing was changed. This would install${names:+ $names and}"
    say "github-orchestrator, then start its watcher. Run it again with a terminal, or"
    say "answer yes to everything with: curl -LsSf https://github.com/$REPO/releases/latest/download/install.sh | sh -s -- -y"
    if [ -n "$MISSING" ]; then
        say "Or install the requirements by hand first:"
        by_hand
    fi
    exit 1
fi
if [ -n "$MISSING" ]; then
    if ! agreed "Install $names now?"; then
        say "Nothing was installed. Every item is needed; install them by hand, then"
        say "run this installer again:"
        by_hand
        exit 1
    fi
fi

await_clt() {
    waited=0
    note "Apple's installer asks in its own window; waiting for it to finish."
    while ! xcode-select -p >/dev/null 2>&1; do
        if [ "$waited" -ge 1800 ]; then
            fail "The Command Line Tools did not finish within 30 minutes; run this installer again once they have."
        fi
        sleep 5
        waited=$((waited + 5))
    done
}

install_gh() {
    tag=$(curl -fsSI -o /dev/null -w '%{redirect_url}' "$GH_RELEASES/latest" | sed 's#.*/tag/##' | tr -d '\r')
    version=${tag#v}
    [ -n "$version" ] || fail "Could not find the newest gh release at $GH_RELEASES/latest."
    case "$PLATFORM/$ARCH" in
        macos/arm64) asset="gh_${version}_macOS_arm64.zip" ;;
        macos/x86_64) asset="gh_${version}_macOS_amd64.zip" ;;
        linux/x86_64) asset="gh_${version}_linux_amd64.tar.gz" ;;
        *) asset="gh_${version}_linux_arm64.tar.gz" ;;
    esac
    step "Installing gh $version into ~/.local/bin"
    note "It talks to GitHub for the watcher and the agents."
    curl -fsSL --retry 3 -o "$WORK/$asset" "$GH_RELEASES/download/$tag/$asset" \
        || fail "Could not download $GH_RELEASES/download/$tag/$asset."
    curl -fsSL --retry 3 -o "$WORK/checksums.txt" \
        "$GH_RELEASES/download/$tag/gh_${version}_checksums.txt" \
        || fail "Could not download gh's checksums."
    expected=$(grep " $asset\$" "$WORK/checksums.txt" | cut -d ' ' -f 1)
    [ -n "$expected" ] && [ "$(sha256_of "$WORK/$asset")" = "$expected" ] \
        || fail "$asset does not match gh's published checksum; nothing was installed."
    case "$asset" in
        *.zip) (cd "$WORK" && unzip -q "$asset") ;;
        *) tar -xzf "$WORK/$asset" -C "$WORK" ;;
    esac
    use_bin
    cp "$WORK/${asset%.zip}/bin/gh" "$BIN/gh" 2>/dev/null \
        || cp "$WORK/${asset%.tar.gz}/bin/gh" "$BIN/gh" \
        || fail "Could not find bin/gh inside $asset."
    chmod +x "$BIN/gh"
}

for item in $MISSING; do
    case "$item" in
        uv)
            step "Installing uv"
            note "It installs github-orchestrator and the Python it runs on."
            if [ -n "$NO_PATH" ]; then
                curl -LsSf "$UV_INSTALLER" | UV_NO_MODIFY_PATH=1 sh || fail "The uv installer failed."
            else
                curl -LsSf "$UV_INSTALLER" | sh || fail "The uv installer failed."
            fi
            use_bin
            ;;
    esac
done
for item in $MISSING; do
    case "$item" in
        clt)
            step "Installing Apple's Command Line Tools"
            note "They bring git."
            xcode-select --install >/dev/null 2>&1
            await_clt
            ;;
        gh) install_gh ;;
        claude)
            step "Installing claude"
            note "Claude Code runs the agents that answer review comments."
            curl -fsSL "$CLAUDE_INSTALLER" | bash || fail "Anthropic's installer failed."
            use_bin
            ;;
    esac
done
command -v uv >/dev/null 2>&1 || fail "uv is still not on PATH; open a new terminal and run this installer again."

if ! gh auth status >/dev/null 2>&1; then
    if [ -z "$TTY" ]; then
        fail "gh has no login yet, and there is no terminal to log in on. Run gh auth login
(or set GH_TOKEN), then run this installer again."
    fi
    step "gh has no login yet. Logging in to GitHub"
    note "(gh auth login runs here; it opens github.com in your browser)"
    gh auth login --web --git-protocol https </dev/tty >/dev/tty 2>&1
    gh auth status >/dev/null 2>&1 \
        || fail "gh is still not logged in. Run gh auth login --web --git-protocol https, then run this installer again."
fi

OLDER=
link=$BIN/github-orchestrator
if [ -L "$link" ]; then
    case "$(readlink "$link")" in
        */.venv/bin/github-orchestrator) OLDER="$link links into a checkout ($(readlink "$link"))" ;;
    esac
fi
plist="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ "$PLATFORM" = macos ] && [ -f "$plist" ] && grep -q -e '--project' -e '/.venv/bin/python' "$plist"; then
    OLDER="${OLDER:+$OLDER; }the LaunchAgent runs a checkout"
fi
if [ "$PLATFORM" = linux ] && crontab -l 2>/dev/null | grep -q github_orchestrator; then
    OLDER="${OLDER:+$OLDER; }the crontab runs a checkout"
fi
if [ -n "$OLDER" ]; then
    say "An older install is here: $OLDER."
    if [ -z "$YES" ] && [ -z "$TTY" ]; then
        fail "With no terminal to ask on, it was left alone. Run again with -y to replace it."
    fi
    agreed "Replace it with the installed tool? Its config and data move over." \
        || fail "Left the older install as it is."
    if [ -L "$link" ]; then
        rm -f "$link"
    fi
fi

wheel_of() {
    tr '\n' ' ' <"$1" | tr '{' '\n' \
        | sed -n 's/.*"url": *"\([^"]*\)".*"name": *"\([^"]*\.whl\)".*/\1 \2/p' | head -n 1
}

if [ -n "$WHEEL" ]; then
    case "$WHEEL" in
        http://* | https://*)
            name=$(basename "${WHEEL%%\?*}")
            curl -fsSL --retry 3 -o "$WORK/$name" "$WHEEL" || fail "Could not download $WHEEL."
            wheel="$WORK/$name"
            ;;
        *) wheel=$WHEEL ;;
    esac
    [ -f "$wheel" ] || fail "There is no wheel at $wheel."
else
    if [ -n "$VERSION" ]; then
        release_url="$RELEASES_API/tags/v$VERSION"
    else
        release_url="$RELEASES_API/latest"
    fi
    api_get "$release_url" "$WORK/release.json" "application/vnd.github+json" \
        || fail "Could not look up the release at $release_url."
    set -- $(wheel_of "$WORK/release.json")
    [ $# -eq 2 ] || fail "The release at $release_url has no wheel."
    api_get "$1" "$WORK/$2" "application/octet-stream" || fail "Could not download $2."
    wheel="$WORK/$2"
fi
wheel_version=$(basename "$wheel" | cut -d - -f 2)
step "Installing github-orchestrator $wheel_version"
note "uv puts it in its own environment, with a Python of its own if it needs one."
uv tool install --force --python "$TOOL_PYTHON" "$wheel" || fail "uv tool install failed."
TOOL_BIN=$(uv tool dir --bin)
COMMAND="$TOOL_BIN/github-orchestrator"
[ -x "$COMMAND" ] || fail "uv installed github-orchestrator, but $COMMAND is missing."

if ! on_path "$TOOL_BIN"; then
    if [ -z "$NO_PATH" ] && agreed "Add $TOOL_BIN to your shell's PATH, so github-orchestrator, gh and $AGENT are found?"; then
        uv tool update-shell >/dev/null 2>&1 && note "Added; open a new terminal to pick it up."
    else
        say "Add this line to your shell profile to run github-orchestrator by name:"
        note "export PATH=\"$TOOL_BIN:\$PATH\""
    fi
fi
use_bin

remember_agent() {
    if [ "$CONFIGURED_AGENT" = "$AGENT" ]; then
        return
    fi
    if [ -z "$CONFIGURED_AGENT" ] && [ "$AGENT" = claude ]; then
        return
    fi
    step "Writing agent = \"$AGENT\" into $CONFIG"
    mkdir -p "$CONFIG_FOLDER"
    if [ -n "$CONFIGURED_AGENT" ]; then
        sed "s/^agent *= *\"[^\"]*\"/agent = \"$AGENT\"/" "$CONFIG" >"$WORK/config.toml"
    else
        {
            printf 'agent = "%s"\n' "$AGENT"
            if [ -f "$CONFIG" ]; then cat "$CONFIG"; fi
        } >"$WORK/config.toml"
    fi
    cat "$WORK/config.toml" >"$CONFIG" || fail "Could not write $CONFIG."
}

remember_agent

step "Starting the watcher"
note "It runs as a $([ "$PLATFORM" = macos ] && echo LaunchAgent || echo systemd user unit) and serves the board."
"$COMMAND" start --from-installer || fail "The watcher did not start; github-orchestrator doctor says why."

build_notifier() {
    if ! xcrun --find swiftc >/dev/null 2>&1 || ! xcrun --find codesign >/dev/null 2>&1; then
        say "Building them needs Apple's Command Line Tools."
        if [ -z "$NOTIFIER" ] && ! asked "Install them now? [Y/n]" y; then
            return 1
        fi
        xcode-select --install >/dev/null 2>&1
        await_clt
    fi
    step "Building the notification apps (about a minute)"
    python="$(uv tool dir)/github-orchestrator/bin/python"
    script=$("$python" -c 'import pathlib, github_orchestrator.desktop as d; print(pathlib.Path(d.__file__).parent / "notifier" / "build.sh")')
    sh "$script"
}

if [ "$PLATFORM" = macos ]; then
    if [ -n "$NOTIFIER" ] || { [ -z "$YES" ] && asked "Would you like desktop notifications when a PR needs you? [Y/n]" y; }; then
        build_notifier || say "No notifications for now; github-orchestrator doctor names the command that adds them."
    else
        say "No desktop notifications; github-orchestrator doctor names the command that adds them later."
    fi
elif [ -n "$LINGER" ] || { [ -z "$YES" ] && asked "Keep the watcher running after you log out? [y/N]" n; }; then
    loginctl enable-linger >/dev/null 2>&1 \
        || say "loginctl enable-linger needs more rights here; run: sudo loginctl enable-linger $(id -un)"
fi

offer_skill() {
    case "$("$COMMAND" skill --status 2>/dev/null)" in
        missing)
            if [ "$SKILL" != no ] && { [ "$SKILL" = yes ] \
                || agreed "Install the rebase-on-main skill for $AGENT_NAME (agents use it to rebase PRs)?"; }; then
                step "Installing the rebase-on-main skill into $SKILLS_DIR"
                "$COMMAND" skill || say "The skill was not installed; github-orchestrator skill tries again."
            else
                say "No rebase-on-main skill; github-orchestrator skill installs it later."
            fi
            ;;
        different)
            say "The rebase-on-main skill in $SKILLS_DIR differs from this version's."
            if [ "$SKILL" != no ] && [ -z "$YES" ] && asked "Replace it with this version's? [y/N]" n; then
                "$COMMAND" skill --replace
            else
                say "It was left alone; github-orchestrator skill --replace puts this version's in its place."
            fi
            ;;
    esac
}

offer_skill

if [ -z "$NO_OPEN" ]; then
    "$COMMAND" open
else
    port=$(sed -n 's/^hub_port *= *\([0-9]*\).*/\1/p' "$CONFIG_FOLDER/config.toml" 2>/dev/null | head -n 1)
    say "The board is at http://127.0.0.1:${port:-$DEFAULT_PORT}"
fi
