"""
core/testing.py — PHASE 19: shared fixtures for the whole test suite.

Why a shared module? Every test file needs the same small realistic
world (a few products, a customer, an address). Defining it ONCE here
means the ~45 tests stay short, consistent and fast, and a change to
the fixtures (e.g. a new required model field) is made in one place.

Run everything with:
    python manage.py test
"""

import io
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils.text import slugify
from PIL import Image

from core import ratelimit
from customers.models import Address
from products.models import Brand, Category, Product


# ---------------------------------------------------------------------------
# Factories (small on purpose — tests read better with them)
# ---------------------------------------------------------------------------
def make_image(name='test.png', color=(80, 120, 200)):
    """A tiny but valid PNG so ImageField uploads work in tests."""
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), color).save(buf, 'PNG')
    return ContentFile(buf.getvalue(), name=name)


def make_category(name, slug=None, active=True):
    return Category.objects.create(
        name=name, slug=slug or slugify(name),
        description=f'{name} products', active=active,
    )


def make_brand(name, slug=None):
    return Brand.objects.create(name=name, slug=slug or slugify(name))


def make_product(name, price='1000.00', stock=10, category=None,
                 brand=None, discount=None, active=True, featured=False,
                 description=None):
    """Create a fully-valid Product (image included)."""
    slug = slugify(name)
    product = Product(
        name=name,
        slug=slug,
        short_description=f'{name} short description',
        description=description or f'{name} full description text.',
        category=category or make_category('Default Cat'),
        brand=brand,
        price=Decimal(price),
        discount_price=Decimal(discount) if discount else None,
        stock=stock,
        sku=f'SKU-{slug[:24].upper()}',
        featured=featured,
        active=active,
    )
    product.image.save(f'{slug}.png', make_image(f'{slug}.png'), save=False)
    product.save()
    return product


def make_user(username, password='TestPass!99', email=None):
    return User.objects.create_user(
        username, email or f'{username}@test.example', password)


def make_address(user, **overrides):
    defaults = {
        'label': 'Home',
        'full_name': user.get_full_name() or username_of(user),
        'phone': '9800001111',
        'address_line_1': '1 Test Street',
        'city': 'Testville',
        'state': 'Gujarat',
        'pincode': '380001',
        'country': 'India',
    }
    defaults.update(overrides)
    return Address.objects.create(user=user, **defaults)


def username_of(user):
    return user.username


# ---------------------------------------------------------------------------
# The checkout flow, as a helper (used by review + coupon + payment tests)
# ---------------------------------------------------------------------------
def add_to_cart(client, product, qty=1):
    """POST the classic add-to-cart form (same as the page does)."""
    return client.post(f'/cart/add/{product.pk}/', {'quantity': qty})


def run_checkout_steps(client, address, payment='cod', card=None):
    """
    Drive the 5-step checkout up to "place order" and place the order.
    `card` = {'card_number', 'name', 'expiry', 'cvv'} for card payment.
    Returns the place-order response.
    """
    client.post('/checkout/address/', {'address_id': address.pk})
    client.post('/checkout/continue/', {'delivery': 'standard'})
    if payment == 'card':
        data = {'payment': 'card'}
        data.update(card)
    else:
        data = {'payment': 'cod'}
    client.post('/checkout/continue/', data)
    return client.post('/checkout/place-order/', {'notes': ''})


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------
class StoreTestCase(TestCase):
    """
    Every test in the project inherits from this. It gives each test:

      * two categories, two brands, three products:
          product_a  Alpha Widget   ₹899   stock 10   (electronics/alpha)
          product_b  Beta Gadget    ₹399   stock 5    (electronics/beta)
          product_c  Gamma Runner   ₹1499  stock 3    (sports/alpha)
      * a ready customer + address
      * a CLEAN rate limiter (in-memory buckets are shared across tests
        in one process — without this, one test's "abuse" would
        throttle the next test)

    Useful known totals (for math assertions):
      2 × product_a + 1 × product_b = 2197 → shipping 0 (≥ ₹1000),
      tax 109.85 → grand 2306.85
      1 × product_b = 399 → shipping 49, tax 19.95 → grand 467.95
    """

    def setUp(self):
        super().setUp()
        ratelimit.clear_buckets()

        self.cat_a = make_category('Electronics', 'test-electronics')
        self.cat_b = make_category('Sports', 'test-sports')
        self.brand_a = make_brand('Alpha Co', 'alpha-co')
        self.brand_b = make_brand('Beta Co', 'beta-co')

        self.product_a = make_product(
            'Alpha Widget', price='899.00', stock=10,
            category=self.cat_a, brand=self.brand_a)
        self.product_b = make_product(
            'Beta Gadget', price='399.00', stock=5,
            category=self.cat_a, brand=self.brand_b)
        self.product_c = make_product(
            'Gamma Runner', price='1499.00', stock=3,
            category=self.cat_b, brand=self.brand_a)

        self.customer = make_user('customer')
        self.password = 'TestPass!99'
        self.address = make_address(self.customer)
