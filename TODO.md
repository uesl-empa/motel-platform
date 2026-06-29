# Public Release TODO

This file tracks remaining work before the repository is announced publicly.

## Data Quality

- Verify that all `motel-db/` records can be released under compatible source-data licenses.
- Review generated mapping tables for duplicate records and rerun harmonisation where needed.
- Confirm attribute names follow the schema naming guidance.
- Ensure each unmapped entity has a `harmonisation_record.mapping_status`.
- Record the LLM model and harmonisation settings used for each production run.

## Documentation

- Add final project contact and citation information.
- Replace placeholder values in `CITATION.cff` once a DOI or preferred citation is available.
- Add a short contributor guide if external submissions are expected.

## Future Work

- Link harmonised records to the MOTEL ontology/graph workflow.
- Connect the curated database to the MOTEL web application.
- add mathmatical equations in the secondary datasets or a property of attributes [this was mentioned in the MOTEL proposal but do not address in the project duration]
- more guidelines needed to be added to classify technology and process, now the process.csv only has name but no other info.