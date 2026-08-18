#!/usr/bin/env bash
set -euo pipefail
helm template customer-a charts/software-factory \
  --namespace sf-customer-a-dev \
  --values gitops/tenants/customer-a/environments/dev/values.yaml
