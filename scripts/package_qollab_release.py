"""Build standalone Qollab app and Python runtime-smoke ZIP packages."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_qollab_html import build as build_qollab_html
from scripts.build_qollab_html import build_qollab_main_js


APP_FILES = (
    "main.py",
    "repackq_qollab_bridge.py",
    "styles.css",
    "run_repackq_web.py",
    "Launch RePack-Q.bat",
    "README.md",
    "requirements.txt",
    "LICENSE",
    "ATTRIBUTION.md",
)
APP_SCRIPT_FILES = (
    "scripts/__init__.py",
    "scripts/qollab_runtime_probe.py",
    "scripts/build_qollab_html.py",
    "scripts/package_qollab_release.py",
)
APP_DOC_FILES = (
    "docs/RESULTS.md",
    "docs/QOLLAB_SPIKE.md",
    "docs/QOLLAB_PROJECT_PAGE.md",
    "docs/DEMO_SCRIPT.md",
    "docs/SUBMISSION_CHECKLIST.md",
)

SMOKE_ENTRYPOINT = '''"""Qollab Task 8 runtime and local QAOA smoke report.

This check runs only Qiskit's local BasicSimulator. It never discovers or
submits a remote Qollab or IonQ job. Runtime package details and safe backend
object names/methods are included to guide a later explicit platform check.
"""

import json
import sys

from repackq_main_api import qollab_runtime_probe, run_task5_toy_demo


def main() -> None:
    runtime = qollab_runtime_probe(globals())
    candidate_backend = globals().get("backend")
    candidate_type = type(candidate_backend)
    injected_basic_simulator = (
        candidate_type.__module__ == "qiskit.providers.basic_provider.basic_simulator"
        and candidate_type.__name__ == "BasicSimulator"
        and callable(getattr(candidate_backend, "run", None))
    )
    report = {
        "application": "RePack-Q Qollab Task 8 smoke",
        "runtime": runtime,
        "qollab_injected_basic_simulator": {
            "available": injected_basic_simulator,
            "used_for_qaoa": injected_basic_simulator,
            "type": (
                f"{candidate_type.__module__}.{candidate_type.__qualname__}"
                if injected_basic_simulator
                else None
            ),
        },
        "local_basic_simulator_qaoa": None,
        "remote_backend_job_submitted": False,
        "data_classification": "synthetic",
    }
    try:
        report["local_basic_simulator_qaoa"] = run_task5_toy_demo(
            backend=candidate_backend if injected_basic_simulator else None,
            shots=512,
            simulator_seed=20261010,
        )
    except Exception as exc:
        report["local_basic_simulator_qaoa"] = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    qaoa = report["local_basic_simulator_qaoa"]
    report["ok"] = bool(
        report["runtime"].get("local_qiskit_smoke", {}).get("ok")
        and isinstance(qaoa, dict)
        and qaoa.get("feasible") is True
    )
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
'''


def _copy_file(relative: str, destination: Path) -> None:
    source = ROOT / relative
    if not source.is_file():
        raise FileNotFoundError(f"Required release input is missing: {source}")
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(relative: str, destination: Path, *, target_name: str | None = None) -> None:
    source = ROOT / relative
    if not source.is_dir():
        raise FileNotFoundError(f"Required release directory is missing: {source}")
    target = destination / (target_name or Path(relative).name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _zip_directory(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source).as_posix())


def build_app_package(destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="repackq-qollab-app-") as temporary:
        stage = Path(temporary)
        build_qollab_html(stage)
        (stage / "main.js").write_text(
            build_qollab_main_js(),
            encoding="utf-8",
            newline="\n",
        )
        for relative in APP_FILES + APP_SCRIPT_FILES + APP_DOC_FILES:
            _copy_file(relative, stage)
        _copy_tree("src/repackq", stage, target_name="repackq")
        _copy_tree("data/fixtures", stage, target_name="data/fixtures")
        _copy_tree("web", stage, target_name="web")

        # Qollab's hosted Python runtime may reject filesystem reads with
        # OSError [Errno 29]. Embed this explicitly synthetic fixture as a
        # Python string so the bridge can load it without opening a file.
        fixture_json = (ROOT / "data/fixtures/synthetic_demo.json").read_text(
            encoding="utf-8"
        )
        fixture_module = (
            '"""Synthetic Qollab fixture embedded for read-restricted runtimes."""\n\n'
            f"FIXTURE_JSON = {fixture_json!r}\n"
        )
        (stage / "repackq_qollab_fixture.py").write_text(
            fixture_module,
            encoding="utf-8",
            newline="\n",
        )

        for required in (
            "index.html",
            "main.js",
            "styles.css",
            "main.py",
            "repackq_qollab_bridge.py",
            "repackq_qollab_fixture.py",
            "repackq/__init__.py",
        ):
            if not (stage / required).is_file():
                raise RuntimeError(f"Qollab app package is missing {required}")
        main_js = (stage / "main.js").read_text(encoding="utf-8")
        if (
            'from "repackq_qollab_bridge"' not in main_js
            or 'callPromising(...args)' not in main_js
            or 'callRePackQPython("submit_qaoa_circuit"' not in main_js
            or "await selectedBackend.run(" in main_js
            or "import.meta" in main_js
            or './quantumBridge.js' in main_js
        ):
            raise RuntimeError(
                "The generated Qollab entrypoint is missing the documented Python "
                "bridge or promised backend submission path"
            )
        _zip_directory(stage, destination)


def build_python_smoke_package(destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="repackq-qollab-smoke-") as temporary:
        stage = Path(temporary)
        (stage / "main.py").write_text(SMOKE_ENTRYPOINT, encoding="utf-8", newline="\n")
        shutil.copy2(ROOT / "main.py", stage / "repackq_main_api.py")
        for relative in ("requirements.txt", "LICENSE", "ATTRIBUTION.md", "scripts/__init__.py", "scripts/qollab_runtime_probe.py"):
            _copy_file(relative, stage)
        _copy_tree("src/repackq", stage, target_name="repackq")

        for required in ("main.py", "repackq_main_api.py", "requirements.txt", "repackq/__init__.py", "scripts/qollab_runtime_probe.py"):
            if not (stage / required).is_file():
                raise RuntimeError(f"Qollab smoke package is missing {required}")
        _zip_directory(stage, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT,
        help="directory for qollab-task8-app.zip and qollab-task8-python-smoke.zip",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    app_zip = output_dir / "qollab-task8-app.zip"
    smoke_zip = output_dir / "qollab-task8-python-smoke.zip"
    build_app_package(app_zip)
    build_python_smoke_package(smoke_zip)
    print(f"Created Qollab HTML/JS app: {app_zip}")
    print(f"Created Qollab Python smoke package: {smoke_zip}")


if __name__ == "__main__":
    main()
