# payments-notify sample service

A small Java service for the fictional organisation, with an endpoint that grows the heap until the container is terminated for exceeding its memory limit. It gives the demo a fault that can be triggered on demand and diagnosed from standard metrics (DD01).

Phase 08 builds it in the cluster and deploys it to the `demo-payments` namespace with its heap metrics and alert rules (DD18). `PaymentsNotify.java` is the whole service: the JDK's HTTP server, `/healthz`, `/metrics` and `POST /fault?scenario=single|recurring` or `/fault/clear`. How to trigger the fault in a demo is in the build guide, section 13.
