#!/usr/bin/env bash
set -euo pipefail

PORT="${HEADLESS_PORT:-9333}"
PROFILE="${TMPDIR:-/tmp}/frontend-work-chrome-$PORT"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

usage() {
  cat <<'EOF'
helper.sh start [WIDTHxHEIGHT]   launch headless Chrome (default 1440x900, 2x pixels)
helper.sh navigate URL           load URL and wait for it to settle
helper.sh screenshot FILE.png    capture the viewport
helper.sh click SELECTOR         real mouse click at the element's centre
helper.sh hover SELECTOR         move the mouse onto the element
helper.sh type SELECTOR TEXT     focus the element and type TEXT
helper.sh key KEY                press a key (Enter, Escape, ArrowDown, j, 4, ...)
helper.sh js EXPRESSION          evaluate in the page and print the JSON result
helper.sh resize WIDTH HEIGHT    resize the window
helper.sh stop                   quit Chrome

Every command except start and stop prints the page's console output and
uncaught errors raised while it ran, and exits 1 on an uncaught error.
HEADLESS_PORT picks the debugging port (default 9333), CHROME the binary.
EOF
}

start() {
  local size="${1:-1440x900}"
  if curl -sf "http://127.0.0.1:$PORT/json/version" >/dev/null; then
    echo "headless Chrome already listening on $PORT"
    return
  fi
  mkdir -p "$PROFILE"
  "$CHROME" --headless=new --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" --window-size="${size/x/,}" \
    --force-device-scale-factor=2 --no-first-run --no-default-browser-check \
    about:blank >"$PROFILE/chrome.log" 2>&1 &
  for _ in $(seq 50); do
    curl -sf "http://127.0.0.1:$PORT/json/version" >/dev/null && {
      echo "headless Chrome listening on $PORT"
      return
    }
    sleep 0.1
  done
  echo "Chrome did not start; see $PROFILE/chrome.log" >&2
  exit 1
}

stop() {
  pkill -f -- "--remote-debugging-port=$PORT" && echo "stopped" || echo "not running"
}

drive() {
  PORT="$PORT" node --input-type=module -e "$(cat <<'EOF'
import { writeFileSync } from 'node:fs';

const [command, ...args] = process.argv.slice(1);
const port = process.env.PORT;
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = targets.find((one) => one.type === 'page');
if (!page) throw new Error('no page target; run helper.sh start');

const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = reject;
});

let next = 0;
const waiting = new Map();
const listeners = new Map();
const logs = [];
let uncaught = false;
const started = Date.now();
const fresh = (timestamp) => timestamp >= started;

socket.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.id !== undefined) {
    const { resolve, reject } = waiting.get(message.id);
    waiting.delete(message.id);
    message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    return;
  }
  (listeners.get(message.method) ?? []).forEach((listen) => listen(message.params));
};

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++next;
    waiting.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
const once = (method) =>
  new Promise((resolve) => listeners.set(method, [...(listeners.get(method) ?? []), resolve]));
const listen = (method, handle) =>
  listeners.set(method, [...(listeners.get(method) ?? []), handle]);
const settle = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

listen('Runtime.consoleAPICalled', ({ type, args, timestamp }) =>
  fresh(timestamp) && logs.push(`console.${type}: ${args.map((one) => one.value ?? one.description ?? '').join(' ')}`));
listen('Runtime.exceptionThrown', ({ exceptionDetails, timestamp }) => {
  if (!fresh(timestamp)) return;
  uncaught = true;
  logs.push(`Uncaught: ${exceptionDetails.exception?.description ?? exceptionDetails.text}`);
});
listen('Log.entryAdded', ({ entry }) => fresh(entry.timestamp) && logs.push(`${entry.source}.${entry.level}: ${entry.text}`));
await send('Runtime.enable');
await send('Log.enable');
await send('Page.enable');

async function evaluate(expression) {
  const { result, exceptionDetails } = await send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function centre(selector) {
  const point = await evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return null;
    element.scrollIntoView({ block: 'center', inline: 'center' });
    const box = element.getBoundingClientRect();
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  })()`);
  if (!point) throw new Error(`nothing matches ${selector}`);
  return point;
}

const mouse = (type, { x, y }) =>
  send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });

async function key(name) {
  const text = name.length === 1 ? name : name === 'Enter' ? '\r' : undefined;
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: name, code: name, text });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, code: name });
}

const commands = {
  async navigate(url) {
    const loaded = once('Page.loadEventFired');
    await send('Page.navigate', { url });
    await loaded;
    await settle(1000);
  },
  async screenshot(file) {
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(file, Buffer.from(data, 'base64'));
    console.log(file);
  },
  async click(selector) {
    const point = await centre(selector);
    await mouse('mouseMoved', point);
    await mouse('mousePressed', point);
    await mouse('mouseReleased', point);
    await settle(500);
  },
  async hover(selector) {
    await mouse('mouseMoved', await centre(selector));
    await settle(500);
  },
  async type(selector, text) {
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
    await send('Input.insertText', { text });
    await settle(300);
  },
  async key(name) {
    await key(name);
    await settle(500);
  },
  async js(expression) {
    console.log(JSON.stringify(await evaluate(expression), null, 2));
    await settle(200);
  },
  async resize(width, height) {
    const { windowId } = await send('Browser.getWindowForTarget');
    await send('Browser.setWindowBounds', {
      windowId,
      bounds: { width: Number(width), height: Number(height) },
    });
    await settle(300);
  },
};

if (!commands[command]) throw new Error(`unknown command ${command}`);
await commands[command](...args);
logs.forEach((line) => console.error(line));
socket.close();
process.exit(uncaught ? 1 : 0);
EOF
)" -- "$@"
}

case "${1:-}" in
  start) shift; start "$@" ;;
  stop) stop ;;
  navigate | screenshot | click | hover | type | key | js | resize) drive "$@" ;;
  *) usage ;;
esac
