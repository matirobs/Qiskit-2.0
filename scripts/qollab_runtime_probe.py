"""Print safe Qollab runtime facts from a Qollab Python session.

When imported and called from a notebook/Python cell, ``probe_runtime()`` also
inspects that caller's global namespace for likely backend objects. It prints
only names, types, and public method names; it never prints object values,
environment variable values, or credentials.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from typing import Any, Mapping


_SENSITIVE_NAME_PARTS = ("token", "secret", "password", "credential", "api_key", "apikey")
_BACKEND_METHODS = ("run", "submit", "retrieve_job", "get_counts", "result")


def _safe_name(name: str) -> bool:
    lowered = name.lower()
    return not any(part in lowered for part in _SENSITIVE_NAME_PARTS)


def runtime_report(namespace: Mapping[str, Any] | None = None) -> dict[str, Any]:
    packages: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "")
        lowered = name.lower()
        if any(part in lowered for part in ("qiskit", "qollab", "ionq", "numpy", "scipy")):
            packages[name] = distribution.version

    candidates: list[dict[str, Any]] = []
    if namespace is not None:
        for name, value in namespace.items():
            if name.startswith("_") or not _safe_name(name):
                continue
            methods = [method for method in _BACKEND_METHODS if callable(getattr(value, method, None))]
            if methods:
                candidates.append(
                    {
                        "name": name,
                        "type": f"{type(value).__module__}.{type(value).__qualname__}",
                        "methods": methods,
                    }
                )

    try:
        from repackq.quantum.qiskit_compat import run_smoke_test

        local_smoke: dict[str, Any] = run_smoke_test()
    except Exception as exc:  # report missing/incompatible Qiskit without dumping internals
        local_smoke = {"ok": False, "error_type": type(exc).__name__, "message": str(exc)}

    return {
        "python_version": sys.version.split()[0],
        "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower())),
        "possible_backend_objects": candidates,
        "local_qiskit_smoke": local_smoke,
        "credential_values_printed": False,
        "note": "The capability probe uses local BasicSimulator; it does not submit a remote Qollab or IonQ job or inspect browser JavaScript globals.",
    }


def probe_runtime(namespace: Mapping[str, Any] | None = None) -> None:
    if namespace is None:
        try:
            namespace = sys._getframe(1).f_globals
        except (AttributeError, ValueError):
            namespace = None
    print(json.dumps(runtime_report(namespace), indent=2, sort_keys=True))


if __name__ == "__main__":
    probe_runtime(globals())
