"""Compile and call the local Java network; exchange matrices through files."""
from __future__ import annotations

import hashlib
import math
import shutil
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def write_matrix(path: Path, rows: list[list[float]]) -> None:
    """Write the framework's big-endian dimension header and double matrix."""
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("Matrix must be nonempty and rectangular")
    if any(not math.isfinite(value) for row in rows for value in row):
        raise ValueError("Matrix entries must be finite")
    with path.open("wb") as stream:
        stream.write(struct.pack(">ii", len(rows), len(rows[0])))
        for row in rows:
            stream.write(struct.pack(">" + "d" * len(row), *row))


def read_matrix(path: Path) -> list[list[float]]:
    """Read predictions, rejecting malformed, truncated, and non-finite matrices."""
    data = path.read_bytes()
    if len(data) < 8:
        raise ValueError("Missing matrix header")
    rows, columns = struct.unpack_from(">ii", data)
    if rows < 1 or columns < 1 or len(data) != 8 + 8 * rows * columns:
        raise ValueError("Invalid matrix dimensions or byte count")
    values = struct.unpack_from(">" + "d" * (rows * columns), data, 8)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Non-finite matrix value")
    return [list(values[row * columns:(row + 1) * columns]) for row in range(rows)]


class JavaNetwork:
    """Compile the local Java files and call the bridge with argument lists."""

    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        self.classes = self.root / "build/java/classes"

    def compile(self):
        """Rebuild the Java classes when a source file has changed."""
        sources = sorted((self.root / "java").rglob("*.java"))
        if not sources or not shutil.which("java") or not shutil.which("javac"):
            raise RuntimeError("Local training requires a Java Development Kit (version 17 or newer)")
        digest = hashlib.sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()
        stamp = self.classes.parent / "source.sha256"
        if stamp.exists() and stamp.read_text() == digest and (
                self.classes / "org/repackq/BatteryModelCli.class").exists():
            return
        self.classes.mkdir(parents=True, exist_ok=True)
        subprocess.run(["javac", "--release", "17", "-d", str(self.classes),
                        *map(str, sources)], check=True, capture_output=True, text=True, timeout=120)
        stamp.write_text(digest)

    def run(self, arguments: list[str], timeout=300):
        self.compile()
        result = subprocess.run(["java", "-cp", str(self.classes), "org.repackq.BatteryModelCli",
                                 *map(str, arguments)], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Java network failed:\n{result.stderr}\n{result.stdout}")
        return result.stdout

    def run_logged(self, arguments: list[str], log_path: Path, timeout=7200) -> float:
        """Write training progress to a log and return elapsed seconds."""
        self.compile()
        started = time.perf_counter()
        with log_path.open("w") as log:
            result = subprocess.run(["java", "-cp", str(self.classes),
                "org.repackq.BatteryModelCli", *map(str, arguments)], stdout=log,
                stderr=subprocess.STDOUT, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Java network failed; see {log_path}")
        return time.perf_counter() - started


def write_control(path: Path, *, inputs: Path, weights: Path, rows: int, width: int,
                  hidden=12, targets: Path | None = None, epochs_per_block=100,
                  hidden_activation="sigmoid", learning_rate=.03, shuffle=False):
    """Write network options and matrix paths in the Java key=value format."""
    training = targets is not None
    layers = [hidden] if isinstance(hidden, int) else list(hidden)
    if not layers or any(not isinstance(size, int) or size < 1 for size in layers):
        raise ValueError("Hidden layers must contain positive integer widths")
    if hidden_activation not in ("sigmoid", "tanh"):
        raise ValueError("Unsupported hidden activation")
    values = {"inputSize": width, "hiddenSizes": " ".join(map(str, layers)), "outputSize": 1,
              "numActivationLayers": len(layers) + 2, "randLowerBound": -.3, "randUpperBound": .3,
              "hiddenActivation": hidden_activation, "shuffleTraining": str(shuffle).lower(),
              "learningRate": learning_rate, "maxIterations": epochs_per_block, "errorThreshold": 0,
              "keepAlive": 0, "training": str(training).lower(), "runningTestCases": "true",
              "saveWeights": "true", "printInputs": "false",
              "weightInputChoice": ("xavier" if hidden_activation == "tanh" else "random") if training else "load", "numTestCases": rows,
              "trainingDataFileName": inputs.resolve(), "truthTableFileName": targets.resolve() if targets else "unused",
              "loadFileName": weights.resolve(), "saveFileName": weights.resolve()}
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")


def export_weights(binary: Path, dimensions: list[int]) -> list:
    """Convert the source-by-destination Java weight matrices into portable lists."""
    data = binary.read_bytes()
    header_bytes = 4 * len(dimensions)
    if len(data) < header_bytes or list(struct.unpack_from(">" + "i" * len(dimensions), data)) != dimensions:
        raise ValueError("Weight topology differs from the configured model")
    expected = sum(a * b for a, b in zip(dimensions, dimensions[1:]))
    if len(data) != header_bytes + 8 * expected:
        raise ValueError("Weight file length differs from its topology")
    flat = iter(struct.unpack_from(">" + "d" * expected, data, header_bytes))
    weights = [[[next(flat) for _ in range(destination)] for _ in range(source)]
               for source, destination in zip(dimensions, dimensions[1:])]
    if any(not math.isfinite(value) for matrix in weights for row in matrix for value in row):
        raise ValueError("Non-finite learned weight")
    return weights
