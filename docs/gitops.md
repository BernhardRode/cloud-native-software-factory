# GitOps model

This repository uses an app-of-apps layout.

- `gitops/bootstrap/root-application.yaml` is applied once to a cluster.
- The root application reconciles a cluster directory.
- Cluster directories reference tenant environments and application overlays.

For production, each customer cluster should use a dedicated cluster directory and only reconcile resources for that customer.
