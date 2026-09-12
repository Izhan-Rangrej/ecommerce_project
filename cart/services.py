"""
cart app — shared cart-mutation service.

Both the public "add to cart" endpoint (cart.views.add_to_cart) and the
wishlist "move to cart" action (customers.views.wishlist_move_to_cart)
call this, so stock validation and session handling live in ONE place —
they can never drift apart.

    ok, message, cart_count = add_to_cart(request, product, quantity)
"""

from .constants import CART_SESSION_KEY, CART_SESSION_LIFETIME

# A sanity cap so nobody can "add" a million units from a tampered form.
MAX_QTY_PER_REQUEST = 999


def get_cart(request):
    """The session cart as a dict: {'<product_id>': quantity, ...}."""
    return request.session.get(CART_SESSION_KEY) or {}


def save_cart(request, cart):
    """Persist the cart dict and keep it alive for 14 days of inactivity."""
    request.session[CART_SESSION_KEY] = cart
    request.session.set_expiry(CART_SESSION_LIFETIME)


def add_to_cart(request, product, quantity=1):
    """
    Add `quantity` units of `product` to the session cart.

    ALL validation happens here, on the server:
        * product must be in stock
        * existing cart qty + quantity must not exceed current stock
        * quantity is clamped to a sane 1..MAX_QTY_PER_REQUEST range

    :return: (ok, message, cart_count)
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1
    quantity = min(max(quantity, 1), MAX_QTY_PER_REQUEST)

    if not product.is_available:
        return (False,
                f"Sorry, '{product.name}' is currently out of stock.",
                sum(get_cart(request).values()))

    cart = get_cart(request)
    key = str(product.pk)
    current = int(cart.get(key, 0))

    if current + quantity > product.stock:
        return (False,
                f"Only {product.stock} unit(s) of '{product.name}' left in stock.",
                sum(cart.values()))

    cart[key] = current + quantity
    save_cart(request, cart)
    return True, f"'{product.name}' added to cart.", sum(cart.values())
