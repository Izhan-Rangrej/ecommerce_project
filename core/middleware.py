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
"""


class SecurityHeadersMiddleware:
    """Add a Content-Security-Policy header to every response."""

    CSP = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = self.CSP
        return response
