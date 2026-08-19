# Enterprise stack blueprints

A customer needs more than a Kubernetes cluster to build and run services. This repository defines the minimum software stack as reusable blueprints. Tenants can start with the standard SaaS stack and then opt in to extra capabilities.

## Blueprint layers

| Layer | Purpose | Default blueprint |
| --- | --- | --- |
| Runtime platform | Kubernetes namespace, RBAC, network boundaries, service accounts | `tenant-runtime` |
| Delivery | GitOps, CI/CD, preview environments, promotion gates | `software-delivery` |
| Application workloads | Web services, APIs, workers, scheduled jobs | `workload-web-service`, `workload-api-service`, `workload-worker-service` |
| Data | PostgreSQL, Redis, object storage, backups | `capability-postgres`, `capability-redis`, `capability-object-storage` |
| Integration | Event streaming, async messaging, webhooks | `capability-event-stream` |
| Identity | tenant-local OIDC provider, passkeys, groups, client provisioning | `capability-identity` |
| Security | secrets, policy, admission, image scanning, SBOM/signing | `capability-security-baseline` |
| Observability | metrics, logs, traces, dashboards, alerts | `capability-observability` |
| Developer experience | templates, golden paths, docs, local dev setup | `developer-experience` |
| AI/software factory | coding agents, workflow orchestration, repository automation | `software-factory` |

## Recommended standard SaaS stack

The `standard-saas` reference architecture gives a company the pieces required to build most internal and external services:

1. Tenant runtime namespace and RBAC.
2. GitOps deployment with Argo CD.
3. Crossplane control plane API for environments and services.
4. Web/API service blueprint.
5. Worker service blueprint.
6. PostgreSQL capability.
7. Redis capability.
8. Object storage capability.
9. Observability baseline.
10. Tenant-local identity provider, see `identity-pocket-id.md`.
11. Security baseline.
12. CI/CD and image promotion policy.
13. Software factory automation.

## Service API

Companies should not copy raw Kubernetes manifests for every service. They should create a namespaced composite resource:

```yaml
apiVersion: platform.example.org/v1alpha1
kind: ServiceBlueprint
metadata:
  name: checkout-api
  namespace: sf-customer-a-dev
spec:
  owner: payments-team
  blueprint: workload-api-service
  image: ghcr.io/example/checkout-api:1.0.0
  port: 8080
  replicas: 2
  dependencies:
    postgres: true
    redis: true
    eventStream: false
```

Crossplane then composes the Kubernetes resources for the service. Capability blueprints define the production-grade implementations that will later be backed by cloud providers, managed services, or in-cluster operators.

## Repository locations

- `blueprints/catalog/software-pieces.yaml` is the company-facing catalog.
- `blueprints/reference-architectures/standard-saas/blueprint.yaml` defines the default stack.
- `blueprints/workloads/*/blueprint.yaml` define workload golden paths.
- `blueprints/capabilities/*/blueprint.yaml` define optional platform capabilities.
- `packages/software-factory-control-plane/apis/serviceblueprint-xrd.yaml` defines the service API.
- `packages/software-factory-control-plane/examples/checkout-api.yaml` shows how a tenant consumes a service blueprint.
