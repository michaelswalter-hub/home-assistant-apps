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


async def application(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        scope = _rewrite_null_origin(scope)
    await paperless_application(scope, receive, send)
