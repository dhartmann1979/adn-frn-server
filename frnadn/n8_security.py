"""
N8 security 1.0 – shared by the N8schicht web services (N8 Crosslink, HBlink4-FreeRadioID, adn-frn-server,
N8-HotSpot). Same file in every repository.

* ``FASTAPI_KWARGS``: no /docs, /redoc or /openapi.json (the API description would list every admin route
  with its schema). For development: environment variable ``N8_API_DOCS=1``.
* ``UVICORN_KWARGS``: no "server: uvicorn" header.
* ``headers(response, https)``: security headers for every answer – Content-Security-Policy,
  Strict-Transport-Security (only over HTTPS), Permissions-Policy, X-Content-Type-Options, X-Frame-Options,
  Referrer-Policy, Cross-Origin-Opener-Policy/Resource-Policy.

The pages load everything from their own server (scripts, styles, fonts, Leaflet); only map tiles and
avatars may come from other HTTPS servers as images. Inline scripts are still allowed because the pages use
inline event handlers – the policy stops foreign scripts, plugins, <base> tricks, foreign forms and framing.
"""
import os

DOCS = os.environ.get("N8_API_DOCS", "").strip().lower() in ("1", "true", "yes", "on")

FASTAPI_KWARGS = {} if DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}
UVICORN_KWARGS = {"server_header": False}

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self' ws: wss:",
    "media-src 'self' blob: data:",
    "worker-src 'self' blob:",
    "frame-src 'self'",
    "frame-ancestors 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])
PERMISSIONS = ("camera=(), microphone=(), geolocation=(self), payment=(), usb=(), serial=(), "
               "magnetometer=(), gyroscope=(), accelerometer=()")
HSTS = "max-age=31536000"


def headers(response, https: bool = False, csp: str = CSP) -> None:
    """Add the security headers (keeps headers a route has set itself)."""
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", PERMISSIONS)
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cross-Origin-Resource-Policy", "same-site")
    if csp:
        h.setdefault("Content-Security-Policy", csp)
    if https:
        h.setdefault("Strict-Transport-Security", HSTS)
    try:
        del h["server"]
    except KeyError:
        pass


def is_https(request) -> bool:
    """Request came over HTTPS – directly or through a reverse proxy that says so."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"
