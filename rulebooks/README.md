# Event-Driven Ansible rulebooks

AAP looks for rulebooks in this directory when the repository is added as an EDA project.

| Rulebook | Purpose | Design reference |
|---|---|---|
| `integration_alerts.yml` (written) | Receives Alertmanager notifications through an event stream with Basic authentication, and launches the integration stand-in's job with only their alerts | Section 2.1, step 1; DD19 |
| `incident_enrichment.yml` (written) | Receives qualifying ServiceNow incidents through the event stream, checks the incident fields and launches the enrichment workflow with only those fields; an incident resolved with Knowledge ticked launches the knowledge bot's draft instead | Section 5.1; DD33 |
| `knowledge_refresh.yml` (written) | Receives the knowledge bot App's pushes to `main` through an event stream that checks GitHub's signature, and launches the index refresh with only the commits | DD34 |
