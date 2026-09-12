"""
core/middleware.py — PHASE 18: extra security headers.

Django has settings for HSTS, SSL redirect, secure cookies and
X-Frame-Options, but it has no setting for a
Content-Security-Policy — so this one small middleware adds it.

The CSP below lists exactly the origins this site loads from:
    * 'self'                        our own files (CSS, JS, images)
    * https://cdn.jsdelivr.net     Bootstrap 5 + Bootstrap Icons
    * https://fonts.googleapis.com / fonts.gstatic.com   Google Fonts
Anything else (trackers, injected scripts, …) is refused by the
browser. There are NO inline <script> blocks in the templates, so
'script-src' never needs 'unsafe-inline'.

PHASE 21 — CSP_EXTRA_IMG_SRC
----------------------------
`img-src` is deliberately locked to 'self' + data: because product photos
are served from our own /media/. The moment those move to object storage
or a CDN (Cloudinary, S3, Cloudflare R2 — the documented scale-up path),
'self' no longer covers them and EVERY product image silently disappears:
the <img> tag is still in the HTML, the file is still on the server, and
only the browser console mentions the CSP refusal. That is a confusing
hour to lose, so the extra origins are configurable instead of hardcoded:

    CSP_EXTRA_IMG_SRC=https://res.cloudinary.com,https://cdn.example.com

Empty (the default) produces exactly the same header as before.
"""

from django.conf import settings


def _build_csp():
    """Assemble the policy once, at import time, from settings."""
    # Extra image origins, if the deployment moved media off this server.
    extra_img = [
        origin.strip()
        for origin in getattr(settings, 'CSP_EXTRA_IMG_SRC', '').split(',')
        if origin.strip()
    ]
    img_src = "img-src 'self' data:"
    if extra_img:
        img_src += ' ' + ' '.join(extra_img)

    return (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
        f"{img_src}; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )


class SecurityHeadersMiddleware:
    """Add a Content-Security-Policy header to every response."""

    CSP = _build_csp()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = self.CSP
        return response
