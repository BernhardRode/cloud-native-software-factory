#!/usr/bin/env python3
"""Seed a Pocket ID instance with the groups, users, and OIDC clients of a tenant environment.

The script is idempotent: it reconciles the desired state described in bootstrap.json
against the running instance, so it can run on every install and upgrade.

Configuration:
  POCKET_ID_URL      cluster-internal base URL of Pocket ID
  POCKET_ID_APP_URL  browser-facing base URL, used to render login links
  POCKET_ID_API_KEY  static API key with admin permissions
  BOOTSTRAP_CONFIG   path to the desired state document (default /config/bootstrap.json)
  OIDC_CLIENT_SECRET client secret to register for the configured OIDC client
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ["POCKET_ID_URL"].rstrip("/")
APP_URL = os.environ.get("POCKET_ID_APP_URL", BASE_URL).rstrip("/")
API_KEY = os.environ["POCKET_ID_API_KEY"]
CONFIG_PATH = os.environ.get("BOOTSTRAP_CONFIG", "/config/bootstrap.json")
CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")

READY_TIMEOUT_SECONDS = int(os.environ.get("READY_TIMEOUT_SECONDS", "300"))


def log(message):
    print(message, flush=True)


def api(method, path, body=None):
    """Call the Pocket ID API and return (status, parsed_body)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    request.add_header("X-API-Key", API_KEY)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return error.code, {"raw": payload.decode("utf-8", "replace")}


def expect(status, body, allowed, action):
    if status not in allowed:
        raise SystemExit("{} failed with HTTP {}: {}".format(action, status, json.dumps(body)))
    return body


def wait_until_ready():
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(BASE_URL + "/healthz", timeout=10) as response:
                if 200 <= response.status < 300:
                    log("Pocket ID is ready at {}".format(BASE_URL))
                    return
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        else:
            last_error = "unexpected status"
        if time.monotonic() >= deadline:
            raise SystemExit("Pocket ID did not become ready in {}s: {}".format(READY_TIMEOUT_SECONDS, last_error))
        if attempt % 5 == 0:
            log("Waiting for Pocket ID to become ready ...")
        time.sleep(3)


def find_by(path, search, field, value):
    """Return the first entry of a paginated list endpoint whose `field` equals `value`."""
    query = urllib.parse.urlencode({"search": search, "pagination[limit]": 100})
    status, body = api("GET", "{}?{}".format(path, query))
    expect(status, body, (200,), "listing {}".format(path))
    for entry in (body or {}).get("data", []):
        if entry.get(field) == value:
            return entry
    return None


def ensure_group(group):
    name = group["name"]
    existing = find_by("/api/user-groups", name, "name", name)
    if existing:
        log("Group '{}' already exists".format(name))
        return existing["id"]

    status, body = api(
        "POST",
        "/api/user-groups",
        {"name": name, "friendlyName": group.get("friendlyName", name)},
    )
    if status == 201:
        log("Created group '{}'".format(name))
        return body["id"]

    # A concurrent bootstrap may have won the race, so re-read before giving up.
    existing = find_by("/api/user-groups", name, "name", name)
    if existing:
        return existing["id"]
    raise SystemExit("creating group '{}' failed with HTTP {}: {}".format(name, status, json.dumps(body)))


def ensure_user(user, group_ids):
    username = user["username"]
    desired_groups = [group_ids[name] for name in user.get("groups", []) if name in group_ids]
    existing = find_by("/api/users", username, "username", username)

    if existing:
        status, body = api(
            "PUT",
            "/api/users/{}/user-groups".format(existing["id"]),
            {"userGroupIds": desired_groups},
        )
        expect(status, body, (200, 201), "updating groups of user '{}'".format(username))
        log("User '{}' already exists, group membership reconciled".format(username))
        return existing["id"]

    payload = {
        "username": username,
        "firstName": user.get("firstName", ""),
        "lastName": user.get("lastName", ""),
        "isAdmin": bool(user.get("isAdmin", False)),
        "userGroupIds": desired_groups,
    }
    if user.get("email"):
        payload["email"] = user["email"]
        payload["emailVerified"] = True

    status, body = api("POST", "/api/users", payload)
    if status == 201:
        log("Created user '{}'".format(username))
        return body["id"]

    existing = find_by("/api/users", username, "username", username)
    if existing:
        return existing["id"]
    raise SystemExit("creating user '{}' failed with HTTP {}: {}".format(username, status, json.dumps(body)))


def ensure_client(client, group_ids):
    client_id = client["id"]
    payload = {
        "name": client.get("name", client_id),
        "description": client.get("description", ""),
        "callbackURLs": client.get("callbackURLs", []),
        "logoutCallbackURLs": client.get("logoutCallbackURLs", []),
        "isPublic": False,
        "pkceEnabled": True,
        "requiresReauthentication": False,
        "skipConsent": bool(client.get("skipConsent", True)),
        "isGroupRestricted": bool(client.get("allowedGroups")),
    }
    if client.get("launchURL"):
        payload["launchURL"] = client["launchURL"]

    status, _ = api("GET", "/api/oidc/clients/{}".format(client_id))
    if status == 404:
        payload["id"] = client_id
        status, body = api("POST", "/api/oidc/clients", payload)
        expect(status, body, (201,), "creating OIDC client '{}'".format(client_id))
        log("Created OIDC client '{}'".format(client_id))
    else:
        status, body = api("PUT", "/api/oidc/clients/{}".format(client_id), payload)
        expect(status, body, (200,), "updating OIDC client '{}'".format(client_id))
        log("OIDC client '{}' already exists, configuration reconciled".format(client_id))

    if client.get("allowedGroups"):
        allowed = [group_ids[name] for name in client["allowedGroups"] if name in group_ids]
        status, body = api(
            "PUT",
            "/api/oidc/clients/{}/allowed-user-groups".format(client_id),
            {"userGroupIds": allowed},
        )
        expect(status, body, (200, 201), "restricting OIDC client '{}' to groups".format(client_id))
        log("OIDC client '{}' restricted to groups {}".format(client_id, ", ".join(client["allowedGroups"])))

    ensure_client_secret(client_id)


def ensure_client_secret(client_id):
    if not CLIENT_SECRET:
        log("No client secret provided for '{}', skipping secret registration".format(client_id))
        return

    status, body = api("GET", "/api/oidc/clients/{}/secrets".format(client_id))
    expect(status, body, (200,), "listing secrets of OIDC client '{}'".format(client_id))
    if any(secret.get("isActive") for secret in body or []):
        log("OIDC client '{}' already has an active secret".format(client_id))
        return

    status, body = api(
        "POST",
        "/api/oidc/clients/{}/secrets".format(client_id),
        {"secret": CLIENT_SECRET},
    )
    expect(status, body, (201,), "registering secret for OIDC client '{}'".format(client_id))
    log("Registered the configured client secret for '{}'".format(client_id))


def print_login_link(username, user_id, ttl):
    status, body = api("POST", "/api/users/{}/one-time-access-token".format(user_id), {"ttl": ttl})
    if status != 201:
        log("Could not create a login link for '{}': HTTP {}".format(username, status))
        return
    log("Login link for '{}' (valid for {}): {}/lc/{}".format(username, ttl, APP_URL, body["token"]))


def main():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        config = json.load(handle)

    wait_until_ready()

    group_ids = {}
    for group in config.get("groups", []):
        group_ids[group["name"]] = ensure_group(group)

    user_ids = {}
    for user in config.get("users", []):
        user_ids[user["username"]] = ensure_user(user, group_ids)

    for client in config.get("clients", []):
        ensure_client(client, group_ids)

    login_links = config.get("loginLinks", {})
    if login_links.get("enabled") and user_ids:
        log("")
        log("Seeded users still need a passkey. Open one of these one-time links to register one:")
        for username, user_id in user_ids.items():
            print_login_link(username, user_id, login_links.get("ttl", "1h"))

    log("")
    log("Pocket ID bootstrap completed")


if __name__ == "__main__":
    sys.exit(main())
