"""Run buf lint and buf breaking for contracts/proto (tasks 2.3 and 2.6).

    python contracts/tools/check_proto.py                          # breaking against .git#branch=main
    python contracts/tools/check_proto.py --against '.git#ref=HEAD~1'

Run from the repository root (where buf.yaml is). buf comes from the BUF environment variable or PATH and must
be the version pinned in DEPENDENCIES.lock.md. Output uses buf's msvs format, so every violation names the file,
line, and rule, for example:

    contracts\\proto\\...\\config_validation.proto(32,1) : error FIELD_NO_DELETE : Previously present field ...

This enforces "new package version, never mutate v1" (ADR-003, Req 13.11): buf breaking uses the FILE category
configured in buf.yaml, so removing, renumbering, or retyping anything in a v1 package fails, and a new v2
package passes. Exit status is 0 only when both checks pass.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def _buf() -> str:
    buf = os.environ.get("BUF") or shutil.which("buf")
    if not buf:
        sys.exit("buf not found: install the pinned buf and put it on PATH or set BUF")
    return buf


def _run(step: str, args: list[str]) -> bool:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        print(f"[PASS] {step}")
        return True
    print(f"[FAIL] {step} (exit {proc.returncode})")
    print(output or "(buf printed no detail)")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="buf lint and buf breaking for contracts/proto")
    parser.add_argument("--against", default=".git#branch=main",
                        help="buf input to compare with (default: .git#branch=main)")
    args = parser.parse_args(argv)
    buf = _buf()
    version = subprocess.run([buf, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"buf {version}; breaking against {args.against}")
    ok = _run("buf lint", [buf, "lint", "--error-format=msvs"])
    ok = _run(f"buf breaking --against {args.against}", [buf, "breaking", "--against", args.against, "--error-format=msvs"]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
