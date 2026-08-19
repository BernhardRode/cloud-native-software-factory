#!/usr/bin/env python3
"""Group Explorer: a minimal OIDC relying party that shows the groups of the logged in user.

It exists to prove that the tenant-local Pocket ID instance issues the identity and the
group memberships that downstream policy decisions rely on. Only the Python standard
library is used so the app runs from a ConfigMap without a build step.

Configuration:
  OIDC_DISCOVERY_URL  cluster-internal discovery document of the identity provider
  OIDC_ISSUER         expected `iss` value of the ID token
  OIDC_CLIENT_ID      client id registered in Pocket ID
  OIDC_CLIENT_SECRET  client secret registered in Pocket ID
  OIDC_REDIRECT_URI   browser-facing callback URL of this app
  APP_BASE_URL        browser-facing base URL of this app
  OIDC_SCOPES         scopes to request, must contain `groups`
  GROUPS_CLAIM        claim carrying the group names (default `groups`)
  PORT                port to listen on (default 8080)
"""

import base64
import hashlib
import html
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DISCOVERY_URL = os.environ["OIDC_DISCOVERY_URL"]
ISSUER = os.environ["OIDC_ISSUER"].rstrip("/")
CLIENT_ID = os.environ["OIDC_CLIENT_ID"]
CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
REDIRECT_URI = os.environ["OIDC_REDIRECT_URI"]
APP_BASE_URL = os.environ.get("APP_BASE_URL", REDIRECT_URI.rsplit("/", 1)[0]).rstrip("/")
SCOPES = os.environ.get("OIDC_SCOPES", "openid profile email groups")
GROUPS_CLAIM = os.environ.get("GROUPS_CLAIM", "groups")
PORT = int(os.environ.get("PORT", "8080"))
TENANT = os.environ.get("TENANT_NAME", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT_NAME", "")

SESSION_COOKIE = "group_explorer_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_TTL_SECONDS = 10 * 60

_lock = threading.Lock()
_sessions = {}
_logins = {}
_metadata = {"document": None, "fetched_at": 0.0}


def discover():
    """Return the provider metadata, refreshed at most every five minutes."""
    with _lock:
        document = _metadata["document"]
        if document and time.time() - _metadata["fetched_at"] < 300:
            return document

    request = urllib.request.Request(DISCOVERY_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        document = json.loads(response.read())

    with _lock:
        _metadata["document"] = document
        _metadata["fetched_at"] = time.time()
    return document


def prune():
    now = time.time()
    with _lock:
        for key, session in list(_sessions.items()):
            if session["expires_at"] < now:
                del _sessions[key]
        for key, login in list(_logins.items()):
            if login["expires_at"] < now:
                del _logins[key]


def decode_jwt_claims(token):
    """Decode the claims of a JWT without verifying its signature.

    The token is read straight from the token endpoint over a direct back-channel call,
    so its origin is already established (OpenID Connect Core 3.1.3.7 permits skipping
    signature validation in that case). The claims below are still checked explicitly.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def get_json(url, access_token):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    request.add_header("Authorization", "Bearer " + access_token)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def page(title, body):
    tenant_line = ""
    if TENANT:
        tenant_line = "<p class=\"context\">Tenant <strong>{}</strong> &middot; environment <strong>{}</strong></p>".format(
            html.escape(TENANT), html.escape(ENVIRONMENT or "-")
        )
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 2.5rem 1.5rem;
         background: Canvas; color: CanvasText; line-height: 1.55; }}
  main {{ max-width: 46rem; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
  .context {{ color: GrayText; margin-top: 0; }}
  .card {{ border: 1px solid color-mix(in srgb, CanvasText 20%, transparent); border-radius: 12px;
           padding: 1.25rem 1.5rem; margin: 1.25rem 0; }}
  .groups {{ list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .groups li {{ border: 1px solid color-mix(in srgb, CanvasText 30%, transparent); border-radius: 999px;
                padding: 0.2rem 0.85rem; font-family: ui-monospace, monospace; font-size: 0.9rem; }}
  dl {{ display: grid; grid-template-columns: minmax(8rem, auto) 1fr; gap: 0.4rem 1rem; margin: 0; }}
  dt {{ color: GrayText; }}
  dd {{ margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }}
  a.button {{ display: inline-block; padding: 0.6rem 1.2rem; border-radius: 8px; text-decoration: none;
              border: 1px solid currentColor; }}
  pre {{ overflow-x: auto; padding: 0.75rem; border-radius: 8px;
         background: color-mix(in srgb, CanvasText 8%, transparent); }}
  .empty {{ color: GrayText; font-style: italic; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
{tenant_line}
{body}
</main>
</body>
</html>
""".format(title=html.escape(title), tenant_line=tenant_line, body=body)


def render_login():
    return page(
        "Group Explorer",
        """
<div class="card">
  <p>This test app signs you in against the tenant-local Pocket ID instance and shows the
     groups that Pocket ID reports for your identity.</p>
  <p><a class="button" href="/login">Sign in with Pocket ID</a></p>
</div>
""",
    )


def render_session(session):
    claims = session["claims"]
    userinfo = session["userinfo"]
    groups = userinfo.get(GROUPS_CLAIM, claims.get(GROUPS_CLAIM, []))
    if isinstance(groups, str):
        groups = [groups]

    if groups:
        group_items = "".join("<li>{}</li>".format(html.escape(str(group))) for group in groups)
        group_block = '<ul class="groups">{}</ul>'.format(group_items)
    else:
        group_block = '<p class="empty">Pocket ID reports no group membership for this user.</p>'

    def row(label, value):
        return "<dt>{}</dt><dd>{}</dd>".format(html.escape(label), html.escape(str(value or "-")))

    identity = "".join(
        [
            row("Subject", claims.get("sub")),
            row("Username", claims.get("preferred_username")),
            row("Name", claims.get("name")),
            row("Email", claims.get("email")),
            row("Issuer", claims.get("iss")),
        ]
    )

    body = """
<div class="card">
  <h2>Groups</h2>
  {group_block}
</div>
<div class="card">
  <h2>Identity</h2>
  <dl>{identity}</dl>
</div>
<div class="card">
  <details>
    <summary>ID token claims</summary>
    <pre>{claims}</pre>
  </details>
  <details>
    <summary>Userinfo response</summary>
    <pre>{userinfo}</pre>
  </details>
</div>
<p><a class="button" href="/logout">Sign out</a></p>
""".format(
        group_block=group_block,
        identity=identity,
        claims=html.escape(json.dumps(claims, indent=2, sort_keys=True)),
        userinfo=html.escape(json.dumps(userinfo, indent=2, sort_keys=True)),
    )
    return page("Signed in as {}".format(claims.get("preferred_username") or claims.get("sub", "")), body)


def render_error(message):
    return page(
        "Sign-in failed",
        '<div class="card"><p>{}</p><p><a class="button" href="/">Back</a></p></div>'.format(html.escape(message)),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "group-explorer"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def respond(self, status, body, content_type="text/html; charset=utf-8", headers=()):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location, headers=()):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()

    def current_session(self):
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None, None
        cookie = SimpleCookie(cookie_header)
        if SESSION_COOKIE not in cookie:
            return None, None
        session_id = cookie[SESSION_COOKIE].value
        with _lock:
            session = _sessions.get(session_id)
        if session and session["expires_at"] < time.time():
            with _lock:
                _sessions.pop(session_id, None)
            return None, None
        return session_id, session

    def do_GET(self):
        prune()
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if path == "/healthz":
            self.respond(200, "ok", "text/plain; charset=utf-8")
        elif path == "/":
            _, session = self.current_session()
            self.respond(200, render_session(session) if session else render_login())
        elif path == "/login":
            self.handle_login()
        elif path == "/callback":
            self.handle_callback(query)
        elif path == "/logout":
            self.handle_logout()
        else:
            self.respond(404, page("Not found", '<div class="card"><p>Unknown path.</p></div>'))

    def handle_login(self):
        try:
            metadata = discover()
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            self.respond(503, render_error("The identity provider is not reachable: {}".format(error)))
            return

        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

        with _lock:
            _logins[state] = {
                "verifier": verifier,
                "nonce": nonce,
                "expires_at": time.time() + LOGIN_TTL_SECONDS,
            }

        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        self.redirect(metadata["authorization_endpoint"] + "?" + urllib.parse.urlencode(params))

    def handle_callback(self, query):
        if "error" in query:
            self.respond(400, render_error("The identity provider returned an error: {}".format(query["error"][0])))
            return

        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        with _lock:
            login = _logins.pop(state, None)
        if not login or not code:
            self.respond(400, render_error("The sign-in request expired or was tampered with. Please try again."))
            return

        try:
            metadata = discover()
            tokens = post_form(
                metadata["token_endpoint"],
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code_verifier": login["verifier"],
                },
            )
            claims = decode_jwt_claims(tokens["id_token"])
            self.validate_claims(claims, login["nonce"])
            userinfo = get_json(metadata["userinfo_endpoint"], tokens["access_token"])
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
            self.respond(502, render_error("Could not complete the token exchange: {}".format(error)))
            return
        except AssertionError as error:
            self.respond(400, render_error(str(error)))
            return

        session_id = secrets.token_urlsafe(32)
        with _lock:
            _sessions[session_id] = {
                "claims": claims,
                "userinfo": userinfo,
                "id_token": tokens["id_token"],
                "expires_at": time.time() + SESSION_TTL_SECONDS,
            }

        cookie = "{}={}; Path=/; HttpOnly; SameSite=Lax".format(SESSION_COOKIE, session_id)
        if APP_BASE_URL.startswith("https://"):
            cookie += "; Secure"
        self.redirect("/", headers=[("Set-Cookie", cookie)])

    def validate_claims(self, claims, nonce):
        if claims.get("iss", "").rstrip("/") != ISSUER:
            raise AssertionError("The ID token was issued by an unexpected issuer.")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if CLIENT_ID not in audiences:
            raise AssertionError("The ID token was not issued for this application.")
        if claims.get("nonce") != nonce:
            raise AssertionError("The ID token nonce does not match the sign-in request.")
        if float(claims.get("exp", 0)) < time.time():
            raise AssertionError("The ID token is already expired.")

    def handle_logout(self):
        session_id, session = self.current_session()
        if session_id:
            with _lock:
                _sessions.pop(session_id, None)

        expired = "{}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0".format(SESSION_COOKIE)
        location = "/"
        if session:
            try:
                metadata = discover()
                end_session = metadata.get("end_session_endpoint")
                if end_session:
                    location = end_session + "?" + urllib.parse.urlencode(
                        {
                            "id_token_hint": session["id_token"],
                            "client_id": CLIENT_ID,
                            "post_logout_redirect_uri": APP_BASE_URL + "/",
                        }
                    )
            except (urllib.error.URLError, TimeoutError, ValueError):
                pass
        self.redirect(location, headers=[("Set-Cookie", expired)])


def main():
    print("Group Explorer listening on port {} for client '{}'".format(PORT, CLIENT_ID), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
