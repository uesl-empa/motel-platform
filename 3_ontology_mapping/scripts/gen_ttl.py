"""Command-line entrypoint for motel-db TTL generation.

This script is a thin wrapper around ``generator_core.py``.
Use it when you want to regenerate ``3_ontology_mapping/output_ttl/cls_atr_motel.ttl``
without running the notebook.

The notebook ``ttl_creation_from_motel_db.ipynb`` should use the same shared
logic so both paths produce the same TTL output.
"""

from generator_core import DEFAULT_MOTEL_DB_PATH
from generator_core import DEFAULT_OUTPUT_TTL
from generator_core import write_ttl_output


def main() -> None:
    # Keep this file as a small entrypoint so the notebook and script both reuse
    # the shared generation logic from generator_core.py.
    result = write_ttl_output(
        path_motel_db=DEFAULT_MOTEL_DB_PATH,
        output_ttl=DEFAULT_OUTPUT_TTL,
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
    if warnings:
        print(f"Warnings: {len(warnings):,}")
        for warning in warnings[:20]:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
