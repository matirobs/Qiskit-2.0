"""Build the self-contained, root-entrypoint browser assets for Qollab."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_FILE = ROOT / "web" / "js" / "quantumBridge.js"
APP_FILE = ROOT / "web" / "js" / "app.js"
HTML_FILE = ROOT / "index.html"
STYLES_FILE = ROOT / "styles.css"
ASSET_SOURCES = {
    "repackq-demo-future.json": ROOT / "web" / "data" / "demo" / "future.json",
    "repackq-demo-inventory.json": ROOT / "web" / "data" / "demo" / "inventory.json",
    "repackq-demo-classical.json": ROOT / "web" / "data" / "demo" / "classical.json",
    "repackq-demo-qaoa-replay.json": ROOT / "web" / "data" / "demo" / "qaoa-replay.json",
    "repackq-benchmark-summary.json": ROOT / "web" / "data" / "benchmark" / "summary.json",
    "repackq-benchmark-trials.json": ROOT / "web" / "data" / "benchmark" / "trials.json",
}


def build_main_js() -> str:
    bridge = BRIDGE_FILE.read_text(encoding="utf-8")
    bridge = re.sub(r"^export\s+", "", bridge, flags=re.MULTILINE)
    bridge = bridge.replace(
        "export ",
        "",
    )
    bridge = bridge.rstrip()
    bridge = f"""(() => {{
  {bridge}
  return {{
    registerRuntimeAdapter,
    getRuntimeAdapter,
    hasInteractiveRuntime,
    getCapabilities,
    getDemoState,
    evaluateSelection,
    runClassicalComparison,
    runQaoa,
    revealFuture,
  }};
}})()"""

    app = APP_FILE.read_text(encoding="utf-8")
    app = app.replace('import * as quantumBridge from "./quantumBridge.js";\n\n', "", 1)
    app = app.replace(
        'const ASSET_ROOT = new URL("../data/", import.meta.url).href.replace(/\\/$/, "");',
        'const ASSET_ROOT = new URL("./", document.baseURI).href.replace(/\\/$/, "");',
        1,
    )
    replacements = {
        "${ASSET_ROOT}/demo/future.json": "${ASSET_ROOT}/repackq-demo-future.json",
        "${ASSET_ROOT}/demo/inventory.json": "${ASSET_ROOT}/repackq-demo-inventory.json",
        "${ASSET_ROOT}/demo/classical.json": "${ASSET_ROOT}/repackq-demo-classical.json",
        "${ASSET_ROOT}/demo/qaoa-replay.json": "${ASSET_ROOT}/repackq-demo-qaoa-replay.json",
        "${ASSET_ROOT}/benchmark/summary.json": "${ASSET_ROOT}/repackq-benchmark-summary.json",
        "${ASSET_ROOT}/benchmark/trials.json": "${ASSET_ROOT}/repackq-benchmark-trials.json",
    }
    for before, after in replacements.items():
        app = app.replace(before, after)
    if 'const asset = await response.json();' not in app:
        raise ValueError("Could not find the held-out fixture load to inline lazily.")
    future_load = '''const response = await fetch(`${ASSET_ROOT}/repackq-demo-future.json`, { cache: "no-store" });
      if (!response.ok) throw new Error("The held-out fixture asset could not be loaded.");
      const asset = await response.json();'''
    if future_load not in app:
        raise ValueError("Could not find the held-out fixture fetch to replace.")
    app = app.replace(future_load, "const asset = JSON.parse(QOLLAB_INLINE_FUTURE_JSON);", 1)

    asset_anchor = 'const ASSET_ROOT = new URL("./", document.baseURI).href.replace(/\\/$/, "");'
    if asset_anchor not in app:
        raise ValueError("Could not find the asset root declaration to inline fixtures.")
    inline_assets = {
        filename: json.loads(source.read_text(encoding="utf-8"))
        for filename, source in ASSET_SOURCES.items()
        if filename != "repackq-demo-future.json"
    }
    future_json = ASSET_SOURCES["repackq-demo-future.json"].read_text(encoding="utf-8")
    inline_declarations = (
        "const QOLLAB_INLINE_ASSETS = "
        + json.dumps(inline_assets, ensure_ascii=False, separators=(",", ":"))
        + ";\nconst QOLLAB_INLINE_FUTURE_JSON = "
        + json.dumps(future_json, ensure_ascii=False)
        + ";"
    )
    app = app.replace(asset_anchor, asset_anchor + "\n" + inline_declarations, 1)

    old_load_json = '''async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}'''
    new_load_json = '''async function loadJson(path) {
  const filename = new URL(path, document.baseURI).pathname.split("/").pop();
  if (Object.prototype.hasOwnProperty.call(QOLLAB_INLINE_ASSETS, filename)) {
    return JSON.parse(JSON.stringify(QOLLAB_INLINE_ASSETS[filename]));
  }
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}'''
    if old_load_json not in app:
        raise ValueError("Could not find the preview JSON loader to inline fixtures.")
    app = app.replace(old_load_json, new_load_json, 1)
    if "import.meta" in app or "./quantumBridge.js" in app:
        raise ValueError("The browser app still has an ES-module dependency after bundling.")
    if "await initialize();" not in app:
        raise ValueError("Could not find the app initialization statement to bundle.")
    app = app.replace("await initialize();", "await initialize();", 1)

    return f'''/* Generated by scripts/build_qollab_html.py. Edit web/js sources, then rebuild. */
(function () {{
  "use strict";

  function reportStartupError(error) {{
    var status = document.querySelector("#workspace-status");
    if (!status) return;
    status.textContent = "RePack-Q could not initialize: " + (error && error.message ? error.message : "an unexpected browser error occurred.");
    status.dataset.kind = "error";
  }}

  function boot() {{
    if (typeof document === "undefined" || !document.querySelector("#main-content")) return;
    if (window.__REPACKQ_APP_BOOT_STARTED__) return;
    window.__REPACKQ_APP_BOOT_STARTED__ = true;
    var quantumBridge = {bridge};
    (async function startRePackQApp() {{
{_indent(app, 6)}
    }})().catch(reportStartupError);
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", boot, {{ once: true }});
  }} else {{
    boot();
  }}
}})();
'''


def _indent(value: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in value.rstrip().splitlines())


def build_qollab_main_js() -> str:
    """Build the Qollab module entrypoint with its documented Python bridge."""

    adapter = r'''import * as repackqPython from "repackq_qollab_bridge";

function qollabSelectedBackend() {
  try {
    if (typeof backend !== "undefined") return backend;
  } catch (_) {
    // Some Qollab runtimes expose the selected backend only on globalThis.
  }
  return globalThis.backend ?? null;
}

async function callRePackQPython(functionName, args) {
  const pythonFunction = repackqPython[functionName];
  if (!pythonFunction || typeof pythonFunction.callPromising !== "function") {
    throw new Error(`Qollab could not call Python function ${functionName} with callPromising().`);
  }
  try {
    const result = await pythonFunction.callPromising(...args);
    const converted = result && typeof result.toJs === "function" ? result.toJs() : result;
    if (typeof converted === "string") {
      try {
        return JSON.parse(converted);
      } catch (_) {
        throw new Error(`Python function ${functionName} returned invalid JSON.`);
      }
    }
    return converted;
  } catch (error) {
    console.error(`RePack-Q Qollab Python call ${functionName} failed:`, error);
    throw error;
  }
}

async function callRePackQPythonRaw(functionName, args) {
  const pythonFunction = repackqPython[functionName];
  if (!pythonFunction || typeof pythonFunction.callPromising !== "function") {
    throw new Error(`Qollab could not call Python function ${functionName} with callPromising().`);
  }
  return await pythonFunction.callPromising(...args);
}

function qollabBackendName(selectedBackend) {
  let reportedName = "";
  try {
    const value = selectedBackend.name;
    reportedName = String(typeof value === "function" ? value.call(selectedBackend) : (value ?? ""));
  } catch (_) {
    reportedName = "";
  }
  const genericNames = new Set(["", "default", "backend", "qollab_selected_backend"]);
  if (!genericNames.has(reportedName.trim().toLowerCase())) return reportedName;

  // Some Qiskit providers expose the generic name "default". Keep that name
  // but append the backend class so the inspector still identifies its
  // provider implementation without inspecting credentials or private state.
  try {
    const pythonClass = selectedBackend.__class__;
    const className = pythonClass?.__name__;
    const moduleName = pythonClass?.__module__;
    if (className) {
      const moduleLeaf = String(moduleName ?? "").split(".").at(-1);
      const implementation = moduleLeaf && moduleLeaf !== "" ? `${moduleLeaf}.${className}` : String(className);
      return reportedName ? `${reportedName} (${implementation})` : implementation;
    }
  } catch (_) {
    // Fall back to the JavaScript proxy's constructor name below.
  }
  try {
    const constructorName = selectedBackend?.constructor?.name;
    if (constructorName && constructorName !== "Object" && constructorName !== "PyProxy") {
      return reportedName ? `${reportedName} (${constructorName})` : constructorName;
    }
  } catch (_) {
    // The Qiskit proxy may hide its JavaScript constructor.
  }
  return reportedName || "qollab_selected_backend";
}

function qollabProblemArgs(options = {}) {
  return [
    Number(options.horizon_cycles ?? 200),
    Number(options.pack_size_k ?? 4),
  ];
}

globalThis.__REPACKQ_RUNTIME_ADAPTER__ = {
  async getCapabilities() {
    try {
      const capabilities = await callRePackQPython("get_capabilities", []);
      console.log("RePack-Q Qollab bridge capabilities:", capabilities);
      return capabilities;
    } catch (error) {
      return {
        available: false,
        interactive: false,
        bridge: "qollab-python-callpromising-v1",
        qiskit_available: false,
        statevector_available: false,
        message: error?.message || "Qollab could not load the RePack-Q Python module.",
      };
    }
  },
  async getDemoState(options = {}) {
    const inventory = await callRePackQPython("get_demo_state", qollabProblemArgs(options));
    console.log("RePack-Q candidate inventory response:", {
      response_type: Object.prototype.toString.call(inventory),
      data_classification: inventory?.data_classification,
      future_disclosed: inventory?.future_disclosed,
      candidate_count: inventory?.candidate_ids?.length,
      snapshot_count: inventory?.snapshots?.length,
      top_level_keys: inventory && typeof inventory === "object" ? Object.keys(inventory) : [],
    });
    return inventory;
  },
  async evaluateSelection(indices, options = {}) {
    return callRePackQPython("evaluate_selection", [
      indices,
      ...qollabProblemArgs(options),
      String(options.objective_mode ?? "trajectory_aware"),
    ]);
  },
  async runClassicalComparison(options = {}) {
    return callRePackQPython("run_classical_comparison", [
      ...qollabProblemArgs(options),
      String(options.objective_mode ?? "trajectory_aware"),
    ]);
  },
  async runQaoa({ onStage, ...options } = {}) {
    const selectedBackend = qollabSelectedBackend();
    if (!selectedBackend || typeof selectedBackend.run !== "function") {
      throw new Error("Qollab did not expose the selected Qiskit backend to this project run. Choose a simulator in Qollab's Run dialog and retry.");
    }
    onStage?.("running_python");
    let circuit = null;
    let circuitName = "";
    try {
      circuit = await callRePackQPythonRaw("prepare_qaoa_circuit", [
        ...qollabProblemArgs(options),
        String(options.objective_mode ?? "trajectory_aware"),
        Number(options.shots ?? 1024),
        Number(options.reps ?? 1),
        String(options.optimizer_mode ?? "grid"),
        Number(options.max_evaluations ?? 121),
        selectedBackend,
      ]);
      circuitName = String(circuit.name ?? "");
      if (!circuitName.startsWith("repackq_qaoa_")) {
        throw new Error("Python preparation returned a circuit without its RePack-Q run identifier.");
      }

      // Qollab requires Python functions that submit provider jobs to run via
      // callPromising(). Python has optimized and transpiled for this selected
      // backend; this call submits exactly once and returns measured counts.
      onStage?.("parameter_optimization");
      onStage?.("sampling");
      const samplingStarted = performance.now();
      const submitted = await callRePackQPython("submit_qaoa_circuit", [
        circuit,
        selectedBackend,
        Number(options.shots ?? 1024),
      ]);
      const samplingMs = performance.now() - samplingStarted;
      const result = await callRePackQPython("complete_qaoa_circuit", [
        circuitName,
        JSON.stringify(submitted.counts),
        qollabBackendName(selectedBackend),
        samplingMs,
      ]);
      console.log("RePack-Q live QAOA result:", result);
      onStage?.("complete");
      return result;
    } catch (error) {
      console.error("RePack-Q live QAOA failed:", error);
      if (circuitName) {
        try {
          await callRePackQPython("discard_qaoa_circuit", [circuitName]);
        } catch (cleanupError) {
          console.warn("RePack-Q could not clear a failed QAOA preparation:", cleanupError);
        }
      }
      throw error;
    }
  },
  async revealFuture(indices, options = {}) {
    return callRePackQPython("reveal_future", [indices, ...qollabProblemArgs(options)]);
  },
};
'''
    return adapter + "\n" + build_main_js()


def build_index_html() -> str:
    html = HTML_FILE.read_text(encoding="utf-8")
    styles = STYLES_FILE.read_text(encoding="utf-8")
    stylesheet_link = re.compile(r'<link\s+rel="stylesheet"\s+href="styles\.css"\s*>', re.IGNORECASE)
    embedded_styles = f'<style id="repackq-inline-styles">\n{styles}\n</style>'
    if stylesheet_link.search(html):
        return stylesheet_link.sub(lambda _match: embedded_styles, html, count=1)
    style_tag = re.compile(
        r'<style\s+id="repackq-inline-styles"\s*>.*?</style>',
        re.IGNORECASE | re.DOTALL,
    )
    if style_tag.search(html):
        return style_tag.sub(lambda _match: embedded_styles, html, count=1)
    raise ValueError("Could not find the stylesheet link or generated style block in index.html.")


def build(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "main.js").write_text(build_main_js(), encoding="utf-8", newline="\n")
    (output_dir / "index.html").write_text(build_index_html(), encoding="utf-8", newline="\n")
    for source in ASSET_SOURCES.values():
        if not source.is_file():
            raise FileNotFoundError(f"Required Qollab fixture asset is missing: {source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT, help="directory for standalone index.html and main.js entrypoints")
    args = parser.parse_args()
    build(args.output_dir.resolve())
    print(f"Built Qollab HTML/JS assets in {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
