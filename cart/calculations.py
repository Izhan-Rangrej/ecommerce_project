"""
cart app — shared price calculations.

WHY THIS FILE EXISTS (and why it's not inside a template or a view):
    The numbers shown on the cart page and the numbers written onto the
    final order MUST be identical. So both call this one function, and it
    always recomputes everything on the SERVER from live product prices.
    Nothing is ever trusted from the browser (a changed price, a tampered
    discount, ...).

Only pure logic in here — no request, no session, no database writes.
That makes it trivial to unit test (see PHASE 19).
"""

from decimal import Decimal

from django.conf import settings


def calculate_totals(items, coupon=None):
    """
    Compute all money numbers for a basket of products.

    :param items:  iterable of (product, quantity) pairs
                   (each product must be a saved Product instance)
    :param coupon: a products.models.Coupon instance, or None
    :return: dict with keys:
                subtotal, discount, shipping, tax, grand_total
             (all Decimal values, rounded to 2 decimal places)
    """
    items = list(items)

    # --- 1. Subtotal: sum of (final sale price x quantity) -----------------
    subtotal = sum(
        (product.final_price * quantity for product, quantity in items),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    # --- 2. Discount: only if the coupon is valid for THIS basket ----------
    discount = Decimal('0.00')
    if coupon is not None:
        is_valid, _reason = coupon.validate_for_order(subtotal)
        if is_valid:
            discount = coupon.calculate_discount(subtotal)

    amount_after_discount = subtotal - discount

    # --- 3. Shipping: free above the threshold, otherwise flat fee ---------
    if subtotal == 0:
        shipping = Decimal('0.00')
    elif amount_after_discount >= settings.FREE_SHIPPING_THRESHOLD:
        shipping = Decimal('0.00')
    else:
        shipping = settings.STANDARD_SHIPPING_FEE

    # --- 4. Tax: on the discounted amount ----------------------------------
    tax = (amount_after_discount * settings.TAX_RATE).quantize(Decimal('0.01'))

    # --- 5. Grand total -----------------------------------------------------
    grand_total = (
        amount_after_discount + shipping + tax
    ).quantize(Decimal('0.01'))

    return {
        'subtotal': subtotal,
        'discount': discount,
        'shipping': shipping,
        'tax': tax,
        'grand_total': grand_total,
    }
