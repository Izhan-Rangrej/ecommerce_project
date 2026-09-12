"""
payments app — the payment gateway (PHASE 13).

TODAY: a simulated TEST gateway. No real money ever moves, which is
exactly what you want while building and testing a store.

THE GATEWAY-READY CONTRACT
--------------------------
The rest of the store talks to a gateway ONLY through this small
interface (see orders.views.place_order):

    1. charge(amount, card)      -> {'ok': bool, 'transaction_id': str,
                                     'message': str}
    2. refund(transaction_id)    -> {'ok': bool, ...}

and then calls payment.mark_paid(transaction_id) / mark_failed() —
the Payment record in the database is the single source of truth.

SWAPPING IN A REAL GATEWAY (Razorpay / Stripe) later
-----------------------------------------------------
1. Put the real keys in .env  ->  settings.PAYMENT_LIVE becomes True.
2. Re-implement charge()/refund() here with the gateway's SDK
   (Razorpay: order create + signature verify; Stripe: PaymentIntent).
   Real gateways confirm asynchronously via WEBHOOKS — verify the
   webhook's signature SERVER-SIDE, then mark_paid() in the DB.
3. Nothing else in the store changes: checkout, orders, admin, tests.

TEST CARD RULES (documented on the checkout page too)
-----------------------------------------------------
    * any 16-digit number is accepted, e.g. 4242 4242 4242 4242
    * 4000 0000 0000 0002 is ALWAYS declined (to test the failure path)
"""

import re
import secrets


# The one card that always fails — handy for testing the decline path.
TEST_DECLINED_CARD = '4000000000000002'


def _digits(value):
    """Strip everything that isn't a digit (spaces, dashes, …)."""
    return re.sub(r'\D', '', value or '')


def charge(amount, card_number, name, expiry, cvv):
    """
    Simulate charging a card for `amount`.

    Returns a gateway-style result:
        {'ok': bool, 'transaction_id': str, 'message': str}

    (In a real gateway this call creates the payment intent and the
    'ok' would come from the gateway's confirmation/webhook.)
    """
    number = _digits(card_number)

    # Defence in depth: the form already validated this, but the gateway
    # must never trust its callers.
    if len(number) != 16 or not _digits(cvv) or not (name or '').strip():
        return {'ok': False, 'transaction_id': '',
                'message': 'Invalid card details — please check and try again.'}

    if number == TEST_DECLINED_CARD:
        return {
            'ok': False, 'transaction_id': '',
            'message': 'The card was declined by the issuing bank (test). '
                       'Try another card, or choose Cash on Delivery.',
        }

    return {
        'ok': True,
        'transaction_id': 'pay_' + secrets.token_hex(8),
        'message': 'Payment successful.',
    }


def refund(transaction_id):
    """
    Simulate refunding a charge. Called when a card was charged but the
    order couldn't be created (e.g. stock ran out in the same instant) —
    a store must never keep money for goods it didn't ship.
    """
    return {'ok': True, 'transaction_id': transaction_id,
            'message': 'Refund initiated (test).'}
