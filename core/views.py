"""
core — site-level views.

    home                          -> the home page (PHASE 6)
    about / contact / privacy / terms   -> simple info pages
    newsletter_subscribe                -> footer newsletter signup
    error_403 / error_404 / error_500   -> styled error pages
"""

from django.contrib import messages
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from .forms import NewsletterForm
from .ratelimit import check_rate_limit   # PHASE 18: rate limiter
from .utils import is_ajax
from customers.models import NewsletterSubscriber
from orders.models import OrderItem
from products.models import Category, Product, Review


# ---------------------------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------------------------
def home(request):
    """
    The home page. Every section is live data from the database:

        categories    -> the "Shop by category" tiles (navbar dropdown too)
        featured      -> products with featured=True
        new_arrivals  -> most recently added products
        best_sellers  -> products with the most units SOLD (real orders)
        reviews       -> the newest customer reviews

    Product queries annotate each product with its average rating +
    review count so the cards show stars without N extra queries.
    """
    def with_ratings(qs):
        return qs.select_related('category', 'brand').annotate(
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews'),
        )

    active = Product.objects.filter(active=True)

    featured = with_ratings(active.filter(featured=True))[:8]

    # Model Meta.ordering is ['-created_at'], so a plain slice = newest first.
    new_arrivals = with_ratings(active)[:4]

    # Best sellers = the product ids with the highest total units sold.
    top_sold = list(
        OrderItem.objects
        .values('product_id')
        .annotate(total_units=Sum('quantity'))
        .order_by('-total_units')[:4]
    )
    best_sellers = list(
        with_ratings(active).filter(pk__in=[row['product_id'] for row in top_sold])
    )
    if not best_sellers:
        # No orders yet: fall back to featured products so the section
        # is never empty on a fresh store.
        best_sellers = list(featured[:4])
    # Keep the ORDER of best_sellers = "most sold first".
    if top_sold:
        order_index = {row['product_id']: i for i, row in enumerate(top_sold)}
        best_sellers.sort(key=lambda p: order_index.get(p.pk, 99))

    latest_reviews = (
        Review.objects
        .select_related('product', 'user')
        .order_by('-created_at')[:4]
    )

    context = {
        'featured': featured,
        'new_arrivals': new_arrivals,
        'best_sellers': best_sellers,
        'reviews': latest_reviews,
        'has_products': active.exists(),
    }
    return render(request, 'home.html', context)


# ---------------------------------------------------------------------------
# Info pages
# ---------------------------------------------------------------------------
def about(request):
    return render(request, 'pages/about.html')


def contact(request):
    return render(request, 'pages/contact.html')


def privacy(request):
    return render(request, 'pages/privacy.html')


def terms(request):
    return render(request, 'pages/terms.html')


# ---------------------------------------------------------------------------
# Newsletter (footer)
# ---------------------------------------------------------------------------
def newsletter_subscribe(request):
    """
    Subscribe an email address. Works as a classic POST (redirect + message)
    and as AJAX (JSON response) — see core.utils.is_ajax.
    """
    if request.method == 'POST':
        # PHASE 18: max 5 signups / IP / 10 minutes (spam guard).
        allowed, wait_min = check_rate_limit(request, 'newsletter', 5, 600)
        form = NewsletterForm(request.POST)
        if not allowed:
            message = (
                f'Too many sign-up attempts. Please wait about '
                f'{wait_min} minute(s) and try again.'
            )
            if is_ajax(request):
                return JsonResponse({'ok': False, 'message': message}, status=429)
            messages.error(request, message)
            return redirect('core:about')
        elif form.is_valid():
            email = form.cleaned_data['email']
            already = NewsletterSubscriber.objects.filter(
                email__iexact=email
            ).exists()
            if not already:
                NewsletterSubscriber.objects.create(email=email)
            message = (
                'You are already subscribed — thanks!'
                if already
                else 'You are on the list! Watch your inbox for deals.'
            )
            if is_ajax(request):
                return JsonResponse({'ok': True, 'message': message})
            messages.success(request, message)
            return redirect('core:about')
        if is_ajax(request):
            return JsonResponse(
                {'ok': False, 'message': 'Please enter a valid email address.'},
                status=400,
            )
        messages.error(request, 'Please enter a valid email address.')
    return redirect('core:about')


def robots_txt(request):
    """
    GET /robots.txt — crawler rules (PHASE 19, finishes the SEO
    checklist): public pages may be indexed, private/money pages may
    not, and the sitemap location is announced.
    """
    base = request.build_absolute_uri('/')
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin/',
        'Disallow: /checkout/',
        'Disallow: /orders/',
        'Disallow: /account/',
        'Disallow: /accounts/',
        'Disallow: /search/suggest/',
        'Disallow: /healthz/',
        '',
        f'Sitemap: {base.rstrip("/")}/sitemap.xml',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def sitemap_xml(request):
    """
    GET /sitemap.xml — a static sitemap of every PUBLIC page:
    home, shop, active categories and active products (inactive
    products are excluded, so unpublishing removes them from Google).
    """
    base = request.build_absolute_uri('/')
    urls = [
        {'loc': f'{base}', 'lastmod': None, 'priority': '1.0'},
        {'loc': f'{base}shop/', 'lastmod': None, 'priority': '0.9'},
    ]
    for category in Category.objects.filter(active=True).order_by('slug'):
        urls.append({
            'loc': f'{base}category/{category.slug}/',
            'lastmod': category.created_at,
            'priority': '0.8',
        })
    for product in Product.objects.filter(active=True).order_by('slug'):
        urls.append({
            'loc': f'{base}product/{product.slug}/',
            'lastmod': product.created_at,
            'priority': '0.7',
        })
    return HttpResponse(
        render(request, 'sitemap.xml', {'base': base, 'urls': urls}),
        content_type='application/xml')


# ---------------------------------------------------------------------------
# Health check (PHASE 21 — deployment)
# ---------------------------------------------------------------------------
def health_check(request):
    """
    GET /healthz/ — the endpoint Render polls to decide whether this
    instance is alive (Blueprint: `healthCheckPath: /healthz/`).

    Why it deliberately does NOT touch the database:

      * On the free tier the service sleeps after 15 idle minutes and Neon
        suspends its compute after 5. A health check that queried Postgres
        would have to wait for BOTH cold starts, frequently blowing past
        Render's health-check timeout — and Render would then restart or
        fail an instance that is actually fine.
      * It would also keep waking Neon, burning its free compute hours.

    So this proves what it needs to prove — the Python process is up,
    Django's URL routing and middleware stack work, whitenoise isn't
    wedged — and returns in well under a millisecond.

    For a human doing a post-deploy check, `?db=1` additionally verifies
    the database round-trip (that one is allowed to be slow).
    """
    payload = {'status': 'ok'}

    if request.GET.get('db') == '1':
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            payload['database'] = 'ok'
        except Exception as exc:            # noqa: BLE001 — report, don't 500
            payload['status'] = 'degraded'
            payload['database'] = f'error: {exc.__class__.__name__}'
            return JsonResponse(payload, status=503)

    response = JsonResponse(payload)
    # A load balancer or browser must never cache "ok" and serve it later.
    response['Cache-Control'] = 'no-store, max-age=0'
    return response


# ---------------------------------------------------------------------------
# Error pages (wired via handlers403/404/500 in settings.py)
# ---------------------------------------------------------------------------
def error_403(request, exception):
    """Permission denied — styled 403 page."""
    return render(request, 'errors/403.html', status=403)


def error_404(request, exception):
    """Page not found — styled 404 page."""
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    """Server error — styled 500 page.

    NOTE: while DEBUG=True Django shows its detailed technical page instead
    (much more useful while developing). This page appears in production.
    """
    return render(request, 'errors/500.html', status=500)
