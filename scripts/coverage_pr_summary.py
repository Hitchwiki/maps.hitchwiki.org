"""Create a concise, repeatable coverage comment for a GitHub pull request."""

import argparse
from pathlib import Path
from xml.etree import ElementTree


MARKER = "<!-- hitchwiki-maps-coverage-report -->"


def percent(value):
    """Format coverage.py's decimal rates as percentages."""
    return f"{float(value) * 100:.2f}%"


def status(result):
    return "✅ Passing" if result == "success" else f"❌ {result.capitalize()}"


def python_coverage(path):
    if not path.is_file():
        return "—", "—"
    root = ElementTree.parse(path).getroot()
    return percent(root.attrib["line-rate"]), percent(root.attrib["branch-rate"])


def javascript_coverage(path):
    """Read the aggregate line emitted by Node's experimental coverage report."""
    if not path.is_file():
        return "—", "—", "—"
    for line in path.read_text().splitlines():
        values = [value.strip() for value in line.split("|")]
        values[0] = values[0].removeprefix("#").removeprefix("ℹ").strip()
        if values and values[0] == "all files" and len(values) >= 4:
            return tuple(
                f"{value}%" if not value.endswith("%") else value
                for value in values[1:4]
            )
    return "—", "—", "—"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-status", required=True)
    parser.add_argument("--javascript-status", required=True)
    parser.add_argument("--python-report", type=Path, required=True)
    parser.add_argument("--javascript-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    python_lines, python_branches = python_coverage(args.python_report)
    js_lines, js_branches, js_functions = javascript_coverage(args.javascript_report)
    body = f"""{MARKER}
## Coverage overview

| Suite | Status | Lines | Branches | Functions |
| --- | --- | ---: | ---: | ---: |
| Python (`hitch/`) | {status(args.python_status)} | {python_lines} | {python_branches} | — |
| JavaScript unit tests | {status(args.javascript_status)} | {js_lines} | {js_branches} | {js_functions} |

Coverage is collected from the deterministic pull-request suite. Live Nostr relay checks remain excluded so a third-party outage cannot make a PR flaky.
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body)


if __name__ == "__main__":
    main()
