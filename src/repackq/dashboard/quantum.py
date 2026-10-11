"""Run both Qiskit methods on the dashboard's existing scoring instance."""
from concurrent.futures import ThreadPoolExecutor
from repackq.quantum import capabilities, run_both

# keep native Qiskit parameter creation on one persistent thread across requests
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="repackq-quantum")


def run_quantum(instance, *, seed=11, enabled=False):
    """Classical-only runs stay available without installing Qiskit."""
    capability = capabilities()
    if not enabled:
        return [], {**capability, "status": "not_run" if capability["available"] else "not_installed",
                    "runs": [], "executed_runs": 0}
    if not capability["available"]:
        raise ValueError(capability["message"])
    runs = _worker.submit(run_both, instance, seed=seed).result()
    selections = [run["selection"] for run in runs if run["selection"] is not None]
    return selections, {**capability, "status": "computed", "executed_runs": len(runs),
                        "runs": [{k: v for k, v in run.items() if k != "selection"} for run in runs]}
