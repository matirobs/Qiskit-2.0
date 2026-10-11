"""Read-only inspection CLI for the Deep Sorting battery dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from repackq.data.inspection import inspect_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read raw dataset CSVs without modifying them; report schemas, likely "
            "battery/protocol/cycle fields, representative step indices, numeric "
            "ranges, and missing cell files. The default scans all rows."
        )
    )
    parser.add_argument("raw_root", nargs="?", help="raw dataset directory, CSV, or ZIP")
    parser.add_argument("--raw-root", dest="raw_root_option", help="same as positional raw_root")
    parser.add_argument(
        "--phase", choices=("primary", "second_life"), default="second_life",
        help="dataset phase to inspect (default: second_life)",
    )
    parser.add_argument(
        "--representative-files", type=int, default=2,
        help="number of first files whose unique step indices are reported",
    )
    parser.add_argument(
        "--max-rows-per-file", type=int,
        help="optional quick sample limit; omitted means scan every row",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="omit per-file detail rows while keeping global ranges and representative files",
    )
    args = parser.parse_args(argv)
    raw_root = args.raw_root_option or args.raw_root
    if not raw_root:
        parser.error("provide a raw dataset root path")
    try:
        report = inspect_dataset(
            raw_root,
            phase=args.phase,
            representative_files=args.representative_files,
            max_rows_per_file=args.max_rows_per_file,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        parser.exit(2, f"inspect_dataset: error: {error}\n")
    if args.summary:
        report.pop("files", None)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

