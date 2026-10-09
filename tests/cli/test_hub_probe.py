import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from github_orchestrator.cli import Cli
from github_orchestrator.wiring import make_container


class _Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/api/health":
            self.send_error(404)
            return
        body = b'{"status": "ok", "serves": "hub", "state": "watching"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def hub() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _hub_line(machine, capsys):
    cli: Cli = make_container(machine.environment, machine.home).get(Cli)
    capsys.readouterr()
    cli.main(["status"])
    return capsys.readouterr().out.splitlines()[1]


def test_status_asks_the_hub_itself_whether_it_is_up(machine, capsys, hub):
    machine.configure(f"hub_port = {hub}\n")
    assert _hub_line(machine, capsys) == f"Hub: http://127.0.0.1:{hub}, watching 1 repo"


def test_a_port_nothing_answers_on_is_not_taken_for_a_hub(machine, capsys):
    with ThreadingHTTPServer(("127.0.0.1", 0), _Health) as closed:
        silent = closed.server_address[1]
    machine.configure(f"hub_port = {silent}\n")
    assert _hub_line(machine, capsys) != f"Hub: http://127.0.0.1:{silent}"
