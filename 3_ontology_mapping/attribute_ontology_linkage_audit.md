# Attribute ontology linkage audit

This file is a lightweight tracking sheet for motel-db attribute harmonisation.

Use it to answer:

- which source attributes are mapped
- which ontology class each source attribute uses
- where that ontology class is defined
- whether backend compatibility is already wired
- what still needs review

## Current mapped attributes

| Source attribute name | Ontology class | Category class | Defined in | Backend field | Backend-compatible | Notes / review status |
|---|---|---|---|---|---|---|
| Technology Readiness Level | `TRL` | `PhysicalAttribute` | `motel_project.ttl` | `trl` | Yes | Existing ontology class reused |
| Technology Maturity | `tech_maturity` | `CategoricalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Technical Efficiency | `technical_efficiency` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Theoretical Efficiency | `theoretical_efficiency` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Operating Temperature | `operating_temperature_c` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Economic Lifetime | `Lifetime` | `PhysicalAttribute` | `motel_project.ttl` | `lifetime` | Yes | Existing ontology class reused |
| Capital Expenditure One Time | `CAPEXOneTime` | `SimpleCostAttribute` | `motel_project_ext.ttl` | `capex` | Yes | Backend alias added |
| One-Time Operational Expenditure | `OPEXOneTime` | `SimpleCostAttribute` | `motel_project_ext.ttl` | `opex` | Yes | Backend alias added |
| Fixed Operational Expenditure Percentage Of Capital Expenditure | `opex_fix_pct_of_capex` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Annual OPEX Per Capacity | `OPEXPerCapacity` | `UnitBasedCostAttribute` | `motel_project_ext.ttl` | `opex_cap` | Yes | Backend alias added |
| Operational Expenditure Per Energy | `OPEXPerEnergy` | `UnitBasedCostAttribute` | `motel_project_ext.ttl` | `opex_energy` | Yes | Backend alias added |
| Minimum Installation Size | `min_installation_size` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Uncertainty Rating | `uncertainty_rating` | `CategoricalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |
| Discount Rate | `InterestRate` | `PhysicalAttribute` | `motel_project.ttl` | `interest_rate` | Yes | Existing ontology class reused |
| Capex Per Capacity | `CAPEXPerCapacity` | `UnitBasedCostAttribute` | `motel_project_ext.ttl` | `capex_per_rated_power` | Yes | Backend alias added |
| Reference Unit Size | `reference_unit_size` | `PhysicalAttribute` | `motel_project_ext.ttl` |  | Partial | New extension class |

## Status meanings

| Status | Meaning |
|---|---|
| Yes | Ontology mapping exists and backend compatibility is already wired |
| Partial | Ontology mapping/class exists, but backend logic may not yet use it directly in all places |
| No | Not harmonised yet |

## Still to check regularly

- Any attributes present in `attribute.csv` but missing from `attribute_ontology_mapping.yaml`
- Any ontology classes used in the YAML but not defined in `motel_project.ttl` or `motel_project_ext.ttl`
- Any mapped attributes that still do not appear correctly in the frontend
- Any duplicate frontend rows caused by multiple references rather than ontology mapping

## Source files involved

- Source availability: [attribute.csv](C:/Repositories/motel-platform/motel-db) outside this repo
- Harmonisation: [attribute_ontology_mapping.yaml](/C:/Repositories/motel_ontology/app/ttl_creation/from_motel_db/attribute_ontology_mapping.yaml)
- Ontology base: [motel_project.ttl](/C:/Repositories/motel_ontology/app/data/00_ontology/extensions/motel_project.ttl)
- Ontology extension: [motel_project_ext.ttl](/C:/Repositories/motel_ontology/app/data/00_ontology/extensions/motel_project_ext.ttl)
- Generated instance data: [cls_atr_motel.ttl](/C:/Repositories/motel_ontology/app/data/01_classes_and_attributes/cls_atr_motel.ttl)
- Backend field mapping: [technology_attributes.py](/C:/Repositories/motel_ontology/backend/src/constants/technology_attributes.py)
