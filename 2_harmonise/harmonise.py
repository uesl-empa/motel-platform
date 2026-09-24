"""
Harmonise staged technology records into the MOTEL database.

This is the command-line counterpart of ``2_data_harmonisation.ipynb`` and the
way to add a new source to a populated database. Registries, controlled
vocabularies, and mapping tables are appended to; existing IDs are never
renumbered, and names resolved in earlier runs are reused without an LLM call.

Usage
-----
    python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_dac.yaml
    python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_dac.yaml --limit 1
    python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_dac.yaml --llm-provider ollama
    python 2_harmonise/harmonise.py motel-db/unmapped_entity/ --no-llm

Paths may be files or directories; directories are searched for ``*.yaml``.
Files whose records are all mapped already are skipped.

For each run the script:

1. validates the staging records against ``schema/unmapped_entity_technology.yaml``
   and stops before touching the database if any record is invalid,
2. backs up the derived database files to ``motel-db/_backup/``,
3. harmonises the pending records (Claude by default, a local Ollama model with
   ``--llm-provider ollama``, exact match with ``--no-llm``), appends linked
   entities, and merges the mapping tables,
4. checks the foreign keys of the linked entities it created.

Claude needs ``ANTHROPIC_API_KEY`` (or another credential the Anthropic SDK
resolves); the local model needs a running Ollama server. See ``llm_client.py``
for the provider and model settings.

Exit status is 1 when staging validation fails or a created record has a
broken reference, 0 otherwise.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harmonise_helpers as hh  # noqa: E402


def collect_staging_files(targets):
    """Expand files and directories into a sorted list of staging YAML files."""
    files = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            files.extend(sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")))
        elif path.exists():
            files.append(path)
        else:
            raise SystemExit(f"No such file or directory: {target}")
    return files


def validate_staging(files):
    """Run tools/validate_unmapped.py on the staging files; returns its exit status."""
    validator_path = hh.PROJECT_ROOT / "tools" / "validate_unmapped.py"
    spec = importlib.util.spec_from_file_location("validate_unmapped", validator_path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    return validator.main([
        *(str(path) for path in files),
        "--schema", "unmapped_entity_technology",
        "--schema-dir", str(hh.SCHEMA_DIR),
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Harmonise staged technology records into motel-db.",
    )
    parser.add_argument("paths", nargs="+", help="staging YAML files or directories")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="harmonise only the first N pending records of each file (for a trial run)",
    )
    parser.add_argument(
        "--llm-provider", choices=hh.llm_client.PROVIDERS, default=None,
        help="LLM backend: anthropic (Claude, the default) or ollama (local model); "
             "overrides MOTEL_LLM_PROVIDER",
    )
    parser.add_argument(
        "--model", default=None,
        help="model name, e.g. claude-opus-5 or qwen3:14b; overrides MOTEL_LLM_MODEL",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="resolve by exact name match instead of an LLM; needs no API key or server",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="skip the backup of derived files before writing",
    )
    parser.add_argument(
        "--skip-staging-validation", action="store_true",
        help="harmonise even if the staging records fail validation",
    )
    args = parser.parse_args(argv)

    if not args.no_llm:
        settings = hh.llm_client.configure(provider=args.llm_provider, model=args.model)
        print(f"LLM: {settings['provider']} ({settings['model']})")

    files = collect_staging_files(args.paths)
    if not files:
        print("No staging files found.")
        return 0

    if not args.skip_staging_validation and validate_staging(files) != 0:
        print("\nStaging validation failed; nothing was written to motel-db.")
        return 1

    if not args.no_backup:
        hh.backup_derived_data()

    created_ids = []
    for path in files:
        print(f"\n=== {hh._relative_to_root(path)} ===")
        result = hh.run_harmonisation(
            path,
            use_llm=not args.no_llm,
            test_limit=args.limit,
            create_backup=False,
        )
        created_ids.extend(le["linked_entity_id"] for le in result["linked_entities"])

    if not created_ids:
        print("\nNo new linked entities were created.")
        return 0

    problems = hh.validate_linked_entities(linked_entity_ids=created_ids)
    print(f"\nCreated {len(created_ids)} linked entities: {created_ids[0]} .. {created_ids[-1]}")
    if problems:
        print(f"Validation found {len(problems)} problem(s) in the new records:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Validation: every reference in the new records resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
