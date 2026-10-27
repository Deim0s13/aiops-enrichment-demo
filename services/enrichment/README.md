# Enrichment service

A small Python web service (organisation-built, C) that receives incident fields and evidence from the AAP workflow, retrieves approved passages from the knowledge index, calls the model through the OpenShift AI gateway with its own key, and validates the structured output and every citation before returning it.

It holds no ITSM or AAP credentials (P3): only its own API token, which AAP presents, its gateway key, the read-only knowledge identity, and a one-hour token for its service account, mounted and renewed by OpenShift, which may only write traces to MLflow. Phase 06 builds the image in-cluster from this directory with OpenShift Builds (DD08), serves it over TLS from OpenShift's service CA on port 8443, and admits only AAP's jobs.

## What happens to a request

The contract is section 5.3 of the implementation design, and how each rule is applied is decision DD22.

| Step | Module | What it does |
|---|---|---|
| 1 | `app/main.py` | Checks the caller's token and the request: each evidence item against the design 5.2 format, the service's version and the catalogue |
| 2 | `app/sanitise.py` | Redacts tokens, keys, secret values, email addresses and Luhn-valid card numbers from the evidence and the incident description, and counts what it removed (rule 1) |
| 3 | `app/retrieval.py` | One question per evidence item, filtered on the service and its major version, as the read-only identity, leaving out sections that describe a document (Purpose, Scope and the like); keeps passages at or above the relevance threshold, at most five, and the best runbook brings its Diagnosis and Actions, the best resolution its Root cause and Resolution (rule 2, DD24) |
| 4 | `app/prompt.py` | The prompt (`enrichment-v2`) and a schema built for the request: the documented fix as next steps, the model's own ideas as low-trust suggestions citing evidence only, citations only from supplied IDs, the job only from the catalogue, and only `insufficient_evidence` when no passage met the threshold (DD24) |
| 5 | `app/model.py` | The gateway call, OpenAI-compatible, with constrained output; any failure becomes a reason that is safe to show (rule 3) |
| 6 | `app/policy.py` | Checks the answer again (`policy-v2`): drops unknown citations and jobs, turns a step with no approved passage into a suggestion and an answer that cites no passage into `insufficient_evidence`, keeps suggestions to observed evidence with no job, requires manual review where evidence is missing or suggestions are given (rules 4 and 5, DD24) |
| Throughout | `app/tracing.py` | One MLflow trace per request, a span per step, tagged with the incident, the versions and the AAP workflow job (DD23). Best effort: if MLflow cannot be reached the answer says the trace was not recorded, and MLflow is left alone for a minute |

The response adds `evidence_considered` (the sanitised evidence), `knowledge_used` (the passages and their scores, or the passage each was added with) and `checks_removed` to the design 5.3 fields, and its provenance records the versions, the candidates and their scores, what sanitisation removed, the tokens and the time the model took. If the knowledge index cannot be searched the service answers 503; if the model call fails it answers 502. The workflow writes either reason into its "AI enrichment unavailable" note.

## Settings

Set by phase 06 from the `enrichment_service` role's defaults and the inventory:

| Variable | Default | Purpose |
|---|---|---|
| `ENRICHMENT_RELEVANCE_THRESHOLD` | 0.80 | Passages below it are not sent to the model. Provisional until M4.7; phase 05 reports a calibration score to set it from |
| `ENRICHMENT_MAX_PASSAGES` | 5 | The best-matching passages sent for one incident |
| `ENRICHMENT_EXPAND_DOCUMENTS` | 1 | How many documents of each type bring their actionable sections |
| `ENRICHMENT_SKIP_SECTIONS` | Purpose, Scope, Related documents, Change history, Timeline | Section headings, by prefix, that are not searched |
| `ENRICHMENT_TEMPERATURE`, `ENRICHMENT_MAX_TOKENS` | 0.2, 1600 | The model's sampling and answer length |
| `MAAS_REQUEST_EXTRA` | `{}` | Model-specific request fields, such as Qwen3's thinking switch, from `demo_model.request_extra` |
| `MAAS_URL`, `MAAS_MODEL`, `MAAS_API_KEY` | | From the `maas-api-key` Secret (phase 02) |
| `KNOWLEDGE_DB_*` | | The read-only identity, from the `knowledge-reader-db` Secret (phase 05) |
| `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_AUTH`, `MLFLOW_EXPERIMENT_NAME` | | MLflow's in-cluster address from its resource, sign-in as the service account (`kubernetes-namespaced`), and the experiment, `aiops-enrichment` |
| `ENRICHMENT_TRACING` | `on` | `off` stops tracing |

## The knowledge index

The same image runs the knowledge ingestion job and its check (phase 05, DD21): `app/knowledge.py` holds the shared parts (splitting documents into passages, the embedding model baked into the image, and filtered search), `app/ingest.py` loads the corpus as the ingestion identity, and `app/knowledge_check.py` searches as the read-only identity the service uses, and reports the calibration score.

## Testing away from the cluster

`KNOWLEDGE_TEST_EMBEDDER=1` replaces the embedding model with a bag of hashed words, so the service runs against a local PostgreSQL with pgvector without downloading the model. Its scores are much lower than the real model's, so set a low `ENRICHMENT_RELEVANCE_THRESHOLD` when testing with it. Any OpenAI-compatible server that honours `response_format` can stand in for the gateway, and a local `mlflow server` (3.14) for MLflow, with `MLFLOW_TRACKING_URI` set and `MLFLOW_TRACKING_AUTH` unset.
