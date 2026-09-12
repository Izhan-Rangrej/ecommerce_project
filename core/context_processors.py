"""
core — template context available on EVERY page.

A "context processor" is a function that Django runs on every request and
whose return dict is added to every template's context. We use them for
the three little numbers/menus in the navbar:

    categories      -> the "Categories" dropdown
    cart_count      -> the badge on the cart icon
    wishlist_count  -> the badge on the heart icon
"""

from django.core.cache import cache

from cart.constants import CART_SESSION_KEY
from customers.models import WishlistItem
from products.models import Category


def categories(request):
    """
    Active categories for the navbar dropdown (a handful, alphabetically).
    PHASE 18: cached for 5 minutes — this ran on EVERY page before; the
    cache is invalidated by signals when categories/products change
    (core/signals.py), so it stays fresh.
    """
    cats = cache.get('navbar_categories')
    if cats is None:
        cats = list(Category.objects.filter(active=True).order_by('name')[:8])
        cache.set('navbar_categories', cats, 300)
    return {'categories': cats}


def cart_count(request):
    """Total items in the session cart (0 for guests)."""
    cart = request.session.get(CART_SESSION_KEY) or {}
    return {'cart_count': sum(int(qty) for qty in cart.values())}


def wishlist_count(request):
    """How many products the logged-in user saved (0 for guests)."""
    if request.user.is_authenticated:
        return {'wishlist_count': request.user.wishlist.count()}
    return {'wishlist_count': 0}
