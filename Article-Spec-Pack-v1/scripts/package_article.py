#!/usr/bin/env python3
"""Compatibility wrapper for the v2 controller-owned packager.

This file intentionally contains no independent packaging rules and never moves
source files. New callers should use ``article-flow package RUN_ID`` directly.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from article_flow import main as article_flow_main


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delegate to the canonical article-flow package command."
    )
    parser.add_argument("run_id", help="Existing Article Flow run ID in PACKAGE state")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    command = ["package", args.run_id]
    if args.json:
        command.append("--json")
    return article_flow_main(command)


if __name__ == "__main__":
    raise SystemExit(main())
