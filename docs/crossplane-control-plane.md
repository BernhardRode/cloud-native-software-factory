# Crossplane control plane

This repository now uses Crossplane v2 as the API layer for the software factory control plane.

## Why Crossplane here?

Crossplane v2 is a better fit than hand-written CRDs for this repository because tenant software factories are platform APIs, not only raw Kubernetes manifests. Crossplane v2 makes composite resources namespaced by default, supports composing arbitrary Kubernetes resources, and supports namespaced managed resources. That matches the local-first tenant namespace model and the future model where every customer cluster runs its own reconciler.

## API shape

The central platform API is:

```yaml
apiVersion: platform.example.org/v1alpha1
kind: SoftwareFactoryEnvironment
```

A tenant environment describes:

- tenant identity,
- environment name,
- target cluster name,
- GitOps repository and path,
- factory deployment settings.

## Composition

`packages/software-factory-control-plane/compositions/softwarefactoryenvironment-composition.yaml` renders the resources for one tenant-local software factory:

- ConfigMap with GitOps and tenant settings,
- ServiceAccount,
- Deployment,
- Service.

The composition intentionally creates only namespaced resources. Namespace creation remains owned by the cluster GitOps root so the same API works in a shared local cluster and in a dedicated customer cluster.

## GitOps flow

1. Argo CD installs Crossplane from `gitops/platform/crossplane/crossplane-install.yaml`.
2. Argo CD installs the control plane package from `packages/software-factory-control-plane`.
3. A cluster root creates the tenant namespace.
4. A tenant environment submits a `SoftwareFactoryEnvironment` XR.
5. Crossplane composes the tenant-local factory resources.

## Production direction

For production, each customer cluster should:

- install Argo CD,
- install Crossplane,
- reconcile only its `gitops/clusters/<customer-cluster>` directory,
- apply only that customer's `SoftwareFactoryEnvironment` resources.
