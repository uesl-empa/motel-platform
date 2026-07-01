# Public Release TODO

This file tracks remaining work before the repository is announced publicly.

## Data Quality

- Verify that all `motel-db/` records can be released under compatible source-data licenses.
- Review generated mapping tables for duplicate records and rerun harmonisation where needed.
- Confirm attribute names follow the schema naming guidance.
- Ensure each unmapped entity has a `harmonisation_record.mapping_status`.
- Record the LLM model and harmonisation settings used for each production run.


## TODO

- [] check the whole workflow again, after assessment_date was change to reference_year (link to ontology!?)
- [] the harmonisation process seem not working with non-empty datasets in motel-db
- [] in source, the LLM cannot identify which one is journal paper

## DONE
- [x] more guidelines needed to be added to classify technology and process, now the process.csv only has name but no other info.

## Future Work
- add mathmatical equations in the secondary datasets or a property of attributes [this was mentioned in the MOTEL proposal but do not address in the project duration]