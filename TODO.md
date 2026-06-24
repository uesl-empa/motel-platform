1. link with ontology [to be decided]
2. link with MOTEL webapp! [ongoing]


breakdown of the whole database building workflow:
 - collect data -> a specific template/schema for input data (unmapped)
    - challenge: convert LLM/reFuel.ch data to unmapped
 - data harmonisation -> based on new (unmapped) and existing data (in the motel-db) to create a mapped data
 - use the mapped data to create knowlege graph (graphDB)



 [2026-06-23]
 1. complete the documentation, especially step 2 harmoisation
 2. run more test for step 2 (all entity, start from beginning)
 3. how to deal with duplicate date/run? does the script can detect that (seperate process and unprocessed)