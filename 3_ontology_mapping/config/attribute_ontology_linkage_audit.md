# Attribute Ontology Mapping Notes

This folder now separates machine-readable runtime config from human-readable support notes.

## Runtime files

- `attribute_ontology_mapping.yaml`
  Canonical attribute-to-ontology mapping used by `scripts/generator_core.py`.
- `unit_mappings.yaml`
  Unit, flow, capacity-basis, and energy-carrier config used by `scripts/generator_core.py`.

## Support file

- `attribute_ontology_linkage_audit.md`
  Lightweight review notes, maintenance reminders, and context for future updates.

## What to check when mappings change

- Every attribute in `motel-db/controlled_vocabulary/attribute.csv` that should be exported has an entry in `attribute_ontology_mapping.yaml`.
- Each entry defines `ontology_class`, `category_class`, and `dtype`.
- Alias spellings in YAML match the source names seen in `linked_entity.yaml`.
- Any new unit labels are covered in `unit_mappings.yaml`.
- Cost-per-capacity units still resolve to a valid capacity basis.

## Current mapped attribute keys

- `trl`
- `tech_maturity`
- `technical_efficiency`
- `theoretical_efficiency`
- `operating_temperature_c`
- `lifetime_yr`
- `capex_one_time`
- `capex_per_capacity`
- `opex_one_time`
- `opex_fix_pct_of_capex`
- `opex_per_capacity_yr`
- `opex_per_energy`
- `min_installation_size`
- `uncertainty_rating`
- `discount_rate_pct`
- `reference_unit_size`

## Maintenance guidance

- Prefer changing YAML when the update is a mapping-data change.
- Prefer changing `generator_core.py` when the update is parsing, validation, URI generation, or TTL-generation logic.
- Keep the notebook high-level; it should call shared functions rather than embed mapping logic.
