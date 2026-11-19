"""ASGI-Hülle für Paperless-ngx hinter Home-Assistant-Ingress.

Home Assistant setzt auf jede Antwort ``Referrer-Policy: no-referrer``.
Browser schicken dadurch bei POST-Anfragen ``Origin: null``, und Djangos
CSRF-Prüfung lehnt die Anmeldung ab. Für Anfragen, die über Ingress kommen
(erkennbar am Header ``X-Ingress-Path``), wird ``Origin: null`` durch die
tatsächliche Herkunft ersetzt, die Home Assistant in ``X-Forwarded-Proto``
und ``X-Forwarded-Host`` mitschickt. Die CSRF-Token-Prüfung bleibt aktiv.
"""

from paperless.asgi import application as paperless_application


def _rewrite_null_origin(scope):
    headers = scope.get("headers") or []
    lookup = {}
    for name, value in headers:
        lookup.setdefault(name.lower(), value)

    if lookup.get(b"origin") != b"null" or b"x-ingress-path" not in lookup:
        return scope

    proto = lookup.get(b"x-forwarded-proto", b"http").split(b",")[0].strip()
    host = lookup.get(b"x-forwarded-host") or lookup.get(b"host")
    if not host or proto not in (b"http", b"https"):
        return scope
    host = host.split(b",")[0].strip()

    new_headers = [
        (name, proto + b"://" + host if name.lower() == b"origin" else value)
        for name, value in headers
    ]
    return {**scope, "headers": new_headers}


def _restore_ingress_prefix(scope):
    """Home Assistant entfernt den Ingress-Pfad, Django erwartet ihn in ``path``.

    Ohne Präfix entstehen Weiterleitungen wie ``?next=/``, die nach dem Login
    auf die Home-Assistant-Startseite statt auf Paperless führen.
    """
    prefix = None
    for name, value in scope.get("headers") or []:
        if name.lower() == b"x-ingress-path":
            prefix = value.decode("latin-1").rstrip("/")
            break
    if not prefix or not prefix.startswith("/api/hassio_ingress/"):
        return scope

    path = scope.get("path") or "/"
    if path == prefix or path.startswith(prefix + "/"):
        return scope

    new_scope = {**scope, "path": prefix + path, "root_path": prefix}
    raw = scope.get("raw_path")
    if raw is not None:
        new_scope["raw_path"] = prefix.encode("latin-1") + raw
    return new_scope


def _needs_content_length(scope) -> bool:
    """Ingress streamt Uploads ohne Content-Length; Django erkennt dann keine Dateien."""
    if scope.get("type") != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
        return False
    names = {name.lower() for name, _ in scope.get("headers") or []}
    return b"x-ingress-path" in names and b"content-length" not in names


async def _buffer_body(scope, receive):
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None, None
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    body = b"".join(chunks)
    headers = [
        (n, v) for n, v in scope.get("headers") or [] if n.lower() != b"transfer-encoding"
    ]
    headers.append((b"content-length", str(len(body)).encode()))
    sent = False

    async def replay():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return {**scope, "headers": headers}, replay


import os

# Ingress-Anfragen kommen immer vom Supervisor (feste Adresse im internen HA-Netz).
SUPERVISOR_IP = "172.30.32.2"
REMOTE_USER_HEADERS = (b"x-remote-user-id", b"x-remote-user-name", b"x-remote-user-display-name")
SSO_ENABLED = os.environ.get("HA_INGRESS_SSO", "false") == "true"
SSO_USER_MAP = {}
for _pair in os.environ.get("HA_SSO_USER_MAP", "").split(","):
    _ha, _, _pl = _pair.partition("=")
    if _ha.strip() and _pl.strip():
        SSO_USER_MAP[_ha.strip().lower()] = _pl.strip()
_sso_logged = set()


def _secure_remote_user(scope):
    """Anmeldedaten von Home Assistant nur über echten Ingress zulassen.

    Jede andere Anfrage (Port 8010, Home-Assistant-Integration, ...) verliert
    die X-Remote-User-*-Header, damit niemand eine Anmeldung fälschen kann.
    """
    headers = scope.get("headers") or []
    client = str((scope.get("client") or ("", 0))[0] or "")
    if client.lower().startswith("::ffff:"):  # IPv4 als IPv6-Adresse
        client = client[7:]
    names = {n.lower() for n, _ in headers}
    trusted = SSO_ENABLED and client == SUPERVISOR_IP and b"x-ingress-path" in names
    if not trusted:
        if SSO_ENABLED and b"x-ingress-path" in names and ("untrusted", client) not in _sso_logged:
            _sso_logged.add(("untrusted", client))
            print(f"[ha-sso] Ingress-Anfrage von {client} ist nicht vom Supervisor – Anmeldung wird nicht übernommen", flush=True)
        if any(h in names for h in REMOTE_USER_HEADERS):
            headers = [(n, v) for n, v in headers if n.lower() not in REMOTE_USER_HEADERS]
            return {**scope, "headers": headers}
        return scope

    new_headers = []
    for n, v in headers:
        if n.lower() == b"x-remote-user-name":
            ha_name = v.decode("utf-8", "replace").strip()
            pl_name = SSO_USER_MAP.get(ha_name.lower(), ha_name)
            if ha_name not in _sso_logged:
                _sso_logged.add(ha_name)
                print(f"[ha-sso] Home-Assistant-Benutzer '{ha_name}' -> Paperless-Benutzer '{pl_name}'", flush=True)
            v = pl_name.encode("utf-8")
        new_headers.append((n, v))
    return {**scope, "headers": new_headers}


async def application(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        scope = _secure_remote_user(scope)
        scope = _rewrite_null_origin(scope)
        scope = _restore_ingress_prefix(scope)
        if _needs_content_length(scope):
            scope, receive = await _buffer_body(scope, receive)
            if scope is None:
                return
    await paperless_application(scope, receive, send)
