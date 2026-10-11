/**
 * Host-neutral RePack-Q browser/Python contract.
 *
 * The project deliberately does not call guessed Qollab globals. The local
 * workbench registers a same-origin HTTP adapter on loopback hosts; other
 * hosts need a verified bootstrap implementing this contract. Static
 * fixture/replay behavior lives in app.js and remains clearly labeled.
 */

const ADAPTER_KEY = "__REPACKQ_RUNTIME_ADAPTER__";
const REQUIRED_METHODS = [
  "getCapabilities",
  "getDemoState",
  "evaluateSelection",
  "runClassicalComparison",
  "runQaoa",
  "revealFuture",
];

export function registerRuntimeAdapter(adapter) {
  if (!adapter || typeof adapter !== "object") {
    throw new TypeError("Runtime adapter must be an object.");
  }
  const missing = REQUIRED_METHODS.filter((method) => typeof adapter[method] !== "function");
  if (missing.length) {
    throw new TypeError(`Runtime adapter is missing required methods: ${missing.join(", ")}.`);
  }
  globalThis[ADAPTER_KEY] = adapter;
}

export function getRuntimeAdapter() {
  return globalThis[ADAPTER_KEY] ?? null;
}

export function hasInteractiveRuntime() {
  const adapter = getRuntimeAdapter();
  return Boolean(adapter && REQUIRED_METHODS.every((method) => typeof adapter[method] === "function"));
}

export async function getCapabilities() {
  const adapter = getRuntimeAdapter();
  if (!adapter) {
    return {
      available: false,
      interactive: false,
      bridge: "repackq-runtime-adapter-v2",
      qiskit_available: false,
      message: "No Python browser bridge is available in this host.",
    };
  }
  return await adapter.getCapabilities();
}

export async function getDemoState(options) {
  const adapter = getRuntimeAdapter();
  if (!adapter) throw new Error("Python runtime adapter is not connected.");
  return await adapter.getDemoState(options);
}

export async function evaluateSelection(indices, options) {
  const adapter = getRuntimeAdapter();
  if (!adapter) throw new Error("Python runtime adapter is not connected.");
  return await adapter.evaluateSelection(indices, options);
}

export async function runClassicalComparison(options) {
  const adapter = getRuntimeAdapter();
  if (!adapter) throw new Error("Python runtime adapter is not connected.");
  return await adapter.runClassicalComparison(options);
}

export async function runQaoa(options) {
  const adapter = getRuntimeAdapter();
  if (!adapter) throw new Error("Python runtime adapter is not connected.");
  return await adapter.runQaoa(options);
}

export async function revealFuture(indices, options) {
  const adapter = getRuntimeAdapter();
  if (!adapter) throw new Error("Python runtime adapter is not connected.");
  return await adapter.revealFuture(indices, options);
}

function isLoopbackHost(hostname) {
  return hostname === "localhost"
    || hostname === "127.0.0.1"
    || hostname === "::1"
    || hostname === "[::1]";
}

async function responseJson(response) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The local Python service returned an unreadable response.");
  }
  if (!response.ok) {
    throw new Error(payload?.message || "The local Python service could not complete the request.");
  }
  return payload;
}

function createLocalHttpAdapter() {
  async function post(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(payload),
    });
    return responseJson(response);
  }

  return {
    async getCapabilities() {
      return responseJson(await fetch("/api/capabilities", { cache: "no-store" }));
    },
    async getDemoState(options = {}) {
      const query = new URLSearchParams({
        horizon_cycles: String(options.horizon_cycles ?? 200),
        pack_size_k: String(options.pack_size_k ?? 4),
      });
      return responseJson(await fetch(`/api/state?${query}`, { cache: "no-store" }));
    },
    async evaluateSelection(selectedIndices, options = {}) {
      return post("/api/evaluate", { selected_indices: selectedIndices, options });
    },
    async runClassicalComparison(options = {}) {
      return post("/api/classical", { options });
    },
    async revealFuture(selectedIndices, options = {}) {
      return post("/api/future", { selected_indices: selectedIndices, options });
    },
    async runQaoa({ onStage, ...options } = {}) {
      const response = await fetch("/api/qaoa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ options }),
      });
      if (!response.ok) return responseJson(response);
      if (!response.body) {
        throw new Error("The browser cannot read the local QAOA progress stream.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let result = null;
      let streamError = null;
      const consumeLine = (line) => {
        if (!line.trim()) return;
        let event;
        try {
          event = JSON.parse(line);
        } catch {
          throw new Error("The local QAOA service returned malformed progress data.");
        }
        if (event.type === "stage") {
          if (typeof event.stage === "string") onStage?.(event.stage);
        } else if (event.type === "result") {
          result = event.result;
        } else if (event.type === "error") {
          streamError = new Error(event.message || "QAOA could not complete.");
        } else {
          throw new Error("The local QAOA service returned an unknown progress event.");
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        let newline = buffer.indexOf("\n");
        while (newline >= 0) {
          consumeLine(buffer.slice(0, newline));
          buffer = buffer.slice(newline + 1);
          newline = buffer.indexOf("\n");
        }
        if (done) break;
      }
      if (buffer.trim()) consumeLine(buffer);
      if (streamError) throw streamError;
      if (!result) throw new Error("The local QAOA service ended without a result.");
      return result;
    },
  };
}

if (typeof window !== "undefined" && isLoopbackHost(window.location.hostname) && !getRuntimeAdapter()) {
  registerRuntimeAdapter(createLocalHttpAdapter());
}
