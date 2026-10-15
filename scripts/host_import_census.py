#!/usr/bin/env python3
"""Observe imports of the ordinary public CLI; never alter machine execution."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time


def main():
    output, cli = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    arguments = sys.argv[3:]
    root = cli.parent.parent
    sys.path.insert(0, str(cli.parent))
    sys.argv = [str(cli), *arguments]

    write_lock = threading.Lock()

    def collect():
        paths = {cli, Path(__file__).resolve()}
        for module in list(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if filename:
                path = Path(filename).resolve()
                if path.suffix == ".py" and path.is_relative_to(root) and path.is_file():
                    paths.add(path)
        result = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in paths}
        temporary = output.with_suffix(".tmp-" + str(os.getpid()))
        temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        temporary.replace(output)

    def write():
        # Startup observation and interpreter exit can race on a short session.
        with write_lock:
            collect()

    atexit.register(write)
    if arguments[:1] == ["session"] and "--session-dir" in arguments:
        directory = Path(arguments[arguments.index("--session-dir") + 1])

        def startup():
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                if (directory / "session.json").is_file():
                    write()
                    return
                time.sleep(0.05)

        threading.Thread(target=startup, daemon=True).start()
    runpy.run_path(str(cli), run_name="__main__")


if __name__ == "__main__":
    main()
