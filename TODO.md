[to be update!]

1. review the workflow
2. finish the basic input (with guideline, maybe use LLM for next step)
3. link with ontology
4. link with MOTEL webapp!


put develop and put ontology here!

challenge:
 - linked all works together:
 - how to add data to MOTEL is not clear


breakdown of the whole database building workflow:
 - collect data -> a specific template/schema for input data (unmapped)
    - challenge: convert LLM/reFuel.ch data to unmapped
 - data harmonisation -> based on new (unmapped) and existing data (in the motel-db) to create a mapped data
 - use the mapped data to create knowlege graph (graphDB)



 [2026-06-23]
 1. complete the documentation, especially step 2 harmoisation
 2. run more test for step 2 (all entity, start from beginning)
 3. how to deal with duplicate date/run? does the script can detect that (seperate process and unprocessed)