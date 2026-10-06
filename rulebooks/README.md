# Event-Driven Ansible rulebooks

AAP looks for rulebooks in this directory when the repository is added as an EDA project.

| Rulebook (planned) | Purpose | Design reference |
|---|---|---|
| `integration_alerts.yml` | Receives Alertmanager alerts and launches the integration stand-in | Section 2.1, step 1 |
| `incident_enrichment.yml` | Receives qualifying ServiceNow incidents, validates the fields and launches the enrichment workflow | Section 5.1 |
