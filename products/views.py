"""
products app — views.

PHASE 7:
    /shop/               the main listing — search + filters + sort + pagination
    /category/<slug>/    a category page (same listing, locked to one category)
    /product/<slug>/     detail page — gallery, reviews, related products
    /search/             legacy URL, redirects to /shop/ (old links keep working)

PHASE 15: purchase-verified reviews on the detail page.
PHASE 16: /search/suggest/ JSON for live search suggestions (JS
          enhancement only) + category-aware filter links + facet counts.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator, PageNotAnInteger
from django.db.models import Avg, Case, Count, DecimalField, F, Q, Sum, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.ratelimit import check_rate_limit
from orders.models import Order, OrderItem

from .forms import ReviewForm
from .models import Brand, Category, Product, Review

# PHASE 18: longer than this buys nothing (and costs DB time) —
# search terms are truncated to this length in every listing.
MAX_SEARCH_LENGTH = 100

# How many products per page on the shop listing.
PER_PAGE = 12

# The five sort options, shown as buttons on the listing page.
# (value used in the URL, label shown to the customer)
SORT_OPTIONS = [
    ('newest', 'Newest'),
    ('price_asc', 'Price: Low to High'),
    ('price_desc', 'Price: High to Low'),
    ('popular', 'Best selling'),
    ('rating', 'Top rated'),
]
SORT_KEYS = {key for key, _ in SORT_OPTIONS}


# ---------------------------------------------------------------------------
# Listing helpers (shared by /shop/ and /category/<slug>/)
# ---------------------------------------------------------------------------
def _base_products():
    """
    Every ACTIVE product, pre-annotated with the numbers the listing needs:

        effective_price  -> the price the customer actually pays
                            (discount_price when present, else price)
        avg_rating       -> average of its reviews (None if no reviews)
        review_count     -> how many reviews it has
        total_units      -> units sold, from real orders ("Best selling")

    Doing all of this ONCE here means the filters/sorts below stay one
    query (no N+1, no re-computing per sort).
    """
    return (
        Product.objects.filter(active=True)
        .select_related('category', 'brand')
        .annotate(
            effective_price=Case(
                When(discount_price__gt=0, then=F('discount_price')),
                default=F('price'),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews'),
            total_units=Coalesce(Sum('order_items__quantity'), 0),
        )
    )


def _get_money(request, name):
    """Read a non-negative decimal from the query string (else None)."""
    raw = (request.GET.get(name) or '').strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _get_rating(request):
    """Read a 1–5 minimum-rating value from the query string (else None)."""
    raw = (request.GET.get('rating') or '').strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if 1 <= value <= 5 else None


def _apply_filters(qs, request, fixed_category=None,
                   include_category=True, include_brand=True):
    """
    Layer the filters on top of the base queryset:

        text search (q) -> category -> brand -> price range -> min rating

    A category page passes `fixed_category`, which ignores the `category`
    GET param (you can't browse "Electronics" and filter by "Fashion").
    The include_* flags let the listing page compute facet counts —
    "how many results would I get if I picked X?" — by applying every
    filter EXCEPT the group being counted.
    """
    # PHASE 18: truncate absurdly long search terms (abuse guard).
    q = (request.GET.get('q') or '').strip()[:MAX_SEARCH_LENGTH]
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
            | Q(brand__name__icontains=q),
        ).distinct()

    # A page that is LOCKED to a category always keeps that lock —
    # even when counting a different group's facets.
    if fixed_category is not None:
        qs = qs.filter(category=fixed_category)
    elif include_category:
        cat_slug = (request.GET.get('category') or '').strip()
        if cat_slug:
            qs = qs.filter(category__slug=cat_slug)

    if include_brand:
        brand_slug = (request.GET.get('brand') or '').strip()
        if brand_slug:
            qs = qs.filter(brand__slug=brand_slug)

    price_min = _get_money(request, 'min')
    if price_min is not None:
        qs = qs.filter(effective_price__gte=price_min)
    price_max = _get_money(request, 'max')
    if price_max is not None:
        qs = qs.filter(effective_price__lte=price_max)

    min_rating = _get_rating(request)
    if min_rating:
        # Products with NO reviews have avg_rating = NULL and are
        # naturally excluded — a "4★ & up" filter should not show them.
        qs = qs.filter(avg_rating__gte=min_rating)

    return qs


def _apply_sort(qs, request):
    """Apply one of the five sort options (default: newest first)."""
    sort = (request.GET.get('sort') or 'newest').strip()
    if sort not in SORT_KEYS:
        sort = 'newest'
    ordering = {
        'newest': '-created_at',
        'price_asc': 'effective_price',
        'price_desc': '-effective_price',
        'popular': '-total_units',
        'rating': '-avg_rating',
    }[sort]
    # -pk as a tie-breaker keeps pagination stable within equal values.
    return qs.order_by(ordering, '-pk')


def _listing_context(request, title, subtitle, fixed_category=None):
    """Build every value the product_list.html template needs."""
    qs = _apply_sort(_apply_filters(_base_products(), request, fixed_category), request)

    paginator = Paginator(qs, PER_PAGE)
    try:
        page_obj = paginator.page(request.GET.get('page') or 1)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)   # junk/missing page number -> page 1

    # ---- sidebar data: "facet" counts (PHASE 16) ------------------------
    # Each group's counts show "how many results you'd get by picking
    # THIS value" — every filter is applied EXCEPT the group's own
    # selection (so you can still see the other options and their
    # counts). With no filters active these are just plain totals.
    cat_scope = _apply_filters(
        _base_products(), request, fixed_category, include_category=False)
    brand_scope = _apply_filters(
        _base_products(), request, fixed_category, include_brand=False)

    categories = (
        Category.objects.filter(active=True)
        .annotate(count=Count(
            'products',
            filter=Q(products__in=cat_scope.values('pk'),
                     products__active=True),
        ))
        .order_by('name')
    )
    brands = (
        Brand.objects
        .annotate(count=Count(
            'products',
            filter=Q(products__in=brand_scope.values('pk'),
                     products__active=True),
        ))
        .filter(count__gt=0)
        .order_by('name')
    )

    # ---- which filters are currently ACTIVE (for chips + sidebar) ----
    q = (request.GET.get('q') or '').strip()
    if fixed_category is not None:
        active_category = fixed_category
        cat_slug = ''
    else:
        cat_slug = (request.GET.get('category') or '').strip()
        active_category = (
            Category.objects.filter(slug=cat_slug).first() if cat_slug else None
        )
    brand_slug = (request.GET.get('brand') or '').strip()
    active_brand = Brand.objects.filter(slug=brand_slug).first() if brand_slug else None
    price_min = _get_money(request, 'min')
    price_max = _get_money(request, 'max')
    min_rating = _get_rating(request)
    sort = (request.GET.get('sort') or 'newest').strip()
    if sort not in SORT_KEYS:
        sort = 'newest'

    return {
        'products': page_obj,
        'paginator': paginator,
        'page_obj': page_obj,
        'list_title': title,
        'list_subtitle': subtitle,
        'list_category': fixed_category,
        'result_count': paginator.count,
        'page': page_obj.number,
        'num_pages': paginator.num_pages,
        # sidebar
        'categories': categories,
        'brands': brands,
        # active filter state
        'q': q,
        'active_category': active_category,
        'cat_slug': cat_slug,
        'active_brand': active_brand,
        'price_min': price_min,
        'price_max': price_max,
        'min_rating': min_rating,
        'sort': sort,
        'sort_options': SORT_OPTIONS,
        # Django templates can't iterate a literal list like "5 4 3 2",
        # so the star choices come from the view.
        'rating_choices': [5, 4, 3, 2],
        'has_filters': bool(q or fixed_category or cat_slug or brand_slug
                            or price_min is not None or price_max is not None
                            or min_rating),
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def shop(request):
    """/shop/ — the full listing: search + filters + sort + pagination."""
    title = 'All products'
    subtitle = 'Browse the full catalog — filter by category, brand, price or rating.'
    if (request.GET.get('q') or '').strip():
        title = f"Search: “{(request.GET.get('q') or '').strip()}”"
        subtitle = 'Refine the results with the filters on the left.'
    context = _listing_context(request, title, subtitle)
    return render(request, 'products/product_list.html', context)


def category_detail(request, slug):
    """/category/<slug>/ — the same listing, locked to one category."""
    category = get_object_or_404(Category, slug=slug, active=True)
    context = _listing_context(
        request,
        title=category.name,
        subtitle=category.description
            or f'Everything in {category.name}, in one place.',
        fixed_category=category,
    )
    return render(request, 'products/product_list.html', context)


@require_GET
def search_suggest(request):
    """
    GET /search/suggest/?q=... — PHASE 16.

    JSON endpoint behind the navbar search-suggestions dropdown:

        {"results": [{"name", "url", "price", "image"}, ...]}

    Progressive enhancement ONLY: the navbar box is a plain GET form,
    so the site works exactly the same when JavaScript is off or this
    fetch fails. Kept deliberately cheap — max 6 rows, no annotations
    beyond the base listing ones, short-circuits below 2 characters.
    """
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    q = q[:MAX_SEARCH_LENGTH]

    qs = (
        _base_products()
        .filter(
            Q(name__icontains=q)
            | Q(short_description__icontains=q)
            | Q(brand__name__icontains=q)
            | Q(category__name__icontains=q),
        )
        .order_by('name', '-review_count')[:6]
    )
    results = [
        {
            'name': p.name,
            'url': reverse('products:detail', args=[p.slug]),
            # Format explicitly: some database backends (SQLite in
            # particular) return '899' instead of '899.00' for a decimal.
            'price': f"{p.effective_price:.2f}",
            'image': p.image.url if p.image else '',
        }
        for p in qs
    ]
    return JsonResponse({'results': results})


def _has_purchased(product, user):
    """
    PHASE 15 — the purchase gate: True when `user` bought `product` in an
    order that is NOT cancelled. (A cancelled purchase didn't happen, so
    it doesn't earn a review.)
    """
    active_statuses = [
        status.value for status in Order.Status
        if status is not Order.Status.CANCELLED
    ]
    return OrderItem.objects.filter(
        product=product,
        order__user=user,
        order__order_status__in=active_statuses,
    ).exists()


def _product_detail_context(request, product, form=None):
    """Everything product_detail.html needs (shared with review errors)."""
    # Gallery = main photo first, then every extra photo.
    gallery = [{'src': product.image.url, 'alt': product.name}]
    gallery.extend(
        {'src': img.image.url, 'alt': img.alt_text or product.name}
        for img in product.images.all()
    )

    # Reviews: average + a 5..1 distribution + the list, newest first.
    reviews = list(
        product.reviews.select_related('user').order_by('-created_at', '-id')
    )
    review_count = len(reviews)
    avg_rating = (
        round(sum(r.rating for r in reviews) / review_count, 1)
        if review_count else 0
    )
    # (star, count, percent) — percent pre-computed so the template only
    # renders it into the bar width (templates can't do arithmetic).
    distribution = []
    for star in range(5, 0, -1):
        count = sum(1 for r in reviews if r.rating == star)
        percent = (count / review_count * 100) if review_count else 0.0
        distribution.append((star, count, percent))

    # Related = other active products in the same category (with ratings
    # pre-annotated so the cards show stars).
    related = (
        _base_products()
        .filter(category=product.category)
        .exclude(pk=product.pk)[:4]
    )

    # ---- PHASE 15: review-form state --------------------------------------
    user = request.user
    own_review = None
    has_purchased = False
    if user.is_authenticated:
        own_review = Review.objects.filter(product=product, user=user).first()
        has_purchased = _has_purchased(product, user)
        if has_purchased:
            # Unbound (new review) or bound to the existing one (update).
            form = form or ReviewForm(product=product, instance=own_review)

    return {
        'product': product,
        'gallery': gallery,
        'has_gallery': len(gallery) > 1,
        'reviews': reviews,
        'review_count': review_count,
        'avg_rating': avg_rating,
        'distribution': distribution,
        'related': related,
        'form': form,
        'own_review': own_review,
        'has_purchased': has_purchased,
        'star_values': [1, 2, 3, 4, 5],
    }


def product_detail(request, slug):
    """
    /product/<slug>/ — the full product page:

        image gallery (main photo + extra photos from the admin)
        rating summary + per-star distribution
        review list + the purchase-verified review form (PHASE 15)
        related products (same category)
    """
    product = get_object_or_404(
        Product.objects.select_related('category', 'brand')
                       .prefetch_related('images'),
        slug=slug,
        active=True,
    )
    return render(
        request, 'products/product_detail.html',
        _product_detail_context(request, product),
    )


@login_required
@require_POST
def write_review(request, slug):
    """
    POST /product/<slug>/review/ — PHASE 15.

    Purchase-verified: only a customer who bought the product (in a
    non-cancelled order) can review it. One review per customer per
    product — a second submission UPDATES the existing review.
    """
    product = get_object_or_404(Product, slug=slug, active=True)

    # PHASE 18: max 10 reviews / IP / 10 minutes (spam guard).
    allowed, wait_min = check_rate_limit(request, 'write-review', 10, 600)
    if not allowed:
        messages.error(
            request,
            f'Too many reviews submitted. Please wait about '
            f'{wait_min} minute(s) and try again.',
        )
        return redirect_detail(product)

    if not _has_purchased(product, request.user):
        messages.error(
            request,
            'Only customers who purchased this product can review it.',
        )
        return redirect_detail(product)

    own_review = Review.objects.filter(product=product, user=request.user).first()
    form = ReviewForm(request.POST, product=product, user=request.user,
                      instance=own_review)
    if form.is_valid():
        review = form.save()
        if own_review is None:
            messages.success(request, 'Your review has been posted — thank you!')
        else:
            messages.success(request, 'Your review has been updated.')
        return redirect_detail(product)

    # Invalid: re-render the product page WITH the field errors.
    return render(
        request, 'products/product_detail.html',
        _product_detail_context(request, product, form=form),
    )


def redirect_detail(product):
    """Back to the product page, scrolled to the reviews section."""
    return redirect(reverse('products:detail', args=[product.slug]) + '#reviews')
