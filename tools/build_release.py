"""
Build the public release of motel-db: every record and every citation, but only
the values whose sources permit redistribution.

motel-db/ holds values extracted from third-party sources, and many of those
sources do not allow their numbers to be republished (see the licence columns of
secondary/source.csv). This script writes a copy of the database in which those
values are withheld, so that what MOTEL distributes under CC BY 4.0 (the data
explorer, its downloads, a release archive) carries only cleared values. The
repository itself still holds the full data.

It is standalone — standard library plus PyYAML, no imports from this repository
— like tools/validate_unmapped.py.

Usage
-----
    python tools/build_release.py
    python tools/build_release.py --db motel-db --out dist/motel-db
    python tools/build_release.py --check motel-db

--db defaults to $MOTEL_DATA/motel-db when MOTEL_DATA is set (a checkout of
the private motel-data repository), else to motel-db/ in this repository.

--check builds into a temporary folder and exits with status 1 unless nothing
had to be withheld, which is how the public repository proves that the motel-db
it carries is already a release.

The rule
--------
A value is released only when at least one source is linked to it and every
source linked to it is marked ``permitted``. Everything else is withheld, for
one of three reasons:

- ``not_permitted``: a linked source does not allow redistribution
- ``unknown``: a linked source has no decision recorded yet
- ``no_source``: no source is linked to the value, so nobody can say whether it
  may be redistributed. Linking a cleared source to it at ingest releases it.

A source covers a value when its linked attributes name the value's attribute
or ``ALL``; ``ratios_in`` and ``ratios_out`` cover the balancing shares.

Where each decision comes from:

- a staging source: the record itself and, once the source is harmonised, also
  secondary/source.csv; if the two disagree the stricter one applies
- a linked record's sources: secondary/source.csv
- linked_entity_human/, a projection of linked_entity/: judged by the sources of
  the canonical record with the same ID, so a stale copy cannot release what
  the canonical record withholds

The run reports each disagreement and each stale record it finds.

Withholding removes the value and keeps everything around it: the record, its
scope, its carriers, and the citation of every source, so a reader can see what
exists and fetch the numbers from the source. Attribute and value entries are
removed whole, uncertainty included; balancing shares are set to null.

Every withheld value is listed, without the value, in WITHHELD.csv next to the
copied database, and RELEASE.md summarises the run. The script then re-reads its
own output and exits with status 1 if any value that should have been withheld
is still in it. A file it does not know how to filter also stops the run, so a
new kind of data cannot reach the release unchecked.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import shutil
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - dependency guidance
    sys.exit("PyYAML is required: pip install pyyaml")


ROOT = Path(__file__).resolve().parents[1]

# Folders of records whose values are filtered, by record shape.
STAGING_DIRS = ("unmapped_entity", "unmapped_carrier_data")
LINKED_DIRS = ("linked_entity", "linked_carrier_data", "linked_entity_human")
# Linked folders that are projections of a canonical one, judged by its sources.
PROJECTION_DIRS = ("linked_entity_human",)
# Folders of names, IDs, and mappings only; copied unchanged.
PLAIN_DIRS = ("controlled_vocabulary", "secondary", "mapping", "supplementary")
# Local runtime state and notebooks; never part of a release.
SKIPPED_DIRS = ("_backup", "log")
SKIPPED_SUFFIXES = (".ipynb",)

# Written into --out, so a rerun only ever deletes a folder this script made.
MARKER = ".motel-release"

PERMITTED = "permitted"
ALL = "ALL"
REASONS = ("no_source", "not_permitted", "unknown")
# Pseudo-attributes that link a source to the balancing shares.
BALANCING_LINKS = {"inputs": "ratios_in", "outputs": "ratios_out"}
STRICTNESS = {PERMITTED: 0, "unknown": 1, "not_permitted": 2}

WITHHELD_COLUMNS = ["file", "record", "subject", "item", "time_index", "reason", "sources"]


def status_of(value) -> str:
    """A blank decision is an unknown one."""
    return str(value or "").strip() or "unknown"


def stricter(a: str, b: str) -> str:
    return max(a, b, key=lambda status: STRICTNESS.get(status, 1))


def verdict(statuses: list[str]) -> str | None:
    """None when a value may be released, otherwise the reason it is withheld."""
    if not statuses:
        return "no_source"
    if all(status == PERMITTED for status in statuses):
        return None
    return "not_permitted" if "not_permitted" in statuses else "unknown"


def link_token(link) -> str:
    """
    Reduce an attribute, source, or record reference to the token it is matched on.

    Staging links are plain names. Linked records use IDs, which the
    human-readable copy writes as ``ATTR_00001 (Name)``, and mark names that
    never resolved as ``[unregistered: ratios_in]``.
    """
    text = str(link or "").strip()
    if text.startswith("[unregistered:") and text.endswith("]"):
        return text[len("[unregistered:"):-1].strip()
    return text.split(" (", 1)[0]


def record_id(record: dict) -> str:
    return link_token(record.get("linked_entity_id") or record.get("linked_carrier_data_id"))


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_records(path: Path) -> list:
    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [records] if isinstance(records, dict) else records


class Registry:
    """The redistribution decisions, and what the run noticed while applying them."""

    def __init__(self, db: Path):
        self.decisions = {
            row["source_id"].strip(): status_of(row.get("redistribution_permitted"))
            for row in read_csv(db / "secondary" / "source.csv")
            if (row.get("source_id") or "").strip()
        }
        self.source_ids = {
            row["original_name"].strip(): row["source_id"].strip()
            for row in read_csv(db / "mapping" / "source_map.csv")
            if (row.get("original_name") or "").strip() and (row.get("source_id") or "").strip()
        }
        # Sources of each canonical linked record, by record ID.
        self.canonical = {}
        for folder in LINKED_DIRS:
            if folder in PROJECTION_DIRS:
                continue
            for path in sorted((db / folder).glob("*.y*ml")):
                for record in read_records(path):
                    if isinstance(record, dict) and record_id(record):
                        self.canonical[record_id(record)] = self.linked_sources(record)
        self.conflicts = set()
        self.stale = set()

    def staging_sources(self, record: dict) -> list:
        """(label, decision, linked tokens) for each source cited by a staging record."""
        sources = []
        for entry in record.get("sources") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("source_name") or "?"
            decision = status_of(entry.get("redistribution_permitted"))
            source_id = self.source_ids.get(name)
            registered = self.decisions.get(source_id)
            if registered and registered != decision:
                self.conflicts.add((name, source_id, decision, registered))
                decision = stricter(decision, registered)
            links = {link_token(link) for link in entry.get("linked_attribute") or []}
            sources.append((name, decision, links))
        return sources

    def linked_sources(self, record: dict) -> list:
        """(label, decision, linked tokens) for each source cited by a linked record."""
        sources = []
        for entry in record.get("sources") or []:
            if not isinstance(entry, dict):
                continue
            source_id = link_token(entry.get("source_id"))
            links = entry.get("linked_attributes", entry.get("linked_attribute_ids")) or []
            sources.append((source_id, self.decisions.get(source_id, "unknown"),
                            {link_token(link) for link in links}))
        return sources

    def projection_sources(self, record: dict, relative: str) -> list:
        """Sources of a projected record: the canonical record's, when there is one."""
        own = self.linked_sources(record)
        canonical = self.canonical.get(record_id(record))
        if canonical is None:
            return own
        if sorted((label, sorted(links)) for label, _, links in own) != \
                sorted((label, sorted(links)) for label, _, links in canonical):
            self.stale.add((relative, record_id(record)))
        return canonical


def filter_record(record: dict, sources: list, value_field: str, key_field: str,
                  where: dict, withheld: list) -> int:
    """
    Withhold every value of one record that its sources do not clear.

    Removes withheld entries from ``value_field``, nulls withheld balancing
    shares, appends one row per withheld item to ``withheld``, and returns the
    number of values released.
    """
    def covering(token):
        return [(label, decision) for label, decision, links in sources
                if ALL in links or token in links]

    def withhold(item, time_index, cover, reason):
        withheld.append({
            **where,
            "item": item,
            "time_index": time_index,
            "reason": reason,
            "sources": "; ".join(f"{label}={decision}" for label, decision in cover),
        })

    released = []
    for entry in record.get(value_field) or []:
        if not isinstance(entry, dict):
            continue
        cover = covering(link_token(entry.get(key_field)))
        reason = verdict([decision for _, decision in cover])
        if reason is None:
            released.append(entry)
        else:
            withhold(entry.get(key_field), entry.get("time_index"), cover, reason)
    if value_field in record:
        record[value_field] = released

    balancing = record.get("balancing") or {}
    for direction, link in BALANCING_LINKS.items():
        flows = [flow for flow in balancing.get(direction) or [] if isinstance(flow, dict)]
        if all(flow.get("share") is None for flow in flows):
            continue
        cover = covering(link)
        reason = verdict([decision for _, decision in cover])
        if reason is not None:
            for flow in flows:
                flow["share"] = None
            withhold(f"balancing.{direction}", None, cover, reason)

    return len(released)


def filter_file(path: Path, kind: str, relative: str, registry: Registry,
                withheld: list) -> tuple[list, int]:
    """Load one record file, filter every record, and return (records, values released)."""
    records = read_records(path)
    projection = relative.split("/", 1)[0] in PROJECTION_DIRS
    released = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if kind == "staging":
            where = {"file": relative, "record": index,
                     "subject": record.get("technology_name") or record.get("carrier_name")}
            released += filter_record(record, registry.staging_sources(record),
                                      "attributes", "attribute_name", where, withheld)
        else:
            sources = (registry.projection_sources(record, relative) if projection
                       else registry.linked_sources(record))
            where = {"file": relative, "record": record_id(record),
                     "subject": record.get("tech_id") or record.get("carrier_id")}
            released += filter_record(record, sources, "values", "attribute_id", where, withheld)
    return records, released


def classify(db: Path) -> tuple[list, list]:
    """Sort every file under db into (kind, path) jobs; return (jobs, unknown files)."""
    jobs, unknown = [], []
    for path in sorted(p for p in db.rglob("*") if p.is_file()):
        parts = path.relative_to(db).parts
        if parts[0] in SKIPPED_DIRS or path.suffix in SKIPPED_SUFFIXES or path.name == ".gitkeep":
            continue
        if parts == (MARKER,):
            continue
        # A release's own list, rewritten by every build; lets --check run on a release.
        if parts == ("WITHHELD.csv",):
            continue
        if path.suffix == ".md":
            jobs.append(("copy", path))
        elif len(parts) == 2 and parts[0] in STAGING_DIRS and path.suffix in (".yaml", ".yml"):
            jobs.append(("staging", path))
        elif len(parts) == 2 and parts[0] in LINKED_DIRS and path.suffix in (".yaml", ".yml"):
            jobs.append(("linked", path))
        elif len(parts) == 2 and parts[0] in PLAIN_DIRS and path.suffix == ".csv":
            jobs.append(("copy", path))
        else:
            unknown.append(path)
    return jobs, unknown


def prepare_out(out: Path, db: Path) -> None:
    """Empty --out, refusing to delete anything this script did not write."""
    if out == db or db in out.parents or out in db.parents:
        raise SystemExit(f"--out must lie outside the database and not contain it: {out}")
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise SystemExit(f"{out} exists and was not written by this script; "
                             "remove it or choose another --out")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("Written by tools/build_release.py; safe to delete.\n",
                              encoding="utf-8")


def git_version() -> str:
    try:
        result = subprocess.run(["git", "describe", "--always", "--dirty", "--tags"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def tally(released: Counter, withheld: list) -> list[tuple]:
    """(file, released, withheld by reason...) for every filtered file."""
    reasons = Counter((row["file"], row["reason"]) for row in withheld)
    return [
        (name, released[name], *(reasons[(name, reason)] for reason in REASONS))
        for name in sorted(released)
    ]


def write_withheld(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WITHHELD_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, version: str, rows: list[tuple]) -> None:
    lines = [
        "# MOTEL public release",
        "",
        f"Generated {datetime.date.today().isoformat()} from motel-db at `{version}` "
        "by `tools/build_release.py`.",
        "",
        "This is motel-db with every value withheld whose sources do not permit "
        "redistribution. A value is released only when at least one source is linked "
        "to it and every linked source is marked `permitted` in "
        "`secondary/source.csv`. Records, scopes, carriers, and source citations are "
        "kept, so a withheld value can be looked up in its source. `WITHHELD.csv` "
        "lists every withheld value, without the value.",
        "",
        "Withheld because: `no_source`, no source is linked to the value; "
        "`not_permitted`, a linked source does not allow redistribution; `unknown`, "
        "a linked source has no decision recorded yet. The same value appears in the "
        "staging file and in each linked file, so the rows below do not add up.",
        "",
        "| File | Released | " + " | ".join(f"`{reason}`" for reason in REASONS) + " |",
        "| ---- | -------: | " + " | ".join("-------:" for _ in REASONS) + " |",
        *(f"| `{name}` | " + " | ".join(str(count) for count in counts) + " |"
          for name, *counts in rows),
        "",
        "Source data retains the licence of its origin; see the repository's "
        "Licensing section.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build(db: Path, out: Path) -> int:
    jobs, unknown = classify(db)
    if unknown:
        listing = "\n".join(f"  {path.relative_to(db)}" for path in unknown)
        raise SystemExit("Cannot tell whether these files hold source values, so the "
                         f"release was not built:\n{listing}\n"
                         "Teach tools/build_release.py how to filter them first.")

    registry = Registry(db)
    prepare_out(out, db)
    # Keep the database's layout, empty folders included, so a consumer finds
    # every folder it expects.
    for folder in sorted(p for p in db.iterdir() if p.is_dir() and p.name not in SKIPPED_DIRS):
        (out / folder.name).mkdir()

    withheld, released = [], Counter()
    for kind, path in jobs:
        relative = path.relative_to(db).as_posix()
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "copy":
            shutil.copy2(path, target)
            continue
        records, released[relative] = filter_file(path, kind, relative, registry, withheld)
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(records, handle, sort_keys=False, allow_unicode=True)

    rows = tally(released, withheld)
    write_withheld(out / "WITHHELD.csv", withheld)
    write_summary(out / "RELEASE.md", git_version(), rows)

    for name, source_id, staged, registered in sorted(registry.conflicts):
        print(f"  NOTE    {name!r} is {staged} in staging but {registered} for {source_id} "
              "in secondary/source.csv; applied the stricter one")
    for relative in sorted({relative for relative, _ in registry.stale}):
        ids = sorted(identifier for name, identifier in registry.stale if name == relative)
        print(f"  NOTE    {relative} cites different sources than the canonical record for "
              f"{len(ids)} record(s) ({', '.join(ids[:5])}{', ...' if len(ids) > 5 else ''}); "
              "judged by the canonical sources. Regenerate it.")
    for name, count, *reasons in rows:
        detail = ", ".join(f"{n} {reason}" for n, reason in zip(reasons, REASONS) if n)
        print(f"  {name}: {count} released, {sum(reasons)} withheld"
              + (f" ({detail})" if detail else ""))
    print(f"\nWrote {out}")

    # Read the release back and apply the rule again: nothing may be withheld twice.
    leaks = []
    for kind, path in jobs:
        if kind != "copy":
            relative = path.relative_to(db).as_posix()
            filter_file(out / relative, kind, relative, registry, leaks)
    if leaks:
        for row in leaks[:20]:
            print(f"  LEAK    {row['file']}[{row['record']}] {row['item']}: {row['reason']}")
        print(f"\n{len(leaks)} withheld value(s) are still in {out}; do not publish it.")
        return 1
    return 0


def check(db: Path) -> int:
    """Exit status 0 only when db is already a release: nothing left to withhold."""
    with tempfile.TemporaryDirectory() as scratch:
        status = build(db, Path(scratch) / "motel-db")
        withheld = read_csv(Path(scratch) / "motel-db" / "WITHHELD.csv")
    if status:
        return status
    if withheld:
        print(f"\n{db} is not a release: {len(withheld)} withheld entries, counted per "
              "file. Publish the output of tools/build_release.py, not the full database.")
        return 1
    print(f"\n{db} is a release: every value is backed by permitted sources only.")
    return 0


def default_db() -> Path:
    data_root = os.environ.get("MOTEL_DATA", "").strip()
    return Path(data_root).expanduser() / "motel-db" if data_root else ROOT / "motel-db"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write motel-db with every value withheld whose sources do not "
                    "permit redistribution.",
    )
    parser.add_argument("--db", default=str(default_db()),
                        help="database to release (default: $MOTEL_DATA/motel-db, else <repo>/motel-db)")
    parser.add_argument("--out", default=str(ROOT / "dist" / "motel-db"),
                        help="folder to write the release to (default: <repo>/dist/motel-db)")
    parser.add_argument("--check", metavar="DB",
                        help="verify that DB is already a release instead of building one")
    args = parser.parse_args(argv)
    if args.check:
        return check(Path(args.check).resolve())
    return build(Path(args.db).resolve(), Path(args.out).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
