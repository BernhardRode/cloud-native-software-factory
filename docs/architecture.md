# Architecture

## Goals

The software factory is built around GitOps and Kubernetes APIs. All customer intent is represented as declarative files in this repository.

## Deployment model

### Phase 1: one shared cluster

Each customer is deployed into a dedicated namespace in a shared Kubernetes cluster. This is useful for development and demos.

### Phase 2: one cluster per customer

Each customer cluster runs its own GitOps controller and reconciles only the subtree assigned to that customer cluster. The central repository remains the source of truth.

## Main building blocks

1. **Central GitOps repository**: this repository.
2. **Cluster root**: `gitops/clusters/<cluster-name>/` defines what a cluster reconciles.
3. **Tenant environment**: `gitops/tenants/<tenant>/environments/<env>/` contains the desired factory instance.
4. **Crossplane control plane package**: `packages/software-factory-control-plane` defines the tenant platform API and its Composition.
5. **Software factory chart**: `charts/software-factory` remains available as a Helm-only preview path.
6. **Custom resources**: namespaced Crossplane composite resources make onboarding declarative.
7. **Tenant identity provider**: Pocket ID runs inside the tenant namespace and issues the identities and group claims the environment authorizes against, see `identity-pocket-id.md`.

## Tenant isolation

Every tenant gets:

- a namespace,
- a service account,
- scoped RBAC,
- tenant labels on every resource,
- isolated factory configuration,
- environment-specific values,
- a tenant-local OIDC provider, so identities and passkeys stay in the namespace.

## GitOps flow

1. A platform engineer adds or edits tenant resources in Git.
2. Argo CD reconciles the matching cluster root.
3. Crossplane reconciles the `SoftwareFactoryEnvironment` composite resource.
4. The tenant software factory Deployment, ServiceAccount, ConfigMap, and Service are composed into the tenant namespace.
5. Tenant applications are reconciled from `gitops/apps` overlays.
6. Status is observed through Kubernetes resources, Crossplane, and Argo CD.
