"""Command-line entrypoint for motel-db TTL generation.

This script is a thin wrapper around ``generator_core.py``.
Use it when you want to regenerate ``3_ontology_mapping/output_ttl/cls_atr_motel.ttl``
without running the notebook.

The output is not committed: it carries every value of the database it is built
from. The Deploy Docs workflow publishes one built from the public release.

Usage:
    python 3_ontology_mapping/scripts/gen_ttl.py
    python 3_ontology_mapping/scripts/gen_ttl.py --db dist/motel-db --out docs/data/cls_atr_motel.ttl

The notebook ``ttl_creation_from_motel_db.ipynb`` should use the same shared
logic so both paths produce the same TTL output.
"""

import argparse

from generator_core import DEFAULT_MOTEL_DB_PATH
from generator_core import DEFAULT_OUTPUT_TTL
from generator_core import write_ttl_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the MOTEL TTL from a motel-db.")
    parser.add_argument("--db", default=str(DEFAULT_MOTEL_DB_PATH),
                        help="database to read (default: motel-db, or $MOTEL_DATA/motel-db)")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_TTL), help="TTL file to write")
    args = parser.parse_args()

    # Keep this file as a small entrypoint so the notebook and script both reuse
    # the shared generation logic from generator_core.py.
    result = write_ttl_output(
        path_motel_db=args.db,
        output_ttl=args.out,
        generated_by="gen_ttl.py",
    )
    ttl = str(result["ttl"])
    stats = result["stats"]
    warnings = result["warnings"]
    output_path = result["output_ttl"]

    print(f"Written: {output_path}")
    print(f"Lines: {ttl.count(chr(10)):,}")
    print(f"hasAttributeValue triples: {ttl.count('dici_onto:hasAttributeValue'):,}")
    print(f"Flow nodes: {stats['flows']:,}")
    print(f"Carrier data nodes: {stats['carrier_data']:,}")
    if warnings:
        print(f"Warnings: {len(warnings):,}")
        for warning in warnings[:20]:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
