# Cloud Native Software Factory

This repository is a GitOps-first, Kubernetes-native scaffold for deploying a multitenant software factory.

The target model is:

- one central GitOps repository,
- one Kubernetes cluster per customer in production,
- one isolated namespace per tenant for the first local iteration,
- one tenant-owned software factory deployment per customer,
- application delivery driven by declarative resources in Git.

## Repository layout

```text
packages/software-factory-control-plane/ Crossplane v2 control plane package with XRD and Composition
charts/software-factory/     Legacy Helm preview chart for a tenant software factory instance
gitops/bootstrap/            Argo CD bootstrap entrypoint
gitops/clusters/             Cluster-specific GitOps roots
gitops/tenants/              Tenant and environment declarations
gitops/apps/                 Example application manifests
gitops/platform/             Shared platform GitOps components
docs/                        Architecture and operating guides
examples/                    Copyable tenant examples
scripts/                     Local render and validation helpers
```

## Local first deployment

The local setup deploys all customers into the same Kubernetes cluster, isolated by namespaces. Later, every customer cluster can point at its own `gitops/clusters/<cluster-name>` root.

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f gitops/bootstrap/root-application.yaml
```

For a Helm-only preview of one tenant factory:

```bash
helm template customer-a charts/software-factory \
  --namespace sf-customer-a-dev \
  --values gitops/tenants/customer-a/environments/dev/values.yaml
```

## Adding a new customer

1. Copy `examples/tenants/customer-b` to `gitops/tenants/<tenant>/environments/<env>`.
2. Add a namespace under `gitops/clusters/<cluster>/namespaces/`.
3. Add an Argo CD `Application` under `gitops/clusters/<cluster>/` pointing to the tenant environment.
4. Commit and let GitOps reconcile.


## Enterprise blueprint catalog

Companies consume this repository through platform blueprints instead of copying raw Kubernetes manifests. The default stack is documented in `docs/enterprise-stack-blueprints.md` and declared in `blueprints/catalog/software-pieces.yaml`.

The first service-level API is `ServiceBlueprint`, a namespaced Crossplane composite resource that turns a workload blueprint selection plus image, port, owner, and dependencies into Kubernetes runtime resources. See `packages/software-factory-control-plane/examples/checkout-api.yaml`.

## Example custom resources

The Crossplane package installs a namespaced composite API:

- `SoftwareFactoryEnvironment` describes one customer environment and composes the tenant-local factory resources.

See `packages/software-factory-control-plane/examples/customer-a-dev.yaml` and `gitops/tenants/customer-a/environments/dev/factory.yaml` for runnable examples.
