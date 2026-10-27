import { tracked } from '@glimmer/tracking';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import type { TerminalSession } from 'frontend/data/api';
import { tildeOf } from 'frontend/data/address';

export type Standing = 'connecting' | 'live' | 'ended' | 'exited' | 'lost';

const ENDED = 1000;
const GONE = 4404;
const ENCODER = new TextEncoder();
const MONO =
  '"MesloLGS Nerd Font Mono", "MesloLGS NF", ui-monospace, SFMono-Regular, Menlo, "Symbols Nerd Font Mono", monospace';

const DEFAULT_GROUND = 'default';

function leaving(event: KeyboardEvent): boolean {
  return event.ctrlKey && event.shiftKey && event.key === 'ArrowLeft';
}

export interface Scheme {
  ground: string;
  text: string;
}

export interface Colours {
  light: Scheme;
  dark: Scheme;
}

function rgbOf(packed: number): string {
  return `rgb(${(packed >> 16) & 255}, ${(packed >> 8) & 255}, ${packed & 255})`;
}

function mostOf(tally: Map<string, number>): string {
  let most = DEFAULT_GROUND;
  let highest = 0;
  for (const [ground, count] of tally) {
    if (count > highest) [most, highest] = [ground, count];
  }
  return most;
}

function bytesOf(binary: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function exitCodeOf(text: string): number | null {
  try {
    const said = JSON.parse(text) as { exit_code?: unknown };
    return typeof said.exit_code === 'number' ? said.exit_code : null;
  } catch {
    return null;
  }
}

export class Session {
  @tracked standing: Standing = 'connecting';
  @tracked exitCode: number | null = null;
  @tracked leaving = false;

  readonly listed: TerminalSession;
  readonly element: HTMLDivElement = document.createElement('div');

  private readonly screen: Terminal;
  private readonly fit = new FitAddon();
  private readonly address: string;
  private socket: WebSocket;
  private shown = 0;
  private opened = false;
  private leave: () => void = () => {};

  private readonly lost: () => void;
  private readonly colours: Colours;
  private light: boolean;
  private edge: string | null = null;
  private host: HTMLElement | null = null;
  private sampling = false;
  private readonly palette = new Map<number, string>();

  constructor(
    listed: TerminalSession,
    address: string,
    colours: Colours,
    light: boolean,
    lost: () => void,
  ) {
    this.listed = listed;
    this.address = address;
    this.lost = lost;
    this.colours = colours;
    this.light = light;
    this.element.className = 'tty-screen';
    this.screen = new Terminal({
      cursorBlink: true,
      fontFamily: MONO,
      fontSize: 12,
      scrollback: 5000,
      screenReaderMode: true,
      theme: this.themeOf(),
    });
    this.screen.loadAddon(this.fit);
    this.screen.onRender(() => this.sampleSoon());
    this.socket = this.connect(address);
    this.screen.onData((typed) => this.send(ENCODER.encode(typed)));
    this.screen.onBinary((typed) => this.send(bytesOf(typed)));
    this.screen.onResize(() => this.sendSize());
    this.screen.attachCustomKeyEventHandler((event) => {
      if (!leaving(event)) return true;
      if (event.type === 'keydown') this.leave();
      return false;
    });
  }

  get id(): string {
    return this.listed.id;
  }

  get command(): string {
    return this.listed.argv.join(' ');
  }

  get worktree(): string {
    return tildeOf(this.listed.worktree);
  }

  get said(): string {
    if (this.standing === 'connecting') return 'connecting…';
    if (this.standing === 'lost') return 'connection lost';
    if (this.standing === 'ended') return 'ended';
    if (this.standing === 'exited') return `exited ${this.exitCode}`;
    return '';
  }

  mount(into: HTMLElement, leave: () => void): void {
    this.leave = leave;
    this.host = into;
    this.paintHost();
    into.appendChild(this.element);
    if (!this.opened) {
      this.screen.open(this.element);
      this.opened = true;
    }
    this.refit();
    this.screen.focus();
  }

  refit(): void {
    if (this.opened && this.element.isConnected) this.fit.fit();
  }

  paint(light: boolean): void {
    this.light = light;
    this.palette.clear();
    this.screen.options.theme = this.themeOf();
  }

  private themeOf() {
    const { ground, text } = this.light
      ? this.colours.light
      : this.colours.dark;
    if (!ground || !text) return {};
    return {
      background: this.edge ?? ground,
      foreground: text,
      cursor: text,
      cursorAccent: ground,
    };
  }

  private sampleSoon(): void {
    if (this.sampling) return;
    this.sampling = true;
    requestAnimationFrame(() => {
      this.sampling = false;
      const edge = this.edgeOfScreen();
      if (edge === this.edge) return;
      this.edge = edge;
      this.screen.options.theme = this.themeOf();
      this.paintHost();
    });
  }

  private paintHost(): void {
    if (this.host) this.host.style.backgroundColor = this.edge ?? '';
  }

  private edgeOfScreen(): string | null {
    const buffer = this.screen.buffer.active;
    const { cols, rows } = this.screen;
    const tally = new Map<string, number>();
    const count = (x: number, y: number) => {
      const cell = buffer.getLine(buffer.viewportY + y)?.getCell(x);
      if (!cell) return;
      const ground = cell.isBgRGB()
        ? rgbOf(cell.getBgColor())
        : cell.isBgPalette()
          ? this.paletteColour(cell.getBgColor())
          : DEFAULT_GROUND;
      tally.set(ground, (tally.get(ground) ?? 0) + 1);
    };
    for (let x = 0; x < cols; x++) {
      count(x, 0);
      count(x, rows - 1);
    }
    for (let y = 1; y < rows - 1; y++) {
      count(0, y);
      count(cols - 1, y);
    }
    const most = mostOf(tally);
    return most === DEFAULT_GROUND ? null : most;
  }

  private paletteColour(index: number): string {
    const known = this.palette.get(index);
    if (known) return known;
    const probe = document.createElement('span');
    probe.className = `xterm-bg-${index}`;
    this.screen.element?.querySelector('.xterm-rows')?.appendChild(probe);
    const colour = getComputedStyle(probe).backgroundColor;
    probe.remove();
    this.palette.set(index, colour);
    return colour;
  }

  private connect(address: string): WebSocket {
    const socket = new WebSocket(address);
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => this.connected();
    socket.onmessage = (event: MessageEvent) => this.heard(event.data);
    socket.onclose = (event: CloseEvent) => this.closed(event.code);
    return socket;
  }

  private connected(): void {
    this.standing = 'live';
    this.sendSize();
  }

  private heard(data: unknown): void {
    if (data instanceof ArrayBuffer) {
      this.shown += data.byteLength;
      this.screen.write(new Uint8Array(data));
    } else if (typeof data === 'string') {
      this.exitCode = exitCodeOf(data);
    }
  }

  resume(): void {
    this.standing = 'connecting';
    this.socket = this.connect(`${this.address}?after=${this.shown}`);
  }

  gone(): void {
    this.standing = 'ended';
  }

  private closed(code: number): void {
    if (this.exitCode !== null) {
      this.standing = 'exited';
      this.element.setAttribute('data-exited', '');
      return;
    }
    this.standing = code === ENDED || code === GONE ? 'ended' : 'lost';
    if (this.standing === 'lost') this.lost();
  }

  close(): void {
    this.leaving = true;
    this.screen.dispose();
    this.element.remove();
  }

  private send(data: Uint8Array<ArrayBuffer> | string): void {
    if (this.standing === 'live') this.socket.send(data);
  }

  private sendSize(): void {
    this.send(
      JSON.stringify({ columns: this.screen.cols, rows: this.screen.rows }),
    );
  }
}
