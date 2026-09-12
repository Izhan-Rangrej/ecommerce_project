"""
cart app — constants.

Single source of truth for how the cart is stored in the session.
"""

# The cart lives in the Django session under this key:
#   request.session[CART_SESSION_KEY] = {'<product_id>': quantity, ...}
CART_SESSION_KEY = 'cart'

# How long the cart (and session) survives without activity: 14 days.
CART_SESSION_LIFETIME = 14 * 24 * 60 * 60  # seconds
