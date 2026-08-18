# Tenant onboarding

## Add a tenant in the local shared cluster

1. Create `gitops/clusters/local/namespaces/<tenant>-<env>.yaml`.
2. Create `gitops/tenants/<tenant>/environments/<env>/factory.yaml`.
3. Create `gitops/tenants/<tenant>/environments/<env>/values.yaml`.
4. Add an Argo CD application under `gitops/clusters/local/<tenant>-<env>-factory.yaml`.

## Add a tenant cluster later

1. Provision the customer Kubernetes cluster.
2. Install Argo CD in that cluster.
3. Point Argo CD at `gitops/clusters/<customer-cluster>/`.
4. Keep tenant application and software factory changes in this repository.
