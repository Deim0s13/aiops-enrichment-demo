# Enrichment service

A small Python web service (organisation-built, C) that receives incident fields and evidence from the AAP workflow, retrieves approved passages from the knowledge index, calls the model through the OpenShift AI gateway with its own key, and validates the structured output and every citation before returning it.

It holds no ITSM, cluster or AAP credentials (P3). Phase 07 builds the image in-cluster from this directory with OpenShift Builds (DD08), so no external registry is needed.

The request and response contract, sanitisation and validation rules are defined in section 5.3 of the implementation design. The same image runs the knowledge ingestion job (phase 06).
