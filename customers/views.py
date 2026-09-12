"""
customers app — views.

PHASE 5  adds:  wishlist toggle (login required, AJAX + classic).
PHASE 8  adds:  register, profile, address management, password change.
PHASE 10 adds:  the wishlist page + "move to cart".
"""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordResetView
from django.db import IntegrityError
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.http import require_POST

from cart import services
from core.ratelimit import check_rate_limit
from core.utils import is_ajax, safe_next
from products.models import Product

from .forms import AddressForm, ProfileUpdateForm, RegisterForm
from .models import Address, WishlistItem


@login_required
@require_POST
def wishlist_toggle(request, product_id):
    """
    Add the product to the wishlist — or remove it if it's already there.

    * @login_required -> guests are sent to the login page with a
      ?next= link back to the product (Django handles this for us).
    * The unique (user, product) constraint on WishlistItem guarantees no
      duplicates even under concurrent requests (see the IntegrityError
      catch below).
    """
    product = get_object_or_404(Product, pk=product_id, active=True)

    try:
        item, created = WishlistItem.objects.get_or_create(
            user=request.user, product=product
        )
    except IntegrityError:
        # Two fast clicks raced; the database caught the duplicate.
        item = WishlistItem.objects.get(user=request.user, product=product)
        created = False

    if created:
        message = f"'{product.name}' added to your wishlist."
    else:
        item.delete()
        message = f"'{product.name}' removed from your wishlist."

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'in_wishlist': created,
            'message': message,
        })

    messages.success(request, message)
    return redirect(
        safe_next(request.POST.get('next'))
        or reverse('products:detail', args=[product.slug])
    )


# ===========================================================================
# PHASE 8 — AUTHENTICATION & ACCOUNTS
# ===========================================================================
def register(request):
    """
    /register/ — create a new account.

    * Guests only: a logged-in visitor is sent straight to their profile.
    * All validation is server-side (UserCreationForm's password validators,
      unique username, unique email — see customers/forms.py).
    * On success the customer is logged in immediately and taken to the
      profile page with a welcome message.
    """
    if request.user.is_authenticated:
        return redirect('customers:profile')

    if request.method == 'POST':
        # PHASE 18: max 3 registration attempts / IP / 5 minutes
        # (abuse guard — the form still validates everything below).
        allowed, wait_min = check_rate_limit(request, 'register', 3, 300)
        form = RegisterForm(request.POST)
        if not allowed:
            form.add_error(None, (
                f'Too many registration attempts from this address. '
                f'Please try again in about {wait_min} minute(s).'
            ))
        elif form.is_valid():
            user = form.save()
            login(request, user)          # start the session right away
            messages.success(
                request,
                f"Welcome to ShopSphere, {user.username}! "
                'Your account is ready.',
            )
            return redirect('customers:profile')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    """
    /account/ — the customer's profile: edit name, email, username,
    phone and date of birth, plus a quick overview (member since,
    saved addresses).
    """
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()                   # saves the User AND the profile
            messages.success(request, 'Your profile has been updated.')
            return redirect('customers:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)

    context = {
        'form': form,
        'address_count': request.user.addresses.count(),
        'wishlist_count': request.user.wishlist.count(),
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def change_password(request):
    """
    /account/change-password/

    Uses Django's PasswordChangeForm, which requires the CURRENT password
    and validates the new one with the standard rules. After the change we
    call login() again — Django invalidates the session hash when a
    password changes, so re-login keeps the customer signed in.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Your password has been changed.')
            return redirect('customers:profile')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'accounts/change_password.html', {'form': form})


# ---------------------------------------------------------------------------
# ADDRESSES
# ---------------------------------------------------------------------------
@login_required
def address_list(request):
    """/account/addresses/ — all of the customer's saved addresses."""
    addresses = request.user.addresses.all()
    return render(request, 'accounts/addresses/list.html',
                  {'addresses': addresses})


@login_required
def address_add(request):
    """/account/addresses/add/ — save a new shipping address."""
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()                # first address auto-becomes default
            messages.success(request, 'Address saved.')
            return redirect('customers:addresses')
    else:
        # Pre-fill the contact details from the profile to save typing.
        initial = {
            'full_name': request.user.get_full_name() or '',
            'phone': request.user.profile.phone,
        }
        form = AddressForm(initial=initial)

    return render(request, 'accounts/addresses/form.html',
                  {'form': form, 'page_title': 'Add a new address'})


@login_required
def address_edit(request, pk):
    """/account/addresses/<pk>/edit/ — edit one of the customer's addresses."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, 'Address updated.')
            return redirect('customers:addresses')
    else:
        form = AddressForm(instance=address)

    return render(request, 'accounts/addresses/form.html',
                  {'form': form, 'page_title': f"Edit address: {address.label or address.city}"})


@login_required
@require_POST
def address_set_default(request, pk):
    """/account/addresses/<pk>/default/ — make this the default address."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    Address.set_default(address)          # transactional: exactly one default
    messages.success(request, f'"{address.label or address.city}" is now your default address.')
    return redirect('customers:addresses')


@login_required
@require_POST
def address_delete(request, pk):
    """/account/addresses/<pk>/delete/ — remove a saved address."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()

    # If the default just disappeared, promote the most recent remaining
    # address so checkout always has a preselect.
    if was_default:
        remaining = request.user.addresses.first()
        if remaining:
            Address.set_default(remaining)

    messages.success(request, 'Address deleted.')
    return redirect('customers:addresses')


# ===========================================================================
# PHASE 10 — THE WISHLIST PAGE
# ===========================================================================
@login_required
def wishlist_page(request):
    """
    /wishlist/ — everything the customer has saved.

    Each row offers two actions:
        * Move to cart — adds 1 unit (server-side stock validation,
          shared with the public add-to-cart) and removes the row
        * Remove       — just drops it from the wishlist

    Products that were deactivated after being saved are still listed
    (marked "no longer available") so the customer can tidy up.
    """
    items = (
        WishlistItem.objects
        .filter(user=request.user)
        .select_related('product__category', 'product__brand')
        .annotate(
            avg_rating=Avg('product__reviews__rating'),
            review_count=Count('product__reviews'),
        )
        .order_by('-added_at')
    )
    context = {
        'items': items,
        'wishlist_count': items.count(),
    }
    return render(request, 'wishlist/wishlist.html', context)


def _wishlist_error(request, message):
    """Uniform error response for wishlist mutations (AJAX -> 400 JSON)."""
    if is_ajax(request):
        return JsonResponse({'ok': False, 'message': message}, status=400)
    messages.error(request, message)
    return redirect('customers:wishlist_page')


@login_required
@require_POST
def wishlist_remove(request, product_id):
    """/wishlist/remove/<product_id>/ — drop one item from the wishlist."""
    item = get_object_or_404(WishlistItem, product=product_id, user=request.user)
    name = item.product.name
    item.delete()

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'message': f"'{name}' removed from your wishlist.",
            'in_wishlist': False,
            'wishlist_count': request.user.wishlist.count(),
        })

    messages.info(request, f"'{name}' removed from your wishlist.")
    return redirect('customers:wishlist_page')


@login_required
@require_POST
def wishlist_move_to_cart(request, product_id):
    """
    /wishlist/move-to-cart/<product_id>/ — put one saved item in the cart.

    Adds ONE unit through the shared cart service (so the same stock
    rules apply as anywhere else), then removes the item from the
    wishlist. Rejected moves (out of stock / no stock left) keep the
    item in the wishlist.
    """
    item = get_object_or_404(WishlistItem, product=product_id, user=request.user)
    product = item.product

    if not product.active:
        return _wishlist_error(
            request, f"'{product.name}' is no longer available."
        )

    ok, message, cart_count = services.add_to_cart(request, product, 1)
    if not ok:
        # Out of stock / not enough left (the service says exactly why) —
        # the item stays in the wishlist.
        return _wishlist_error(request, message)

    item.delete()
    message = f"'{product.name}' moved to your cart."

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'message': message,
            'cart_count': cart_count,
            'in_wishlist': False,
            'wishlist_count': request.user.wishlist.count(),
        })

    messages.success(request, message)
    return redirect('customers:wishlist_page')


# ---------------------------------------------------------------------------
# PHASE 18 — rate-limited auth entry points
# ---------------------------------------------------------------------------
class ThrottledLoginView(LoginView):
    """
    Django's LoginView with a brute-force guard.

    A client IP may make at most 5 login attempts in any 5-minute
    window. After that the form shows "try again in N minutes" and
    further attempts are not processed until the window resets.
    """

    def post(self, request, *args, **kwargs):
        allowed, wait_min = check_rate_limit(request, 'login', 5, 300)
        if not allowed:
            form = self.get_form()
            form.add_error(None, (
                f'Too many login attempts from this address. '
                f'Please try again in about {wait_min} minute(s).'
            ))
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)


class ThrottledPasswordResetView(PasswordResetView):
    """
    Guards the "forgot password" form: at most 5 reset requests per
    client IP in any 10-minute window (stops reset-flooding).
    """

    def post(self, request, *args, **kwargs):
        allowed, wait_min = check_rate_limit(request, 'password_reset', 5, 600)
        if not allowed:
            form = self.get_form()
            form.add_error(None, (
                f'Too many password-reset requests from this address. '
                f'Please try again in about {wait_min} minute(s).'
            ))
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)
