#!/usr/bin/env python3
"""Install a small personal launcher pointing to this repository's controller."""
import json
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = "Managed by The Productive Prompter Model Release Experiment"


def write_managed(path, body):
    if path.exists() and MARKER not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Existing unrelated launcher preserved: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))


if os.name == "nt":
    directory = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WindowsApps"
    controller = ROOT / "scripts/model_experiment.py"
    write_managed(directory / "model-experiment.cmd",
        f'@echo off\r\nrem {MARKER}\r\n"{sys.executable}" "{controller}" %*\r\n')
    py = str(Path(sys.executable)).replace("'", "''")
    script = str(controller).replace("'", "''")
    write_managed(directory / "model-experiment.ps1",
        f"# {MARKER}\n& '{py}' '{script}' @args\nexit $LASTEXITCODE\n")
else:
    directory = Path.home() / ".local/bin"
    target = directory / "model-experiment"
    write_managed(target, f"#!/bin/sh\n# {MARKER}\nexec {shlex.quote(sys.executable)} "
                  f"{shlex.quote(str(ROOT / 'scripts/model_experiment.py'))} \"$@\"\n")
    target.chmod(0o755)
print(json.dumps({"launcher_directory": str(directory), "controller": str(ROOT / "scripts/model_experiment.py"),
                  "command": "model-experiment update"}))
