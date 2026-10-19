#!/usr/bin/env python3
"""Host-only process mutex, lifecycle controls and bounded Lean byte transport.

School decisions, authorization, jobs, clocks and commit policy execute in Lean.
HTTP remains an owner-local loopback binding. Lifecycle metadata is diagnostic OS
ownership, never a source of school capability or a substitute for admission.
"""
import argparse
import contextlib
import fcntl
import hashlib
import http.server
import json
import os
from pathlib import Path
import signal
import secrets
import stat
import select
import subprocess
import sys
import time
import urllib.request
import urllib.parse

LIMIT = 1048576
SHORTCUTS = {"status": "status", "stop": "stop", "backup": "export", "restore": "restore", "fork": "clone", "pair": "admission-issue"}
SHORTCUTS.update({"publish-training": "training-publish", "models": "models", "select-model": "model-select", "rollback-model": "model-rollback"})
SHORTCUTS["revoke-pair"] = "admission-revoke"


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def start_ticks(pid):
    # The comm field can contain spaces and parentheses.
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])


def runtime(root):
    try:
        value = json.loads((root / "transport.json").read_text())
        if value["bootId"] != boot_id() or value["startTicks"] != start_ticks(value["pid"]):
            return None
        return value
    except (OSError, ValueError, KeyError):
        return None


def post(port, data, timeout=10):
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/command", data=data,
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as reply:
        result = reply.read(LIMIT * 32 + 1)
        if len(result) > LIMIT * 32:
            raise ValueError("response byte limit exceeded")
        return result


def credential_binding(path):
    """Read only a private handoff; no secret appears in child args or logs."""
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError("credential must be an owned private mode0600 regular file")
        raw = handle.read(4097)
    if len(raw) > 4096:
        raise ValueError("credential exceeds4096-byte bound")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("credential must be a handoff object")
    endpoint = urllib.parse.urlsplit(value.get("endpoint", ""))
    if (value.get("schema") != "lemma-school-credential/1" or endpoint.scheme != "http" or
            endpoint.hostname not in {"127.0.0.1", "localhost", "::1"} or endpoint.path != "/v1/client" or
            endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or not endpoint.port):
        raise ValueError("credential requires a supported loopback /v1/client endpoint")
    secret = value.get("token", "")
    if not isinstance(secret, str) or len(secret) != 64 or any(char not in "0123456789abcdef" for char in secret):
        raise ValueError("credential has an invalid private admission secret")
    return value, endpoint


def credential_post(credential, data, timeout=30):
    if len(data) > LIMIT:
        raise ValueError("protected request byte limit exceeded")
    request = urllib.request.Request(credential["endpoint"], data=data, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + credential["token"]})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as reply:
        result = reply.read(LIMIT*32+1)
    if len(result) > LIMIT*32:
        raise ValueError("protected response byte limit exceeded")
    return result


def emit_reply(reply):
    sys.stdout.buffer.write(reply)
    return 0 if json.loads(reply).get("ok") else 1


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def shortcut(args, parser):
    if not args.school or not args.actor:
        parser.error(f"{args.request} requires --school ID --actor ID")
    value = {"op": SHORTCUTS.get(args.request, "status"), "school": args.school, "actor": args.actor}
    if args.request in {"backup", "fork"}:
        if not args.to:
            parser.error(f"{args.request} requires --to PATH")
        value["to"] = str(args.to.resolve())
    if args.request == "restore":
        if not args.source:
            parser.error("restore requires --from PATH (original authority must be stopped)")
        value.update({"from": str(args.source.resolve()), "offline": True})
    if args.request == "fork":
        if not args.new_school or not args.new_deployment:
            parser.error("fork requires --new-school ID --new-deployment ID")
        value.update(newSchool=args.new_school, newDeployment=args.new_deployment)
    if args.request in {"select-model", "rollback-model"}:
        if args.version is None:
            parser.error(f"{args.request} requires --version NUMBER")
        value.update(version=args.version, reason=args.reason)
    if args.request == "revoke-pair":
        if not args.token_hash:
            parser.error("revoke-pair requires --token-hash SHA256")
        value["tokenHash"] = args.token_hash
    if args.request == "publish-training":
        if not args.directory or not args.dataset or not args.checkpoint or not args.rights:
            parser.error("publish-training requires --directory OUTPUT --dataset DATASET --checkpoint FILE --rights PROVENANCE")
        value.update(directory=str(args.directory.resolve()), dataset=str(args.dataset.resolve()),
                     checkpoint=str(args.checkpoint.resolve()), rights=args.rights, reusable=args.reusable)
        if args.configuration:
            value["configuration"] = str(args.configuration.resolve())
    return json.dumps(value).encode()


def pair(args, parser):
    if not args.learner or not args.to:
        parser.error("pair requires --learner ID --to NEW_PRIVATE_TOKEN_FILE")
    if args.to.exists():
        parser.error("pair token destination must not already exist")
    secret = secrets.token_hex(32)
    digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
    request = json.loads(shortcut(args, parser))
    request.update(learner=args.learner, tokenHash=digest, lifetimeMs=args.lifetime_ms)
    # Persist the private handoff before admission. A failed admission leaves a
    # visibly unadmitted credential; it never acknowledges access that was lost.
    args.to.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.to, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"schema": "lemma-school-credential/1", "school": args.school,
                   "learner": args.learner, "token": secret,
                   "endpoint": f"http://127.0.0.1:{args.client_port or args.port}/v1/client"}, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(args.to.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return json.dumps(request).encode(), digest


def launch(args, root, data, parser):
    if runtime(root):
        parser.exit(1, "school transport is already running; use status\n")
    log_path = root / "transport.log"
    command = [sys.executable, str(Path(__file__).resolve()), "--binary", str(args.binary.resolve()),
               "--barrier-helper", str(args.barrier_helper), str(root), "run", "--port", str(args.port)]
    if args.client_port:
        command.extend(["--client-port", str(args.client_port)])
    for origin in args.browser_origin:
        command.extend(["--browser-origin", origin])
    with log_path.open("ab") as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if child.poll() is not None:
                parser.exit(1, f"school launch failed; inspect {log_path}\n")
            running = runtime(root)
            if running and running["pid"] == child.pid:
                try:
                    reply = post(args.port, data, timeout=1)
                    admitted = json.loads(reply)
                    if not admitted.get("ok"):
                        raise ValueError(admitted.get("error", "status admission failed"))
                    return emit_reply(reply)
                except (OSError, urllib.error.URLError):
                    pass
            time.sleep(0.05)
        raise RuntimeError(f"school launch deadline exceeded; inspect {log_path}")
    except BaseException:
        # Only the process group started by this invocation belongs to us.
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--barrier-helper", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("request", help="JSON, serve, run, client-run, start, status, stop, backup, restore, fork, or pair")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--client-port", type=int, help="separate protected loopback learner endpoint alongside run/start")
    parser.add_argument("--browser-origin", action="append", default=[], help="exact opt-in loopback browser origin for learner CORS only")
    parser.add_argument("--school")
    parser.add_argument("--actor")
    parser.add_argument("--to", type=Path)
    parser.add_argument("--from", dest="source", type=Path)
    parser.add_argument("--new-school")
    parser.add_argument("--new-deployment")
    parser.add_argument("--learner")
    parser.add_argument("--lifetime-ms", type=int, default=86400000)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--rights")
    parser.add_argument("--reusable", action="store_true")
    parser.add_argument("--version", type=int)
    parser.add_argument("--reason", default="operator selected an immutable model release")
    parser.add_argument("--credential", type=Path, help="private admitted teacher/operator pairing; never grants filesystem operations")
    parser.add_argument("--token-hash", help="public SHA256 admission identity for revoke-pair")
    args = parser.parse_args()
    if args.credential:
        if args.request in {"serve", "run", "client-run", "start", "restore", "backup", "fork", "publish-training"}:
            parser.error("this operation requires the operator-local filesystem/lifecycle path")
        try:
            credential, endpoint = credential_binding(args.credential)
            args.school, args.actor = credential["school"], credential["learner"]
            if args.client_port is None:
                args.client_port = endpoint.port
            if args.request == "pair":
                data, _ = pair(args, parser)
            elif args.request in SHORTCUTS:
                data = shortcut(args, parser)
            else:
                data = args.request.encode()
                json.loads(data)
            return emit_reply(credential_post(credential, data))
        except (ValueError, KeyError, OSError, urllib.error.URLError):
            # No exception detail can accidentally print the private handoff.
            parser.exit(1, "protected school request failed; check private file, endpoint and admitted scope\n")
    for origin in args.browser_origin:
        parsed = urllib.parse.urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password
                or parsed.netloc != f"{parsed.hostname}:{parsed.port}"):
            parser.error("browser-origin must be an exact http://localhost:PORT or http://127.0.0.1:PORT origin")
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    helper = args.binary.resolve().parent / "school_fs_barrier.py"
    args.barrier_helper = (args.barrier_helper or (helper if helper.exists() else Path(__file__).with_name("school_fs_barrier.py"))).resolve()
    environment = dict(os.environ, LEMMA_SCHOOL_FS_BARRIER=str(args.barrier_helper), LEMMA_SCHOOL_FS_PYTHON=sys.executable)
    if args.request in SHORTCUTS or args.request == "start":
        token_digest = None
        if args.request == "pair":
            data, token_digest = pair(args, parser)
        else:
            data = shortcut(args, parser)
        if args.request == "start":
            return launch(args, root, data, parser)
        running = runtime(root)
        if running:
            if running.get("mode") == "client-run":
                parser.exit(1, "protected-only transport has no operator endpoint; stop foreground process before local operation\n")
            if args.request == "restore":
                parser.exit(1, "restore destination has a running authority; choose fresh storage\n")
            reply = post(running["port"], data)
            if token_digest:
                print(f"private pairing file: {args.to.resolve()} (token hash {token_digest})", file=sys.stderr)
            return emit_reply(reply)
        args.request = data.decode()
    # Ordinary operator tooling uses structured JSON too. Route it through
    # the single existing authority instead of racing its process mutex.
    running = runtime(root)
    if running and args.request not in {"serve", "run", "client-run"}:
        if running.get("mode") == "client-run":
            parser.exit(1, "protected-only transport has no operator endpoint; stop foreground process before local operation\n")
        data = args.request.encode()
        if len(data) > LIMIT:
            parser.error("request byte limit exceeded")
        try:
            json.loads(data)
        except ValueError:
            parser.error("operator request must be JSON or a supported shortcut")
        return emit_reply(post(running["port"], data))
    authority_status = 0
    with (root / "authority.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "school authority is already owned by another process\n")
        if args.request not in {"serve", "run", "client-run"}:
            if len(args.request.encode()) > LIMIT:
                parser.exit(1, "request byte limit exceeded\n")
            # Inherit the same open-file-description lock across parent death.
            return subprocess.call([str(args.binary.resolve()), str(root), args.request],
                                   pass_fds=(lock.fileno(),), env=environment)
        with subprocess.Popen([str(args.binary.resolve()), str(root), "serve"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              pass_fds=(lock.fileno(),), env=environment) as child:
            def exchange(data):
                if len(data) > LIMIT or b"\n" in data.rstrip(b"\r\n"):
                    raise ValueError("request must be one bounded JSON line")
                child.stdin.write(data.rstrip(b"\r\n") + b"\n")
                child.stdin.flush()
                reply = child.stdout.readline(LIMIT * 32 + 1)
                if not reply or len(reply) > LIMIT * 32:
                    raise RuntimeError("school process closed or exceeded response bound")
                return reply
            receipt_path = None
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
                        learner_endpoint = False
                        timeout = 5
                        def origin_allowed(self):
                            return self.headers.get("Origin") in args.browser_origin
                        def end_headers(self):
                            if self.learner_endpoint and self.path == "/v1/client" and self.origin_allowed():
                                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                                self.send_header("Vary", "Origin")
                            super().end_headers()
                        def do_OPTIONS(self):
                            requested = {name.strip().lower() for name in self.headers.get("Access-Control-Request-Headers", "").split(",") if name.strip()}
                            if (not self.learner_endpoint or self.path != "/v1/client" or not self.origin_allowed()
                                    or self.headers.get("Access-Control-Request-Method") != "POST"
                                    or not requested <= {"authorization", "content-type"}):
                                self.send_error(403)
                                return
                            self.send_response(204)
                            self.send_header("Access-Control-Allow-Methods", "POST")
                            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                            self.send_header("Access-Control-Max-Age", "600")
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                        def do_POST(self):
                            try:
                                length = int(self.headers.get("Content-Length", "-1"))
                                expected = "/v1/client" if self.learner_endpoint else "/v1/command"
                                if self.path != expected or not 0 <= length <= LIMIT:
                                    self.send_error(413)
                                    return
                                if self.learner_endpoint and self.headers.get("Origin") and not self.origin_allowed():
                                    self.send_error(403)
                                    return
                                payload = self.rfile.read(length)
                                if self.learner_endpoint:
                                    authorization = self.headers.get("Authorization", "")
                                    if not authorization.startswith("Bearer ") or len(authorization) != 71:
                                        self.send_error(401)
                                        return
                                    payload = json.dumps({"op": "client", "token": authorization[7:],
                                                          "command": json.loads(payload)}).encode()
                                reply = exchange(payload)
                                self.send_response(200)
                                self.send_header("Content-Type", "application/json")
                                self.send_header("Content-Length", str(len(reply)))
                                self.end_headers()
                                self.wfile.write(reply)
                            except (ValueError, RuntimeError, BrokenPipeError):
                                self.send_error(503)
                        def log_message(self, *_args):
                            pass
                    class LearnerHandler(Handler):
                        learner_endpoint = True
                    with contextlib.ExitStack() as stack:
                        primary_handler = LearnerHandler if args.request == "client-run" else Handler
                        server = stack.enter_context(http.server.HTTPServer(("127.0.0.1", args.port), primary_handler))
                        servers = [server]
                        if args.client_port:
                            if args.request == "client-run" or args.client_port == args.port:
                                raise ValueError("separate client-port requires run and a distinct port")
                            servers.append(stack.enter_context(http.server.HTTPServer(("127.0.0.1", args.client_port), LearnerHandler)))
                        receipt = {"schema": "lemma-school-transport/1", "pid": os.getpid(),
                                   "bootId": boot_id(), "startTicks": start_ticks(os.getpid()),
                                   "port": args.port, "mode": args.request, "clientPort": args.client_port,
                                   "browserOrigins": args.browser_origin,
                                   "binarySha256": hashlib.sha256(args.binary.read_bytes()).hexdigest()}
                        receipt_path = root / "transport.json"
                        staged = root / "transport.part"
                        staged.write_text(json.dumps(receipt) + "\n")
                        staged.replace(receipt_path)
                        primary_path = "client" if args.request == "client-run" else "command"
                        print(f"school transport http://127.0.0.1:{args.port}/v1/{primary_path}", file=sys.stderr, flush=True)
                        if args.client_port or args.request == "client-run":
                            print(f"school learner transport http://127.0.0.1:{args.client_port or args.port}/v1/client", file=sys.stderr, flush=True)
                        while child.poll() is None:
                            ready, _, _ = select.select([item.socket for item in servers], [], [], 0.2)
                            for item in servers:
                                if item.socket in ready:
                                    item.handle_request()
            finally:
                if child.stdin and not child.stdin.closed:
                    child.stdin.close()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                if receipt_path and receipt_path.exists():
                    receipt_path.unlink()
                authority_status = child.returncode
    return authority_status


if __name__ == "__main__":
    raise SystemExit(main())
