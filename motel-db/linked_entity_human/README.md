# Linked Entity Human

This folder contains a human-readable projection of the canonical linked-entity data.

- `../linked_entity/linked_entity.yaml`: canonical machine-oriented linked entities
- `linked_entity.yaml`: target human-readable export with foreign keys expanded as `ID (Name)`
- `helper_linked_entity2human.ipynb`: notebook helper for creating the human-readable export

Open the helper notebook and run it when you want to generate the export:

```bash
motel-db\linked_entity_human\helper_linked_entity2human.ipynb
```
