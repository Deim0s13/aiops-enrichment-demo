# payments-notify sample service

A small Java service for the fictional organisation, with an endpoint that grows the heap until the container is terminated for exceeding its memory limit. It gives the demo a fault that can be triggered on demand and diagnosed from standard metrics (DD01).

Phase 05 builds it in-cluster and deploys it to the `demo-payments` namespace with alert rules for heap usage and restarts.
