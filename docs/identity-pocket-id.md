# Tenant-local identity with Pocket ID

Every tenant environment runs its own OpenID Connect provider. [Pocket ID](https://pocket-id.org)
is deployed into the tenant namespace, so passkeys, users, groups, and sessions never leave the
customer environment. Applications inside the namespace authenticate against it over
cluster-internal HTTP; the browser talks to it over the URL configured in `identity.pocketId.appUrl`.

The `group-explorer` test app ships with the chart and proves the integration end to end: it signs
a user in against Pocket ID and renders the groups that Pocket ID reports for that identity.

## What the chart deploys

| Resource | Purpose |
| --- | --- |
| `Deployment/pocket-id` + `Service/pocket-id` | The identity provider, listening on port 1411 |
| `PersistentVolumeClaim/pocket-id-data` | SQLite database, keys, and uploads |
| `Secret/pocket-id` | `encryption-key` and `static-api-key` |
| `Job/pocket-id-bootstrap` | Declarative seeding of groups, users, and OIDC clients |
| `Deployment/group-explorer` + `Service/group-explorer` | The test app |
| `Secret/group-explorer-oidc` | `client-secret` of the test app's OIDC client |

Both `Ingress` resources are optional and disabled by default.

## URLs

Pocket ID publishes two sets of endpoints in its discovery document:

- `APP_URL` is the browser-facing issuer. It ends up in the `iss` claim and in the
  `authorization_endpoint`, so it has to match the URL a human actually opens. Passkeys are bound
  to that origin.
- `INTERNAL_APP_URL` is set by the chart to `http://pocket-id.<namespace>.svc.cluster.local:1411`.
  The `token_endpoint`, `userinfo_endpoint`, and `jwks_uri` point there, so workloads in the
  namespace never leave the cluster for the back-channel calls.

## Automatic configuration

The `pocket-id-bootstrap` job runs after every install and upgrade (`post-install`, `post-upgrade`
for Helm, `PostSync` for Argo CD). It authenticates with the static API key and reconciles the
desired state from `identity.bootstrap`:

1. wait until `/healthz` answers,
2. create the configured user groups if they are missing,
3. create the configured users and reconcile their group membership,
4. create or update the OIDC client of the test app, including callback URLs and, optionally,
   the group restriction,
5. register the client secret from `Secret/group-explorer-oidc` if the client has no active secret,
6. print one-time login links so the seeded users can register a passkey.

The job is idempotent: re-running it against an already configured instance only reconciles
what drifted. It never deletes anything, so groups and users removed from `values.yaml` stay in
Pocket ID and have to be removed by an administrator.

Because a user is created through the API, Pocket ID's initial admin setup page is closed
immediately. The seeded admin signs in through a one-time login link instead.

## Local walkthrough

```bash
helm upgrade --install customer-a charts/software-factory \
  --namespace sf-customer-a-dev --create-namespace \
  --values gitops/tenants/customer-a/environments/dev/values.yaml

kubectl port-forward -n sf-customer-a-dev svc/pocket-id 1411:1411 &
kubectl port-forward -n sf-customer-a-dev svc/group-explorer 8080:8080 &

# the one-time login links of the seeded users
kubectl logs -n sf-customer-a-dev job/pocket-id-bootstrap
```

Open a login link, register a passkey, then open <http://localhost:8080> and sign in. The app
shows the group memberships, the identity claims, and the raw ID token and userinfo payloads.

With the default seed, `developer` sees `developers`, `viewer` sees `viewers`, and `admin` sees
both `platform-admins` and `developers`.

## Groups in tokens

Group names reach the application through the `groups` scope. The chart requests
`openid profile email groups`, and Pocket ID answers with the `name` of every group the user
belongs to, in the ID token and in the userinfo response:

```json
{
  "sub": "4ee425ea-fd9b-4aa3-b3b2-ae53a3fa8ce5",
  "preferred_username": "developer",
  "email": "developer@customer-a.example",
  "groups": ["developers"]
}
```

That claim is the hand-off point for downstream authorization: an ingress proxy, a service mesh
policy, or a SASE broker can key its decisions on it without holding identity data itself.

Set `groupExplorer.allowedGroups` to restrict the client itself. Pocket ID then rejects users
outside those groups before an application ever sees a token.

## Secrets

The chart ships placeholder values so a sandbox comes up with a single command. They are dev-only
and the chart refuses values shorter than 16 characters.

For every other environment create the secrets out of band and reference them:

```yaml
identity:
  pocketId:
    existingSecret: pocket-id-credentials   # keys: encryption-key, static-api-key
groupExplorer:
  existingSecret: group-explorer-oidc       # key: client-secret
```

Generate the values with `openssl rand -base64 32`. The encryption key protects the token signing
keys in the database, so rotating it requires the procedure documented by Pocket ID; the static
API key grants admin access to the instance and only needs to be readable by the bootstrap job.

## Adding another OIDC client

The bootstrap script reads its desired state from `bootstrap.json` in the `pocket-id-bootstrap`
ConfigMap. To register more clients, extend the `clients` list in
`charts/software-factory/templates/identity/bootstrap-configmap.yaml` with the same shape the test
app uses:

```json
{
  "id": "checkout-api",
  "name": "Checkout API",
  "callbackURLs": ["https://checkout.customer-a.example.com/oidc/callback"],
  "logoutCallbackURLs": ["https://checkout.customer-a.example.com/"],
  "skipConsent": true,
  "allowedGroups": ["developers"]
}
```

A client secret is only registered when the job is given one through `OIDC_CLIENT_SECRET`.

## The test app

`charts/software-factory/files/group-explorer.py` is a standard-library-only Python relying party
mounted from a ConfigMap, so it needs no image build. It runs the authorization code flow with
PKCE, verifies `iss`, `aud`, `nonce`, and `exp` on the ID token, and reads the groups from the
userinfo endpoint. The ID token signature is not verified separately because the token is fetched
over a direct back-channel call to the trusted token endpoint, which OpenID Connect Core 3.1.3.7
permits for the code flow. It is a verification tool, not a template for production services.
