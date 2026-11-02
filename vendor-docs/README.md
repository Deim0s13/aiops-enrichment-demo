# Vendor documentation

MessageHub is ACME Bank's fictional SaaS messaging provider, and this is its fictional public documentation: what an engineer would read when MessageHub throttles payments-notify (scenario S2) and no ACME runbook covers it.

Phase 05 publishes these pages, with a sitemap, from a small web server in the `vendor-messagehub` namespace behind a TLS route, reachable only through the cluster's router, so the enrichment service reads them as it would an outside site (DD29). The service researches them only for the services listed in `demo_research_sources` in the inventory, only when the evidence names MessageHub, and only when no approved runbook or resolution covers the failure. What it finds becomes researched fixes in the work note: cited by page and section, labelled as not approved by ACME, never with a job.

These pages are not approved knowledge, and are kept apart from `knowledge/` on purpose: nothing here is loaded into the knowledge index. Each page is split into sections by its `h2` headings, each section needs an `id`, and the `last-updated` meta tag is shown in the note as the date the page was updated.
