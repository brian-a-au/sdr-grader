"""Allow `python -m sdr_grader` to invoke the CLI once Phase 3 wires it up."""

from sdr_grader.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
