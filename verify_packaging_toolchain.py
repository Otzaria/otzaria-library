#!/usr/bin/env python3
"""Fail closed when the release compression toolchain drifts."""

import argparse
import json
import platform
import re
import subprocess
import sys
import zlib
from pathlib import Path


class ToolchainError(ValueError):
    pass


def command_version(command, pattern, field):
    output = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).splitlines()[0]
    match = re.search(pattern, output)
    if not match:
        raise ToolchainError(f"cannot parse {field} version from {output!r}")
    return match.group(1)


def actual_versions():
    return {
        "schema_version": 1,
        "python": platform.python_version(),
        "zlib_build": zlib.ZLIB_VERSION,
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        "gnu_tar": command_version(["tar", "--version"], r"\(GNU tar\) ([0-9.]+)", "gnu_tar"),
        "zstd": command_version(["zstd", "--version"], r"v([0-9.]+)", "zstd"),
    }


def verify_versions(expected, actual):
    required = {"schema_version", "python", "zlib_build", "zlib_runtime", "gnu_tar", "zstd"}
    if (
        not isinstance(expected, dict)
        or set(expected) != required
        or type(expected.get("schema_version")) is not int
        or expected.get("schema_version") != 1
    ):
        raise ToolchainError("packaging_toolchain.json has an unexpected schema")
    if actual != expected:
        differing = {key: {"expected": expected.get(key), "actual": actual.get(key)} for key in required if expected.get(key) != actual.get(key)}
        raise ToolchainError(f"release toolchain drift: {differing}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="packaging_toolchain.json")
    parser.add_argument("--output", default="packaging_toolchain_verified.json")
    args = parser.parse_args(argv)
    try:
        expected = json.loads(Path(args.contract).read_text(encoding="utf-8"))
        actual = actual_versions()
        verify_versions(expected, actual)
        Path(args.output).write_text(json.dumps(actual, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, ToolchainError) as exc:
        print(f"packaging toolchain error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
