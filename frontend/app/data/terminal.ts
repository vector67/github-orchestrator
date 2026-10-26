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

const LIGHT_SYSTEM = window.matchMedia('(prefers-color-scheme: light)');

function cursorOf({ cursor }: Colours, light: boolean) {
  return light
    ? { cursor: cursor.light, cursorAccent: cursor.lightText }
    : { cursor: cursor.dark, cursorAccent: cursor.darkText };
}

function leaving(event: KeyboardEvent): boolean {
  return event.ctrlKey && event.shiftKey && event.key === 'ArrowLeft';
}

export interface Colours {
  ground: string;
  text: string;
  cursor: { light: string; lightText: string; dark: string; darkText: string };
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

  private readonly followSystem = (event: MediaQueryListEvent): void => {
    const theme = this.screen.options.theme;
    if (!theme?.background) return;
    this.screen.options.theme = {
      ...theme,
      ...cursorOf(this.colours, event.matches),
    };
  };

  constructor(
    listed: TerminalSession,
    address: string,
    colours: Colours,
    lost: () => void,
  ) {
    this.listed = listed;
    this.address = address;
    this.lost = lost;
    this.colours = colours;
    this.element.className = 'tty-screen';
    this.screen = new Terminal({
      cursorBlink: true,
      fontFamily: MONO,
      fontSize: 12,
      scrollback: 5000,
      screenReaderMode: true,
      theme: this.themeOf(colours),
    });
    this.screen.loadAddon(this.fit);
    LIGHT_SYSTEM.addEventListener('change', this.followSystem);
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

  private themeOf(colours: Colours) {
    if (!colours.ground || !colours.text) return {};
    return {
      background: colours.ground,
      foreground: colours.text,
      ...cursorOf(colours, LIGHT_SYSTEM.matches),
    };
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
    LIGHT_SYSTEM.removeEventListener('change', this.followSystem);
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
