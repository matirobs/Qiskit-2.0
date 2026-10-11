"""Minimal callable project API used by the environment-check page."""

from __future__ import annotations

import json
from typing import Any

from repackq.quantum.qiskit_compat import get_capabilities as _get_capabilities
from repackq.quantum.qiskit_compat import run_smoke_test as _run_smoke_test


def get_capabilities() -> dict[str, Any]:
    return _get_capabilities()


def run_smoke_test() -> dict[str, Any]:
    return _run_smoke_test()


def main() -> None:
    report = {"capabilities": get_capabilities(), "smoke_test": run_smoke_test()}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
