from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW_DIR = Path(__file__).resolve().parent

COMMANDS = [
    (
        WORKFLOW_DIR / "ingest_harmonise.mmd",
        REPO_ROOT / "docs" / "assets" / "ingest_harmonise.svg",
    ),
    (
        WORKFLOW_DIR / "ontology_graphdb.mmd",
        REPO_ROOT / "docs" / "assets" / "ontology_graphdb.svg",
    ),
]


def find_browser() -> str | None:
    candidates = [
        os.environ.get("PUPPETEER_EXECUTABLE_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    if not mmdc:
        print("Could not find `mmdc` on PATH.", file=sys.stderr)
        return 1

    env = os.environ.copy()
    browser = find_browser()
    if browser:
        env["PUPPETEER_EXECUTABLE_PATH"] = browser
        print(f"Using browser: {browser}")
    else:
        print(
            "No local Chrome/Edge executable found. Mermaid CLI may fail if Puppeteer has no bundled browser.",
            file=sys.stderr,
        )

    for source, output in COMMANDS:
        output.parent.mkdir(parents=True, exist_ok=True)
        print(f"Rendering {source} -> {output}")
        result = subprocess.run(
            [mmdc, "-i", str(source), "-o", str(output)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
