"""
Propose a new public release of motel-db as a pull request.

The full database lives in the private motel-data repository; this repository
carries only its release. After changing motel-data, run from this repository:

    python tools/publish_release.py --data ../motel-data
    python tools/publish_release.py                      # uses $MOTEL_DATA
    python tools/publish_release.py --no-push            # prepare the commit only

It builds the release from <data>/motel-db with tools/build_release.py,
replaces motel-db/ here with it, checks the result with --check, and, if
anything other than RELEASE.md changed, commits it on a new branch
sync/release-<motel-data commit>, pushes the branch, and opens a pull request
with the GitHub CLI. It uses your own git and gh login, so it needs no token.

It refuses to run unless this repository is on main, clean, and up to date with
origin/main, so the release commit contains nothing else.

Standard library plus PyYAML (through build_release.py).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_release  # noqa: E402

DB = ROOT / "motel-db"
# Files in the public motel-db that are not part of a release build.
KEEP = {"linked_entity_human/helper_linked_entity2human.ipynb", "unmapped_carrier_data/.gitkeep"}


def run(*args, cwd=ROOT, capture=True) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=capture, text=True)
    if result.returncode:
        raise SystemExit(f"failed: {' '.join(args)}\n{(result.stderr or '').strip()}")
    return (result.stdout or "").strip()


def require_clean_main() -> None:
    run("git", "fetch", "-q", "origin")
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        raise SystemExit(f"switch to main first (on {branch})")
    if run("git", "status", "--porcelain"):
        raise SystemExit("the working tree has changes; commit or stash them first")
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", "origin/main"):
        raise SystemExit("main differs from origin/main; run git pull first")


def replace_db(release: Path) -> None:
    """Make motel-db/ match the release, keeping the files in KEEP."""
    wanted = {p.relative_to(release).as_posix() for p in release.rglob("*") if p.is_file()}
    wanted.discard(build_release.MARKER)
    for path in sorted(p for p in DB.rglob("*") if p.is_file()):
        relative = path.relative_to(DB).as_posix()
        if relative not in wanted and relative not in KEEP:
            path.unlink()
    for relative in sorted(wanted):
        target = DB / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(release / relative, target)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Propose a new public release of motel-db.")
    parser.add_argument("--data", default=os.environ.get("MOTEL_DATA", ""),
                        help="checkout of the private motel-data repository (default: $MOTEL_DATA)")
    parser.add_argument("--no-push", action="store_true",
                        help="commit on a local branch but do not push or open a pull request")
    args = parser.parse_args(argv)
    if not args.data:
        raise SystemExit("pass --data ../motel-data or set MOTEL_DATA")
    data_db = Path(args.data).expanduser().resolve() / "motel-db"
    if not data_db.is_dir():
        raise SystemExit(f"no motel-db in {data_db.parent}")

    require_clean_main()
    source = run("git", "rev-parse", "--short=8", "HEAD", cwd=data_db)
    if run("git", "status", "--porcelain", "--", ".", cwd=data_db):
        raise SystemExit(f"{data_db} has uncommitted changes; commit them in motel-data first, "
                         "so the release names a real commit")

    with tempfile.TemporaryDirectory() as scratch:
        release = Path(scratch) / "motel-db"
        if build_release.build(data_db, release):
            return 1
        replace_db(release)

    if build_release.check(DB):
        run("git", "checkout", "--", "motel-db")
        run("git", "clean", "-fdq", "--", "motel-db")
        raise SystemExit("the result is not a release; motel-db/ was restored")

    changed = run("git", "status", "--porcelain", "--", "motel-db", ":!motel-db/RELEASE.md")
    if not changed:
        run("git", "checkout", "--", "motel-db")
        print("\nThe release is unchanged; nothing to propose.")
        return 0

    branch = f"sync/release-{source}"
    run("git", "switch", "-c", branch)
    run("git", "add", "motel-db")
    run("git", "commit", "-q", "-m",
        f"Update the release from motel-data {source}\n\n"
        "Built by tools/build_release.py: only values backed exclusively by "
        "permitted sources. See motel-db/RELEASE.md and motel-db/WITHHELD.csv.")
    print(f"\nCommitted the new release on {branch}:")
    print(run("git", "show", "--stat", "--format=", "HEAD"))
    if args.no_push:
        print("\nNot pushed (--no-push). To publish: "
              f"git push -u origin {branch}, then open a pull request.")
        return 0

    run("git", "push", "-q", "-u", "origin", branch, capture=False)
    if shutil.which("gh"):
        print(run("gh", "pr", "create", "--base", "main", "--head", branch,
                  "--title", f"Update the release from motel-data {source}",
                  "--body", f"Built by `tools/build_release.py` from motel-data at `{source}`. "
                            "Only values backed exclusively by permitted sources; see "
                            "`motel-db/RELEASE.md` and `motel-db/WITHHELD.csv`."))
    else:
        print(f"Pushed {branch}; open the pull request on GitHub.")
    run("git", "switch", "-q", "main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
