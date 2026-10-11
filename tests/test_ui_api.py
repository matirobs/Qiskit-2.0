"""Integration coverage for the local browser/Python API boundary."""

from __future__ import annotations

import io
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_repackq_web import RePackQHandler  # noqa: E402


class _StreamHarness:
    def __init__(self) -> None:
        self.wfile = io.BytesIO()
        self.headers: list[tuple[str, str]] = []
        self.status = None
        self.close_connection = False

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.headers.append((name, value))

    def end_headers(self) -> None:
        pass


class _ErrorHarness:
    def __init__(self) -> None:
        self.send_attempts = 0
        self.logged_errors: list[str] = []

    def _send_json(self, status: int, payload: object) -> None:
        self.send_attempts += 1

    def log_error(self, message: str, error: Exception) -> None:
        self.logged_errors.append(message)


class LocalUiApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RePackQHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"

    @staticmethod
    def _decode_chunked(body: bytes) -> list[bytes]:
        chunks: list[bytes] = []
        cursor = 0
        while True:
            line_end = body.index(b"\r\n", cursor)
            size = int(body[cursor:line_end], 16)
            cursor = line_end + 2
            if size == 0:
                return chunks
            chunks.append(body[cursor : cursor + size])
            cursor += size
            if body[cursor : cursor + 2] != b"\r\n":
                raise AssertionError("chunk payload is missing its terminator")
            cursor += 2

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_future_values_are_only_returned_after_reveal_request(self) -> None:
        with urlopen(f"{self.base_url}/api/state?horizon_cycles=200&pack_size_k=4") as response:
            state = json.load(response)
        self.assertFalse(state["future_disclosed"])
        self.assertNotIn("truth", state)
        self.assertNotIn("future_truth", state)

        request = Request(
            f"{self.base_url}/api/future",
            data=json.dumps(
                {
                    "selected_indices": [0, 1, 2, 3],
                    "options": {
                        "horizon_cycles": 200,
                        "pack_size_k": 4,
                        # The workbench includes this current-problem option;
                        # reveal needs only horizon and pack size.
                        "objective_mode": "trajectory_aware",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            revealed = json.load(response)

        self.assertTrue(revealed["future_disclosed"])
        self.assertEqual(revealed["data_classification"], "synthetic-fixture")
        self.assertEqual(len(revealed["truth"]), 4)
        self.assertEqual(len(revealed["selected_cell_ids"]), 4)

    def test_live_qaoa_stream_uses_portable_optimizer_default(self) -> None:
        harness = _StreamHarness()
        RePackQHandler._stream_qaoa(
            harness,
            {
                "horizon_cycles": 200,
                "pack_size_k": 4,
                "objective_mode": "trajectory_aware",
                "shots": 512,
                "reps": 1,
            },
        )
        self.assertEqual(harness.status, 200)
        self.assertIn(("Transfer-Encoding", "chunked"), harness.headers)
        chunks = self._decode_chunked(harness.wfile.getvalue())
        events = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]

        stages = [event["stage"] for event in events if event["type"] == "stage"]
        result = next(event["result"] for event in events if event["type"] == "result")
        self.assertEqual(stages, ["preparing", "parameter_optimization", "sampling", "complete"])
        self.assertTrue(result["feasible"])
        self.assertEqual(result["backend"], "basic_simulator")
        self.assertEqual(result["optimizer"]["mode"], "coarse_to_fine_grid")
        self.assertEqual(result["backend_jobs_submitted"], 1)

    def test_disconnected_browser_request_does_not_trigger_error_reply(self) -> None:
        harness = _ErrorHarness()

        RePackQHandler._handle_api_error(harness, BrokenPipeError("peer closed"))

        self.assertEqual(harness.send_attempts, 0)
        self.assertEqual(harness.logged_errors, [])


if __name__ == "__main__":
    unittest.main()
