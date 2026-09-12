"""
cart app — views (session-based cart core).

The cart is stored in the Django session under CART_SESSION_KEY:

    request.session['cart'] = {'<product_id>': quantity, ...}

Why a session and not a database table?
    * It's fast (no extra queries) and needs no migrations.
    * The cart naturally belongs to the *visitor*, logged in or not.
    (Merging a guest cart into an account after login is a later
    enhancement — PHASE 11, at checkout.)

Every mutating view works TWO ways:
    * AJAX  (X-Fetch: 1 from main.js)  -> small JSON response
    * Classic POST (JavaScript OFF)    -> redirect + Django message
...so the store works even without JavaScript.

PHASE 5: add / remove / clear.
PHASE 9: the /cart/ page, quantity updates with live totals,
         stock re-validation on every read/update.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.utils import is_ajax, safe_next
from products.models import Product

from . import services
from .calculations import calculate_totals
from .constants import CART_SESSION_KEY, CART_SESSION_LIFETIME
from .services import MAX_QTY_PER_REQUEST   # sanity cap, defined in services


def _get_cart(request):
    return services.get_cart(request)


def _save_cart(request, cart):
    services.save_cart(request, cart)


@require_POST
def add_to_cart(request, product_id):
    """Add `quantity` units of a product to the session cart.

    The actual stock validation + session write live in
    cart.services.add_to_cart (shared with the wishlist move-to-cart).
    """
    product = get_object_or_404(Product, pk=product_id, active=True)
    ok, message, count = services.add_to_cart(
        request, product, request.POST.get('quantity', 1)
    )

    if is_ajax(request):
        return JsonResponse(
            {'ok': ok, 'message': message, 'cart_count': count},
            status=200 if ok else 400,
        )

    if ok:
        messages.success(request, message)
        next_url = safe_next(request.POST.get('next'))
        return redirect(next_url or 'products:detail', product.slug)

    messages.error(request, message)
    return redirect('products:detail', product.slug)


@require_POST
def remove_from_cart(request, product_id):
    """Remove a product line from the session cart."""
    product = get_object_or_404(Product, pk=product_id, active=True)
    cart = _get_cart(request)
    key = str(product.pk)

    if key in cart:
        del cart[key]
        _save_cart(request, cart)
        message = f"'{product.name}' removed from cart."
    else:
        message = f"'{product.name}' was not in your cart."

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'message': message,
            'cart_count': sum(cart.values()),
        })
    messages.info(request, message)
    return redirect(safe_next(request.POST.get('next')) or 'products:search')


@require_POST
def clear_cart(request):
    """Empty the whole cart."""
    request.session.pop(CART_SESSION_KEY, None)
    message = 'Your cart has been cleared.'

    if is_ajax(request):
        return JsonResponse({'ok': True, 'message': message, 'cart_count': 0})
    messages.success(request, message)
    return redirect('cart:page')


# ---------------------------------------------------------------------------
# PHASE 9 — the cart page + quantity updates
# ---------------------------------------------------------------------------
def _cart_lines(request):
    """
    Read the session cart and build the display lines + the totals.

    While reading, the cart is HEALED (stock is live — it can change
    after an item was added):

        * product deleted/deactivated  -> line removed from the session
        * quantity above current stock -> clamped down to stock
        * stock now 0                  -> line kept, flagged `oos`
                                         (the customer decides what to do)

    Returns (lines, totals, meta):
        lines  -> [{'product', 'qty', 'line_total', 'oos'}, ...]
        totals -> the dict from calculate_totals (OOS lines excluded)
        meta   -> {'removed_count', 'adjusted': [names], 'oos_count'}
    """
    cart = _get_cart(request)
    lines, adjusted = [], []
    removed_count = oos_count = changed = 0

    if cart:
        # One query for every product that still exists and is active.
        valid_keys = [k for k in cart if str(k).isdigit()]
        products = {
            str(p.pk): p
            for p in Product.objects
            .filter(pk__in=[int(k) for k in valid_keys], active=True)
            .select_related('category', 'brand')
        }

        for key in list(cart.keys()):
            raw_qty = cart[key]
            qty = int(raw_qty) if str(raw_qty).isdigit() else 1
            product = products.get(key)

            if product is None:
                # Gone from the catalog (deleted or deactivated).
                del cart[key]
                removed_count += 1
                changed = True
                continue

            if not product.is_available:
                oos_count += 1
                lines.append({'product': product, 'qty': qty,
                              'line_total': None, 'oos': True})
                continue

            if qty > product.stock:
                qty = product.stock
                cart[key] = qty
                adjusted.append(product.name)
                changed = True

            lines.append({
                'product': product,
                'qty': qty,
                'line_total': product.final_price * qty,
                'oos': False,
            })

        if changed:
            _save_cart(request, cart)

    items = [(line['product'], line['qty']) for line in lines if not line['oos']]
    totals = calculate_totals(items)
    meta = {'removed_count': removed_count, 'adjusted': adjusted,
            'oos_count': oos_count}
    return lines, totals, meta


def _shipping_progress(totals):
    """How far the basket is from the free-shipping threshold."""
    threshold = Decimal(settings.FREE_SHIPPING_THRESHOLD)
    amount = totals['subtotal'] - totals['discount']
    remaining = max(threshold - amount, Decimal('0'))
    percent = 100.0
    if threshold > 0:
        percent = min(100.0, float(amount * 100 / threshold))
    return {
        'threshold': threshold,
        'remaining': remaining,
        'percent': round(percent, 1),
        'reached': remaining == 0 and amount > 0,
    }


def cart_page(request):
    """GET /cart/ — the cart page (guests can view their session cart too)."""
    lines, totals, meta = _cart_lines(request)

    if meta['removed_count']:
        messages.warning(
            request,
            f"{meta['removed_count']} item{'s' if meta['removed_count'] > 1 else ''} "
            'in your cart are no longer available and were removed.',
        )
    if meta['adjusted']:
        messages.warning(
            request,
            f"Quantities adjusted to available stock for: {', '.join(meta['adjusted'])}.",
        )

    progress = _shipping_progress(totals)
    context = {
        'lines': lines,
        'totals': totals,
        'cart_count': sum(l['qty'] for l in lines if not l['oos']),
        'cart_empty': not lines,
        'has_oos': meta['oos_count'] > 0,
        'shipping': progress,
    }
    return render(request, 'cart/cart.html', context)


def _cart_error(request, message):
    """Uniform error response for the cart mutations (AJAX -> 400 JSON)."""
    if is_ajax(request):
        return JsonResponse({'ok': False, 'message': message}, status=400)
    messages.error(request, message)
    return redirect('cart:page')


@require_POST
def update_quantity(request, product_id):
    """
    POST /cart/update/<product_id>/ — set a line's quantity.

    AJAX response carries the new line total AND the full basket totals,
    so main.js can update the page in place without a reload. The
    no-JS path is a classic form submit -> redirect back to /cart/.
    """
    product = get_object_or_404(Product, pk=product_id, active=True)
    cart = _get_cart(request)
    key = str(product.pk)

    if key not in cart:
        return _cart_error(request, f"'{product.name}' is not in your cart.")
    if not product.is_available:
        return _cart_error(request, f"'{product.name}' is currently out of stock.")

    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(quantity, 1)

    max_qty = min(product.stock, MAX_QTY_PER_REQUEST)
    if quantity > max_qty:
        return _cart_error(
            request,
            f"Only {product.stock} unit(s) of '{product.name}' left in stock.",
        )

    if quantity != int(cart.get(key, 1)):
        cart[key] = quantity
        _save_cart(request, cart)

    # Recompute everything the page shows, server-side.
    _, totals, meta = _cart_lines(request)
    progress = _shipping_progress(totals)
    message = f"Updated '{product.name}'."

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'message': message,
            'cart_count': sum(int(q) for q in cart.values()),
            'max_qty': max_qty,
            'unit_price': str(product.final_price),
            'line_total': str(product.final_price * quantity),
            'totals': {k: str(v) for k, v in totals.items()},
            'free_shipping_remaining': str(progress['remaining']),
            'free_shipping_percent': str(progress['percent']),
            'has_oos': meta['oos_count'] > 0,
        })

    # No JavaScript: classic POST -> redirect back to the cart page.
    messages.success(request, message)
    return redirect('cart:page')
