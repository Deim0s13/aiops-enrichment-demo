# Enrichment service

A small Python web service (organisation-built, C) that receives incident fields and evidence from the AAP workflow, retrieves approved passages from the knowledge index, calls the model through the OpenShift AI gateway with its own key, and validates the structured output and every citation before returning it.

It holds no ITSM, cluster or AAP credentials (P3). Phase 05 builds the image in-cluster from this directory with OpenShift Builds (DD08), so no external registry is needed.

Milestone M2 deploys a skeleton (`app/main.py`): it checks the caller's token and the request, and returns a fixed answer in the design 5.3 shape. Phase 06 builds it, serves it over TLS from OpenShift's service CA on port 8443, and admits only AAP's jobs.

The request and response contract, sanitisation and validation rules are defined in section 5.3 of the implementation design. The same image runs the knowledge ingestion job (phase 08).
