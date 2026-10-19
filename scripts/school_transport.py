#!/usr/bin/env python3
"""Host-only process mutex and bounded byte transport for the Lean authority.

No school decisions, jobs, learner policies, storage transitions or JSON schema
semantics are implemented here. HTTP is loopback development transport only.
"""
import argparse
import fcntl
import http.server
import os
from pathlib import Path
import subprocess
import sys

LIMIT = 1048576


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("root", type=Path)
    parser.add_argument("request", help="JSON request, serve (stdio), or run (loopback HTTP)")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "authority.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "school authority is already owned by another process\n")
        if args.request not in {"serve", "run"}:
            if len(args.request.encode()) > LIMIT:
                parser.exit(1, "request byte limit exceeded\n")
            # The authority must retain the same open-file-description lock if
            # this byte-transport parent is killed during a real transaction.
            return subprocess.call([str(args.binary.resolve()), str(root), args.request],
                                   pass_fds=(lock.fileno(),))
        with subprocess.Popen([str(args.binary.resolve()), str(root), "serve"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              pass_fds=(lock.fileno(),)) as child:
            def exchange(data):
                if len(data) > LIMIT or b"\n" in data.rstrip(b"\r\n"):
                    raise ValueError("request must be one bounded JSON line")
                child.stdin.write(data.rstrip(b"\r\n") + b"\n")
                child.stdin.flush()
                reply = child.stdout.readline(LIMIT * 32 + 1)
                if not reply or len(reply) > LIMIT * 32:
                    raise RuntimeError("school process closed or exceeded response bound")
                return reply
            try:
                if args.request == "serve":
                    while True:
                        data = sys.stdin.buffer.readline(LIMIT + 1)
                        if not data:
                            break
                        sys.stdout.buffer.write(exchange(data))
                        sys.stdout.buffer.flush()
                else:
                    class Handler(http.server.BaseHTTPRequestHandler):
                        def do_POST(self):
                            try:
                                length = int(self.headers.get("Content-Length", "-1"))
                                if self.path != "/v1/command" or not 0 <= length <= LIMIT:
                                    self.send_error(413)
                                    return
                                reply = exchange(self.rfile.read(length))
                                self.send_response(200)
                                self.send_header("Content-Type", "application/json")
                                self.send_header("Content-Length", str(len(reply)))
                                self.end_headers()
                                self.wfile.write(reply)
                            except (ValueError, RuntimeError, BrokenPipeError):
                                self.send_error(503)
                        def log_message(self, *_args):
                            pass
                    with http.server.HTTPServer(("127.0.0.1", args.port), Handler) as server:
                        server.timeout = 0.2
                        print(f"school transport http://127.0.0.1:{args.port}/v1/command", file=sys.stderr, flush=True)
                        while child.poll() is None:
                            server.handle_request()
            finally:
                if child.stdin and not child.stdin.closed:
                    child.stdin.close()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
