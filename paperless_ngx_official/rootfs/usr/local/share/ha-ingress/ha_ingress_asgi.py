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


async def application(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        scope = _rewrite_null_origin(scope)
        scope = _restore_ingress_prefix(scope)
    await paperless_application(scope, receive, send)
