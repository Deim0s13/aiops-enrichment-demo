# Enrichment service

A small Python web service (organisation-built, C) that receives incident fields and evidence from the AAP workflow, retrieves approved passages from the knowledge index, calls the model through the OpenShift AI gateway with its own key, and validates the structured output and every citation before returning it.

It holds no ITSM, cluster or AAP credentials (P3). Phase 06 builds the image in-cluster from this directory with OpenShift Builds (DD08), so no external registry is needed.

Until milestone M4 it is a skeleton (`app/main.py`): it checks the caller's token and the request, including each evidence item against the design 5.2 format, and answers in the design 5.3 shape, listing the evidence it received as symptoms, each citing its item, and the diagnostics' gaps, without drawing conclusions. Phase 06 builds it, serves it over TLS from OpenShift's service CA on port 8443, and admits only AAP's jobs.

The request and response contract, sanitisation and validation rules are defined in section 5.3 of the implementation design. The same image runs the knowledge ingestion job and its check (phase 05, DD21): `app/knowledge.py` holds the shared parts (splitting documents into passages, the embedding model baked into the image, and filtered search), `app/ingest.py` loads the corpus as the ingestion identity, and `app/knowledge_check.py` searches as the read-only identity the service will use.
