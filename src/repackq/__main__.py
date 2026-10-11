"""Project commands; training modules load only when requested."""
import argparse
import importlib
import sys

COMMANDS = {
    "dashboard": "repackq.dashboard.server",
    "compare": "repackq.classical.compare",
    "predict": "repackq.prediction.predict",
    "prepare": "repackq.data.prepare",
    "train": "repackq.training.train",
}


def main(argv=None):
    """Run the requested project command."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="repackq", description="Battery prediction and classical/quantum group selection.",
        epilog="Use repackq COMMAND --help for command options. Training is optional.")
    parser.add_argument("command", choices=COMMANDS,
                        help="open the dashboard, compare groups, predict capacity, prepare histories, or train offline")
    if not args:
        parser.print_help()
        return 0
    parsed = parser.parse_args(args[:1])
    original_argv = sys.argv
    try:
        sys.argv = [f"repackq {parsed.command}", *args[1:]]
        return importlib.import_module(COMMANDS[parsed.command]).main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    sys.exit(main())
