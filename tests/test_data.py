"""Check reference-capacity extraction with small invented measurement files."""
import csv
import tempfile
import unittest
from pathlib import Path

from repackq.data.prepare import COLUMNS, summarize_file


class DataTest(unittest.TestCase):
    def write_fixture(self, path, current=-.48):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            for cycle in range(1, 6):
                # include an operational discharge to check that it is not used as reference capacity
                for step, capacity, voltage in ((15, 2.0 - cycle * .01, 3.0), (24, .5, 2.0)):
                    writer.writerow({"Battery_ID": 9, "Protocol_ID": 2, "Cycle_Index": cycle,
                        "Step_Index": step, "Current(A)": current if step == 15 else -2.4,
                        "Voltage(V)": voltage, "Discharge_Capacity(Ah)": capacity,
                        "Internal_Resistance(Ohm)": .04, "Aux_Temperature_1(C)": 25})

    def test_reference_capacity_and_recorded_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "1.csv"
            self.write_fixture(path)
            record = summarize_file(path, "primary")
            self.assertEqual(record["cell_id"], "9")
            self.assertEqual(len(record["points"]), 5)
            self.assertAlmostEqual(record["points"][0]["capacity_ah"], 1.99)
            self.assertEqual(len(record["source"]["sha256"]), 64)

    def test_unverified_reference_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "1.csv"
            self.write_fixture(path, current=-2.4)
            with self.assertRaisesRegex(ValueError, "Unverified"):
                summarize_file(path, "primary")
