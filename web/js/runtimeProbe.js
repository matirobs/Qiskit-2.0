"use strict";

// Read-only browser diagnostics for web/runtime-probe.html. This must stay
// under web/js so Qollab does not mistake it for the project entry point.
const ADAPTER_KEY = "__REPACKQ_RUNTIME_ADAPTER__";
const state = document.querySelector("#runtime-state");
const copy = document.querySelector("#runtime-copy");
const result = document.querySelector("#runtime-result");
const inspectButton = document.querySelector("#inspect-button");
const copyButton = document.querySelector("#copy-button");
const smokeButton = document.querySelector("#smoke-button");
const qaoaButton = document.querySelector("#qaoa-button");
const HOST_NAME_PATTERN = /qollab|python|runtime|backend|quantum/i;
const METHOD_NAME_PATTERN = /run|execute|python|backend|job|submit/i;
const SENSITIVE_NAME_PATTERN = /token|secret|password|credential|api[_-]?key/i;

function showJson(value) {
  result.textContent = JSON.stringify(value, null, 2);
}

function getAdapter() {
  return globalThis[ADAPTER_KEY] ?? null;
}

function inspectScope(scopeName, target) {
  const candidates = [];
  let inspectedNames = 0;
  try {
    for (const name of Object.getOwnPropertyNames(target)) {
      if (!HOST_NAME_PATTERN.test(name) || SENSITIVE_NAME_PATTERN.test(name)) continue;
      inspectedNames += 1;
      try {
        const descriptor = Object.getOwnPropertyDescriptor(target, name);
        if (!descriptor || !("value" in descriptor)) {
          candidates.push({ scope: scopeName, name, type: "accessor", methods: [] });
          continue;
        }
        const value = descriptor.value;
        let methods = [];
        if (value !== null && (typeof value === "object" || typeof value === "function")) {
          methods = Object.getOwnPropertyNames(value).filter((method) =>
            METHOD_NAME_PATTERN.test(method) && !SENSITIVE_NAME_PATTERN.test(method),
          );
        }
        candidates.push({ scope: scopeName, name, type: typeof value, methods });
      } catch {
        candidates.push({ scope: scopeName, name, type: "unavailable", methods: [] });
      }
    }
    return { scope: scopeName, accessible: true, matching_global_names_inspected: inspectedNames, candidates };
  } catch {
    return { scope: scopeName, accessible: false, matching_global_names_inspected: 0, candidates: [] };
  }
}

function inspectHostGlobals() {
  const scopes = [inspectScope("page", globalThis)];
  if (window.parent !== window) scopes.push(inspectScope("parent", window.parent));
  if (window.top !== window && window.top !== window.parent) scopes.push(inspectScope("top", window.top));
  let ancestorOrigins = [];
  try {
    ancestorOrigins = Array.from(location.ancestorOrigins ?? []);
  } catch {
    // Browsers without ancestorOrigins leave this diagnostic empty.
  }
  return {
    app_loaded: true,
    running_in_frame: window.self !== window.top,
    ancestor_origins: ancestorOrigins,
    scopes,
    possible_host_objects: scopes.flatMap((scope) => scope.candidates),
    values_or_credentials_printed: false,
    host_methods_invoked: false,
  };
}

function refreshHostReport() {
  const report = inspectHostGlobals();
  showJson(report);
  const adapter = getAdapter();
  if (adapter) {
    state.textContent = "Adapter found";
    copy.textContent = "The project adapter is present. The host report is available to copy.";
  } else if (report.possible_host_objects.length > 0) {
    state.textContent = "Host objects found";
    copy.textContent = "Copy this report and share it so the Python bridge can be wired to the exact host object.";
  } else {
    state.textContent = "No host object found";
    copy.textContent = "The page loaded, but no matching Qollab/Python runtime object is exposed on the browser global scope.";
  }
  return report;
}

async function initialize() {
  const adapter = getAdapter();
  if (!adapter) {
    refreshHostReport();
    return;
  }

  try {
    const capabilities = await adapter.getCapabilities();
    showJson(capabilities);
    state.textContent = capabilities.qiskit_available ? "Runtime ready" : "Qiskit unavailable";
    copy.textContent = capabilities.qiskit_available
      ? "The host adapter reports Qiskit support. Choose a smoke check or the synthetic Task 5 QAOA run."
      : "The app shell loaded, but this Python runtime does not report Qiskit.";
    smokeButton.disabled = !capabilities.qiskit_available || typeof adapter.runSmokeTest !== "function";
    qaoaButton.disabled = !capabilities.qiskit_available || typeof adapter.runTask5ToyDemo !== "function";
  } catch (error) {
    state.textContent = "Runtime check failed";
    copy.textContent = "The host adapter returned an error while checking Python capabilities.";
    showJson({ error: String(error?.message ?? error) });
  }
}

inspectButton.addEventListener("click", refreshHostReport);

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(result.textContent);
    copyButton.textContent = "Copied";
    window.setTimeout(() => { copyButton.textContent = "Copy report"; }, 1500);
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(result);
    selection?.removeAllRanges();
    selection?.addRange(range);
    copy.textContent = "The report is selected. Copy it with Ctrl+C or Cmd+C.";
  }
});

smokeButton.addEventListener("click", async () => {
  const adapter = getAdapter();
  if (!adapter || typeof adapter.runSmokeTest !== "function") return;
  smokeButton.disabled = true;
  qaoaButton.disabled = true;
  state.textContent = "Running smoke check";
  try {
    const report = await adapter.runSmokeTest();
    showJson(report);
    state.textContent = report.ok ? "Smoke check passed" : "Smoke check failed";
  } catch (error) {
    state.textContent = "Smoke check failed";
    showJson({ error: String(error?.message ?? error) });
  } finally {
    smokeButton.disabled = false;
    qaoaButton.disabled = false;
  }
});

qaoaButton.addEventListener("click", async () => {
  const adapter = getAdapter();
  if (!adapter || typeof adapter.runTask5ToyDemo !== "function") return;
  smokeButton.disabled = true;
  qaoaButton.disabled = true;
  state.textContent = "Running QAOA";
  copy.textContent = "Optimizing locally, then sampling the configured backend once.";
  try {
    const report = await adapter.runTask5ToyDemo();
    showJson(report);
    state.textContent = report.feasible ? "QAOA run complete" : "No feasible sample";
  } catch (error) {
    state.textContent = "QAOA run failed";
    showJson({ error: String(error?.message ?? error) });
  } finally {
    smokeButton.disabled = false;
    qaoaButton.disabled = false;
  }
});

void initialize();
