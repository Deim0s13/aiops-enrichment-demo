# Event-Driven Ansible rulebooks

AAP looks for rulebooks in this directory when the repository is added as an EDA project.

| Rulebook | Purpose | Design reference |
|---|---|---|
| `integration_alerts.yml` (written) | Receives Alertmanager notifications through an event stream with Basic authentication, and launches the integration stand-in's job with only their alerts | Section 2.1, step 1; DD19 |
| `incident_enrichment.yml` (written) | Receives qualifying ServiceNow incidents through the event stream, checks the incident fields and launches the enrichment workflow with only those fields | Section 5.1 |
