"""Check all-step usage summaries and where each history interval ends."""
import csv
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from repackq.training.prepare_full import MEASUREMENTS, MAXIMA, attach_usage, summarize_usage, prepare_full
from repackq.data.prepare import sha256


class FullDataTest(unittest.TestCase):
    def test_all_steps_contribute_and_intervals_never_include_future_cycles(self):
        # combine multiple step currents in each cycle and check the usage cutoff
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "1.csv"
            columns = ["Battery_ID", "Protocol_ID", "Cycle_Index", "Test_Time(s)",
                       *MEASUREMENTS.values(), *MAXIMA.values()]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                for cycle in range(1, 7):
                    for current in (-.48, -2.4, 0.0):
                        writer.writerow({"Battery_ID": 9, "Protocol_ID": 2, "Cycle_Index": cycle,
                            "Test_Time(s)": cycle * 100 + current, "Current(A)": current,
                            "Voltage(V)": 3 + cycle * .01, "Aux_Temperature_1(C)": 25 + cycle,
                            "Internal_Resistance(Ohm)": .04, "Charge_Capacity(Ah)": 1,
                            "Discharge_Capacity(Ah)": 2, "Charge_Energy(Wh)": 4,
                            "Discharge_Energy(Wh)": 5})
            # A three-row cycle spans two-row chunks, exercising exact aggregation.
            summary = summarize_usage(path, chunksize=2)
            self.assertEqual(summary["raw_rows"], 18)
            self.assertEqual(summary["cell_id"], "9")
            points = [{"cycle": i, "capacity_ah": 2.0} for i in (1, 3, 5)]
            second, trailing = attach_usage(points, summary["cycles"], "second_life")
            first, first_trailing = attach_usage(points, summary["cycles"], "primary")
            self.assertAlmostEqual(second[0]["usage"]["current_abs_mean"], .96)
            self.assertEqual(second[0]["usage"]["temperature_max"], 26)
            self.assertEqual(second[-1]["usage"]["temperature_max"], 30)
            self.assertEqual(first[-1]["usage"]["temperature_max"], 31)
            self.assertEqual(trailing, 3)
            self.assertEqual(first_trailing, 0)
            # Complete both phases, then ensure a changed source manifest cannot
            # reuse a previously verified cache just because its file stamp matches.
            root = Path(tmp)
            sources = []
            for folder in ("Primary_use_phase", "Second_life_phase"):
                target = root / folder / "1.csv"
                target.parent.mkdir()
                target.write_bytes(path.read_bytes())
                sources.append({"path": str(target), "sha256": sha256(target), "rows": 18})
            baseline = root / "baseline.json"
            payload = {"cells": [{"cell_id": "9", "primary": points, "second_life": points}],
                       "provenance": {"sources": sources}}
            baseline.write_text(json.dumps(payload))
            output = root / "processed/full.json"
            with contextlib.redirect_stdout(io.StringIO()):
                status = prepare_full(root, baseline, output)
            self.assertEqual(status["raw_rows_processed"], 36)
            self.assertFalse(status["pending_files"])
            loaded = json.loads(output.read_text())
            self.assertIn("usage", loaded["cells"][0]["primary"][0])
            sources[0]["sha256"] = "0" * 64
            baseline.write_text(json.dumps(payload))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "differs"):
                prepare_full(root, baseline, output)
