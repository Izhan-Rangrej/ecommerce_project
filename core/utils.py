"""
core — small shared helpers used by several apps.
"""


def is_ajax(request):
    """
    True when the request was made by our JavaScript (fetch() with the
    X-Fetch: 1 header — see static/js/main.js).

    Views return a small JSON response for AJAX requests and a normal
    redirect + message for classic form posts, so the site keeps working
    even when JavaScript is disabled.
    """
    return request.headers.get('X-Fetch') == '1'


def safe_next(url):
    """
    Validate a "redirect after this action" value coming from the browser.

    Only RELATIVE urls are allowed (must start with exactly one slash).
    This blocks open-redirect attacks such as next=https://evil.com.
    Returns None when the value is missing or unsafe.
    """
    if url and url.startswith('/') and not url.startswith('//'):
        return url
    return None
