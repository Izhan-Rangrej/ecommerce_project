"""
orders app — views (PHASE 11: the 5-step checkout).

The five steps
    1. Shipping address   pick a saved address, or add a new one
    2. Delivery option    standard delivery (fee calculated automatically)
    3. Payment method     Cash on Delivery (online payments in PHASE 13)
    4. Review & place     items + address + delivery + payment + notes
    5. Order complete     the thank-you screen with the order number

How it works (why it is built this way):
    * Every step is a plain <form> + redirect, so the WHOLE flow works
      with JavaScript completely turned off.
    * The selections (address, payment, current step) live in the
      session, so each step is one small POST.
    * Money and stock are ALWAYS re-computed server-side from the live
      database (cart._cart_lines + Order.place). Nothing sent by the
      browser is trusted.
    * Placing the order is ONE atomic operation — Order.place() locks
      the product rows, validates stock, creates the order + items +
      payment record, reduces stock, and the view clears the cart.
      Because the cart is cleared, a double-submitted "Place order"
      button can never create a second order.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.calculations import calculate_totals
from cart.constants import CART_SESSION_KEY
from cart.views import _cart_lines
from core.ratelimit import check_rate_limit   # PHASE 18
from customers.forms import AddressForm
from customers.models import Address
from orders.models import Order
from payments.forms import TestCardForm
from payments.gateway import _digits, charge as gateway_charge, refund as gateway_refund
from payments.models import Payment
from products.models import Coupon, Product

CHECKOUT_SESSION_KEY = 'checkout'
STEP_TOTAL = 4  # interactive steps; step 5 (complete) is its own page

# Payment methods accepted at checkout (PHASE 13: 'card' = test gateway).
PAYMENT_METHODS = {'cod', 'card'}

# The five labels shown in the progress bar (5 = the "complete" screen).
STEP_LABELS = ['Address', 'Delivery', 'Payment', 'Review', 'Complete']


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _checkout_state(request):
    """Read (and normalise) the in-progress checkout from the session."""
    state = request.session.get(CHECKOUT_SESSION_KEY) or {}
    try:
        step = int(state.get('step', 1))
    except (TypeError, ValueError):
        step = 1
    state['step'] = min(max(step, 1), STEP_TOTAL)
    state.setdefault('address_id', None)
    state.setdefault('payment', 'cod')
    return state


def _save_state(request, state):
    request.session[CHECKOUT_SESSION_KEY] = state
    request.session.modified = True


def _reset_state(request):
    request.session.pop(CHECKOUT_SESSION_KEY, None)


def _available_items(request):
    """
    Re-heal the session cart (same logic as the cart page) and return
    (lines, totals, meta, items) where items = [(product, qty), ...]
    for every line that still has stock.
    """
    lines, totals, meta = _cart_lines(request)
    items = [(line['product'], line['qty']) for line in lines if not line['oos']]
    return lines, totals, meta, items


def _checkout_context(request, state, form=None, card_form=None):
    """Build everything the checkout page needs for the current step."""
    lines, totals, meta, items = _available_items(request)

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

    # ---- which address is selected? -------------------------------------
    # The saved selection wins; if it was deleted, fall back to the
    # user's default (or first) address so step 1 is preselected.
    addresses = list(request.user.addresses.all())
    selected = None
    for address in addresses:
        if address.pk == state['address_id']:
            selected = address
            break
    if selected is None:
        selected = next((a for a in addresses if a.is_default), None) \
            or (addresses[0] if addresses else None)
        state['address_id'] = selected.pk if selected else None

    # ---- guard: without an address, steps 2-4 are unreachable -----------
    if state['step'] > 1 and state['address_id'] is None:
        state['step'] = 1
    # ---- guard: a card needs valid details before the review ------------
    if state['step'] > 3 and state['payment'] == 'card' and not state.get('card'):
        state['step'] = 3

    # ---- coupon (PHASE 14): resolve from the DB on EVERY render ----------
    # Only the CODE is kept in the session — the coupon itself is re-read
    # and re-validated each time, so an expired/used-up/min-not-met coupon
    # is dropped automatically (with a warning) instead of silently
    # discounting an order it no longer may.
    coupon = None
    code = (state.get('coupon_code') or '').strip()
    if code:
        candidate = Coupon.objects.filter(code__iexact=code).first()
        if candidate is None:
            state.pop('coupon_code', None)
        else:
            subtotal = sum(
                (product.final_price * quantity for product, quantity in items),
                Decimal('0.00'),
            )
            is_valid, reason = candidate.validate_for_order(subtotal)
            if is_valid:
                coupon = candidate
                state['coupon_code'] = candidate.code
            else:
                state.pop('coupon_code', None)
                messages.warning(
                    request, f"Coupon {candidate.code} no longer applies: {reason}"
                )
    if coupon is not None:
        totals = calculate_totals(items, coupon=coupon)

    _save_state(request, state)

    return {
        'step': state['step'],
        'steps': STEP_LABELS,
        'addresses': addresses,
        'selected_address': selected,
        'address_form': form or AddressForm(),
        'payment_method': state['payment'],
        'coupon': coupon,
        'card_form': card_form or TestCardForm(state.get('card') or {}),
        'card_last4': _digits(state.get('card', {}).get('card_number', ''))[-4:],
        'lines': lines,
        'totals': totals,
        'cart_count': sum(quantity for _product, quantity in items),
        'free_shipping_threshold': settings.FREE_SHIPPING_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# step 1 — page + address selection
# ---------------------------------------------------------------------------
@login_required
def checkout(request):
    """GET /checkout/ — the 5-step checkout (steps 1-4, one per page)."""
    state = _checkout_state(request)
    context = _checkout_context(request, state)

    # Out-of-stock lines can't be part of an order — the cart page is
    # where they get removed (its remove buttons work right there).
    # Without this guard, ordering would silently skip those items.
    if any(line['oos'] for line in context['lines']):
        messages.warning(
            request,
            'Some items in your cart are out of stock — remove them '
            'to continue with checkout.',
        )
        return redirect('cart:page')

    if not context['lines']:
        messages.info(
            request, 'Your cart is empty — add something before checking out.'
        )
        return redirect('cart:page')

    return render(request, 'checkout/checkout.html', context)


@login_required
def checkout_step(request, step):
    """
    GET /checkout/step/<n>/ — the "Back" links + "Change" links.

    The review page's "Change" links pass ?ret=<step>: after the change
    is saved, the customer lands back on review instead of re-walking
    the whole wizard.
    """
    if step not in range(1, STEP_TOTAL + 1):
        raise Http404('Unknown checkout step.')
    state = _checkout_state(request)
    state['step'] = step

    ret = request.GET.get('ret', '')
    if ret.isdigit() and 2 <= int(ret) <= STEP_TOTAL:
        state['return_to'] = int(ret)
    else:
        state.pop('return_to', None)
    _save_state(request, state)
    # GET /checkout/ re-validates everything (cart, address, step order).
    return redirect('orders:checkout')


@login_required
@require_POST
def checkout_address(request):
    """
    POST /checkout/address/ — step 1.

    Two shapes of POST arrive here (same URL, one <form>):
        * a radio selected        -> 'address_id' in request.POST
        * the new-address form    -> AddressForm fields
    (The "Add a new address" form sits inside the same <form>, so both
    can be present in one submission — a selected radio wins.)
    """
    state = _checkout_state(request)

    if 'address_id' in request.POST:
        # Pick an existing saved address — must belong to THIS user.
        address = get_object_or_404(
            Address, pk=request.POST['address_id'], user=request.user
        )
        message = f"Shipping to {address.full_name} — {address.city}."
    else:
        form = AddressForm(request.POST)
        if not form.is_valid():
            messages.error(
                request, 'Please check the address details and try again.'
            )
            context = _checkout_context(request, state, form=form)
            return render(request, 'checkout/checkout.html', context)
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        message = 'Address saved — shipping there.'

    state['address_id'] = address.pk
    # From step 1 -> advance to delivery. Returning from a "Change"
    # link (?ret=N) -> go back to the step that sent the customer here.
    return_to = state.pop('return_to', None)
    state['step'] = return_to if return_to else max(state['step'], 2)
    _save_state(request, state)
    messages.success(request, message)
    return redirect('orders:checkout')


# ---------------------------------------------------------------------------
# steps 2-3 — delivery + payment (one confirm each)
# ---------------------------------------------------------------------------
@login_required
@require_POST
def checkout_continue(request):
    """
    POST /checkout/continue/ — steps 2 and 3.

    Step 2 (delivery): a single option today (standard) — the step
    exists so the flow stays clean when express delivery is added.
    Step 3 (payment):  the choice is validated against the allow-list.
    """
    state = _checkout_state(request)

    if state['step'] == 2:
        if request.POST.get('delivery', 'standard') != 'standard':
            messages.error(request, 'Please choose a valid delivery option.')
        else:
            state['step'] = 3
    elif state['step'] == 3:
        payment = request.POST.get('payment', '')
        if payment == 'cod':
            state['payment'] = 'cod'
            state.pop('card', None)     # ditch any card details entered
            state['step'] = 4
        elif payment == 'card':
            # Test-mode card: validate the details NOW, before review.
            card_form = TestCardForm(request.POST)
            if not card_form.is_valid():
                messages.error(
                    request, 'Please check the card details and try again.')
                # Mark 'card' as the chosen method so the template re-
                # renders the card form WITH the field errors visible.
                state['payment'] = 'card'
                context = _checkout_context(request, state, card_form=card_form)
                return render(request, 'checkout/checkout.html', context)
            state['card'] = card_form.cleaned_data
            state['payment'] = 'card'
            state['step'] = 4
        else:
            messages.error(request, 'Please choose a valid payment method.')
    # Steps 1 and 4 have nothing to "continue" — just re-render checkout.

    _save_state(request, state)
    return redirect('orders:checkout')


# ---------------------------------------------------------------------------
# step 4 — place the order
# ---------------------------------------------------------------------------
@login_required
@require_POST
def place_order(request):
    """
    POST /checkout/place-order/ — step 4 -> step 5.

    Re-validates everything server-side (address ownership, payment
    allow-list, live stock) and then calls Order.place(): ONE
    transaction that locks the product rows, checks stock, creates the
    order + items + payment record and reduces stock. On success the
    cart is cleared, so a double-click / double-submit can never place
    a second order.
    """
    state = _checkout_state(request)
    lines, totals, meta, items = _available_items(request)

    # PHASE 18: max 10 real placement attempts / IP / 10 minutes.
    # (Checked only when there IS something to order, so empty-cart
    # bounces don't eat into the budget.)
    if items:
        allowed, wait_min = check_rate_limit(request, 'place-order', 10, 600)
        if not allowed:
            messages.error(
                request,
                f'Too many order attempts from this address. Please wait '
                f'about {wait_min} minute(s) and try again.',
            )
            return redirect('cart:page')

    if not items:
        messages.info(request, 'Your cart is empty — nothing to order.')
        return redirect('cart:page')

    # Never place a PARTIAL order: if any line went out of stock since
    # the customer started checkout, send them back to fix the cart.
    if meta['oos_count']:
        messages.error(
            request,
            'Some items in your cart are out of stock — remove them '
            'from your cart to place the order.',
        )
        return redirect('cart:page')

    if state['address_id'] is None:
        messages.error(request, 'Please choose a shipping address first.')
        state['step'] = 1
        _save_state(request, state)
        return redirect('orders:checkout')

    address = get_object_or_404(
        Address, pk=state['address_id'], user=request.user
    )
    payment_method = state['payment'] if state['payment'] in PAYMENT_METHODS else 'cod'
    notes = (request.POST.get('notes') or '').strip()[:500]

    # Coupon (PHASE 14): Order.place re-validates it against the FINAL
    # subtotal inside the transaction and raises ValueError if it no
    # longer applies — an invalid coupon can never reduce the price.
    coupon = None
    code = (state.get('coupon_code') or '').strip()
    if code:
        coupon = Coupon.objects.filter(code__iexact=code).first()
        if coupon is None:
            state.pop('coupon_code', None)
            _save_state(request, state)

    # ---- card (test gateway): charge BEFORE creating the order ----------
    # Same shape a real gateway has: charge -> verify -> mark_paid().
    charge_result = None
    if payment_method == 'card':
        card = state.get('card') or {}
        card_form = TestCardForm(card)      # re-validate — never trust it
        if not card_form.is_valid():
            messages.error(
                request, 'Your saved card details are invalid — update them and try again.')
            state['step'] = 3
            _save_state(request, state)
            return redirect('orders:checkout')
        charge_result = gateway_charge(
            amount=totals['grand_total'],
            card_number=card_form.cleaned_data['card_number'],
            name=card_form.cleaned_data['name'],
            expiry=card_form.cleaned_data['expiry'],
            cvv=card_form.cleaned_data['cvv'],
        )
        if not charge_result['ok']:
            # Declined: no order, no money — the customer retries at step 3.
            messages.error(request, charge_result['message'])
            state['step'] = 3
            _save_state(request, state)
            return redirect('orders:checkout')

    try:
        with transaction.atomic():
            order = Order.place(
                user=request.user,
                items=items,
                address=address,
                payment_method=payment_method,
                coupon=coupon,
                notes=notes,
            )
            if payment_method == 'card':
                # Gateway confirmed — flip the payment to PAID with the
                # transaction id (COD stays Pending until delivery).
                order.payment.mark_paid(charge_result['transaction_id'])
    except ValueError as error:
        # Stock ran out (or a product was deactivated) between the review
        # and the click. Show the reason; the cart stays untouched.
        if payment_method == 'card':
            # Charged but no order could be created — refund at once.
            # A store must never keep money for goods it didn't ship.
            gateway_refund(charge_result.get('transaction_id', ''))
        messages.error(request, str(error))
        state['step'] = 4
        _save_state(request, state)
        return redirect('orders:checkout')

    # Success: wipe the cart and the checkout progress.
    request.session.pop(CART_SESSION_KEY, None)
    _reset_state(request)
    messages.success(request, f"Order {order.order_number} placed — thank you!")
    return redirect('orders:order_complete', order.order_number)


# ---------------------------------------------------------------------------
# step 5 — the "order complete" screen
# ---------------------------------------------------------------------------
@login_required
def order_complete(request, order_number):
    """GET /checkout/complete/<order_number>/ — the thank-you screen."""
    order = get_object_or_404(
        Order, order_number=order_number, user=request.user
    )
    items = order.items.select_related('product')
    try:
        payment = order.payment
    except Payment.DoesNotExist:  # pragma: no cover — defensive
        payment = None

    context = {
        'order': order,
        'items': items,
        'payment': payment,
        'steps': STEP_LABELS,
        'step': 5,
    }
    return render(request, 'orders/complete.html', context)


# ---------------------------------------------------------------------------
# PHASE 14 — coupon apply / remove
# ---------------------------------------------------------------------------
@login_required
@require_POST
def checkout_coupon(request):
    """
    POST /checkout/coupon/ — apply or remove a coupon at checkout.

    * with 'code' in the POST  -> look it up, validate it against the
      CURRENT cart subtotal (server-side), store only the code.
    * without 'code'           -> remove the applied coupon.

    The coupon itself is always re-read from the database (the session
    holds just the code), and Order.place re-validates it a final time
    inside the order transaction.
    """
    state = _checkout_state(request)
    _lines, _totals, _meta, items = _available_items(request)

    if not items:
        messages.info(
            request, 'Your cart is empty — add something before applying a coupon.'
        )
        return redirect('cart:page')

    code = (request.POST.get('code') or '').strip()

    if not code:
        # ---- remove ------------------------------------------------------
        if state.get('coupon_code'):
            removed = state.pop('coupon_code')
            _save_state(request, state)
            messages.info(request, f"Coupon {removed} removed.")
        else:
            messages.info(request, 'No coupon is applied.')
        return redirect('orders:checkout')

    # ---- apply -----------------------------------------------------------
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if coupon is None:
        messages.error(request, f"'{code.upper()}' is not a valid coupon code.")
        return redirect('orders:checkout')

    subtotal = sum(
        (product.final_price * quantity for product, quantity in items),
        Decimal('0.00'),
    )
    is_valid, reason = coupon.validate_for_order(subtotal)
    if not is_valid:
        messages.error(request, f"Coupon {coupon.code}: {reason}")
        return redirect('orders:checkout')

    state['coupon_code'] = coupon.code
    _save_state(request, state)
    discount = coupon.calculate_discount(subtotal)
    messages.success(
        request, f"Coupon {coupon.code} applied — you save ₹{discount}."
    )
    return redirect('orders:checkout')


# ---------------------------------------------------------------------------
# PHASE 12 — order history, detail + timeline, customer cancel
# ---------------------------------------------------------------------------
# The forward path of an order (cancelled is a side-exit, not a step):
STATUS_FLOW = [
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PROCESSING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
]


def _status_timeline(order):
    """
    Build the timeline data for the detail page: a list of
    {'value', 'label', 'state'} where state is one of
    'done' (already passed), 'current' (we are here) or 'todo'.
    Only meaningful for non-cancelled orders — the template shows a
    cancelled banner instead for those.
    """
    current = STATUS_FLOW.index(Order.Status(order.order_status))
    timeline = []
    for i, status in enumerate(STATUS_FLOW):
        if i < current:
            state = 'done'
        elif i == current:
            state = 'current'
        else:
            state = 'todo'
        timeline.append({'value': status.value, 'label': status.label,
                         'state': state})
    return timeline


@login_required
def order_list(request):
    """GET /orders/ — the customer's order history (newest first)."""
    rows = []
    for order in request.user.orders.prefetch_related('items__product').all():
        items = list(order.items.all())        # served from the prefetch cache
        rows.append({
            'order': order,
            'thumbs': items[:4],               # up to 4 product thumbnails
            'extra': max(len(items) - 4, 0),   # "+N" badge for the rest
        })
    return render(request, 'orders/order_list.html', {'rows': rows})


@login_required
def order_detail(request, order_number):
    """GET /orders/<order_number>/ — full order view + status timeline."""
    order = get_object_or_404(
        Order, order_number=order_number, user=request.user
    )
    items = order.items.select_related('product')
    try:
        payment = order.payment
    except Payment.DoesNotExist:  # pragma: no cover — defensive
        payment = None

    context = {
        'order': order,
        'items': items,
        'payment': payment,
        'timeline': _status_timeline(order)
        if order.order_status != Order.Status.CANCELLED else [],
        'can_cancel': order.order_status == Order.Status.PENDING,
    }
    return render(request, 'orders/order_detail.html', context)


@login_required
@require_POST
def order_cancel(request, order_number):
    """
    POST /orders/<order_number>/cancel/ — customer cancels an order.

    Rules:
        * only orders that are still **Pending** can be cancelled —
          once the store starts processing, it's support's job;
        * cancelling returns the stock to the shelf (the order took it
          away at placement time);
        * a pending COD payment needs nothing; a (defensive) paid
          payment is marked refunded;
        * everything happens in one transaction.
    """
    order = get_object_or_404(
        Order, order_number=order_number, user=request.user
    )

    if order.order_status == Order.Status.CANCELLED:
        messages.warning(
            request, f"Order {order.order_number} is already cancelled."
        )
        return redirect('orders:order_detail', order.order_number)

    if order.order_status != Order.Status.PENDING:
        messages.error(
            request,
            'Orders can only be cancelled while they are still Pending. '
            'Contact support for anything further along.',
        )
        return redirect('orders:order_detail', order.order_number)

    with transaction.atomic():
        # Put the goods back on the shelf.
        for item in order.items.select_related('product'):
            Product.objects.filter(pk=item.product.pk).update(
                stock=F('stock') + item.quantity
            )
        order.order_status = Order.Status.CANCELLED
        order.save(update_fields=['order_status', 'updated_at'])

        payment = getattr(order, 'payment', None)
        if payment is not None and payment.status == Payment.Status.PAID:
            payment.mark_refunded()

    messages.success(
        request,
        f"Order {order.order_number} has been cancelled — "
        'the stock has been returned.',
    )
    return redirect('orders:order_detail', order.order_number)
