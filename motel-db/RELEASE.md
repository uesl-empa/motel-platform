# MOTEL public release

Generated 2026-10-21 from motel-db at `v0.3.0-17-g32982eb` by `tools/build_release.py`.

This is motel-db with every value withheld whose sources do not permit redistribution. A value is released only when at least one source is linked to it and every linked source is marked `permitted` in `secondary/source.csv`. Records, scopes, carriers, and source citations are kept, so a withheld value can be looked up in its source. `WITHHELD.csv` lists every withheld value, without the value.

Withheld because: `no_source`, no source is linked to the value; `not_permitted`, a linked source does not allow redistribution; `unknown`, a linked source has no decision recorded yet. The same value appears in the staging file and in each linked file, so the rows below do not add up.

The free-text notes of sources that are not permitted are withheld too (18 in all), because notes tend to restate a source's numbers.

| File | Released | `no_source` | `not_permitted` | `unknown` |
| ---- | -------: | -------: | -------: | -------: |
| `linked_carrier_data/linked_carrier_data.yaml` | 0 | 0 | 0 | 0 |
| `linked_entity/linked_entity.yaml` | 470 | 1496 | 75 | 177 |
| `linked_entity_human/linked_entity.yaml` | 470 | 1496 | 75 | 177 |
| `unmapped_entity/unmapped_entities_dac.yaml` | 12 | 8 | 18 | 0 |
| `unmapped_entity/unmapped_entities_refuel.yaml` | 470 | 1496 | 75 | 177 |

Source data retains the licence of its origin; see the repository's Licensing section.
