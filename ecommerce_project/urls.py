"""
ecommerce_project URL configuration.

This is the project's MAIN router: it decides which app handles which
URL prefix. Each app keeps its own urls.py, which is "included" here —
modular and readable.

URL map (growing phase by phase):
    /admin/                          Django admin
    /about/ /contact/ /privacy/ /terms/  site pages (core)
    /newsletter/subscribe/           footer newsletter (core)
    /search/?q=...                   product search (products)
    /product/<slug>/                 product detail (products)
    /cart/add/<id>/ ...              cart actions (cart, POST-only)
    /wishlist/toggle/<id>/           wishlist (customers, POST-only)
    /checkout/ ...                   5-step checkout + order placement (orders)
    /accounts/login/ ...             Django's stock auth pages (restyled in PHASE 8)
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from customers.views import ThrottledLoginView, ThrottledPasswordResetView

# ---------------------------------------------------------------------------
# Brand the admin panel (shown at /admin/)
# ---------------------------------------------------------------------------
admin.site.site_header = 'ShopSphere — Store Administration'   # top blue bar
admin.site.site_title = 'ShopSphere Admin'                     # browser tab
admin.site.index_title = 'Store Dashboard'                     # main heading
admin.site.empty_changelist_text = (
    'Nothing here yet — use the "Add" button in the top-right corner.'
)

# ---------------------------------------------------------------------------
# Custom error pages (PHASE 5) — styled 403/404/500.
# NOTE: in Django 6 these MUST live in urls.py (the old settings
# `handlers403/404/500` were removed). Django looks for `handler404`
# etc. as attributes of this module.
# ---------------------------------------------------------------------------
handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),

    # Site pages + newsletter
    path('', include('core.urls')),

    # Search + product detail
    path('', include('products.urls')),

    # Cart actions (all POST)
    path('cart/', include('cart.urls')),

    # Customer area: wishlist toggle (PHASE 5), registration + account +
    # addresses (PHASE 8). Included ONCE at the root — the app's own urls
    # carry the /wishlist/… and /account/… prefixes.
    # (The /wishlist/ *page* arrives in PHASE 10.)
    path('', include('customers.urls')),

    # Orders: the 5-step checkout at /checkout/… (PHASE 11).
    # PHASE 12 adds /orders/ (history) + /orders/<id>/ to the same urlconf.
    path('', include('orders.urls')),

    # PHASE 18: rate-limited auth entry points. These are listed BEFORE
    # the stock auth include so they win URL matching; the include below
    # still provides logout / password change / reset-confirm, etc.
    path('accounts/login/', ThrottledLoginView.as_view(), name='login'),
    # NOTE: the stock auth urlconf uses "password_reset/" (underscore) —
    # matching that exact path is what makes our throttled view shadow
    # the stock one.
    path('accounts/password_reset/',
         ThrottledPasswordResetView.as_view(), name='password_reset'),

    # Django's built-in auth pages: login, logout, password change/reset.
    # They work right away with Django's plain templates; PHASE 8 replaces
    # them with our styled pages (login, register, profile).
    path('accounts/', include('django.contrib.auth.urls')),
]

# ---------------------------------------------------------------------------
# DEVELOPMENT ONLY:
# Serve user-uploaded files (product photos, avatars) at /media/...
#
# Development: required — the dev server has no web server in front.
# Production: we keep Django serving /media/ ON PURPOSE: it is the
# simplest setup that works (gunicorn -> Django -> /media/). It is fine
# for a small store. When the catalogue grows, move media files to a
# CDN/object storage (Cloudinary, S3, Cloudflare R2) and delete this
# block — that is a Phase-21+ concern, not a launch blocker.
# ---------------------------------------------------------------------------
# NOTE (Django 6): the convenient `static(...)` helper from
# django.conf.urls is a NO-OP when DEBUG=False — so for production we
# register the plain `serve` view directly. It has no debug check of
# its own, which is exactly what we want: gunicorn -> Django -> /media/
# works the same way in dev and on the server.
#
# Scale-up path (Phase 21+): move media files to a CDN/object storage
# (Cloudinary, S3, Cloudflare R2) and delete this block.
urlpatterns += [
    re_path(
        r'^media/(?P<path>.*)$',
        serve,
        kwargs={'document_root': settings.MEDIA_ROOT},
    ),
]
