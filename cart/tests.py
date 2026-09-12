"""
cart app — tests (PHASE 19).

The cart is session-based (no DB model), so these tests exercise the
HTTP endpoints and then inspect the session + the money math.
"""

from decimal import Decimal

from cart.calculations import calculate_totals
from cart.constants import CART_SESSION_KEY
from core.testing import StoreTestCase


class CartSessionTest(StoreTestCase):
    def _cart(self):
        return self.client.session.get(CART_SESSION_KEY) or {}

    def test_add_updates_and_removes(self):
        self.client.post(f'/cart/add/{self.product_a.pk}/', {'quantity': 2})
        self.assertEqual(self._cart().get(str(self.product_a.pk)), 2)

        self.client.post(f'/cart/update/{self.product_a.pk}/', {'quantity': 1})
        self.assertEqual(self._cart().get(str(self.product_a.pk)), 1)

        self.client.post(f'/cart/remove/{self.product_a.pk}/')
        self.assertNotIn(str(self.product_a.pk), self._cart())

        self.client.post(f'/cart/add/{self.product_b.pk}/', {'quantity': 1})
        self.client.post('/cart/clear/')
        self.assertEqual(self._cart(), {})

    def test_quantity_above_stock_is_rejected(self):
        # product_b has stock 5 — asking for 99 is refused outright
        # (the cart never promises more than exists).
        self.client.post(f'/cart/add/{self.product_b.pk}/', {'quantity': 99})
        self.assertNotIn(str(self.product_b.pk), self._cart())
        html = self.client.get('/cart/').content.decode()
        self.assertIn('5 unit', html)

    def test_out_of_stock_product_rejected(self):
        self.product_b.stock = 0
        self.product_b.save(update_fields=['stock'])
        response = self.client.post(
            f'/cart/add/{self.product_b.pk}/', {'quantity': 1})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(str(self.product_b.pk), self._cart())
        html = self.client.get('/cart/').content.decode()
        self.assertIn('out of stock', html.lower())


class CartTotalsTest(StoreTestCase):
    def test_free_shipping_above_threshold(self):
        # 2 × ₹899 + 1 × ₹399 = ₹2197 ≥ ₹1000 → free shipping.
        totals = calculate_totals([
            (self.product_a, 2), (self.product_b, 1),
        ])
        self.assertEqual(totals['subtotal'], Decimal('2197.00'))
        self.assertEqual(totals['shipping'], Decimal('0.00'))
        self.assertEqual(totals['tax'], Decimal('109.85'))
        self.assertEqual(totals['grand_total'], Decimal('2306.85'))

    def test_flat_shipping_below_threshold(self):
        # 1 × ₹399 → shipping ₹49, tax 5% of 399 = 19.95.
        totals = calculate_totals([(self.product_b, 1)])
        self.assertEqual(totals['subtotal'], Decimal('399.00'))
        self.assertEqual(totals['shipping'], Decimal('49.00'))
        self.assertEqual(totals['tax'], Decimal('19.95'))
        self.assertEqual(totals['grand_total'], Decimal('467.95'))

    def test_discount_price_used_in_subtotal(self):
        self.product_a.discount_price = Decimal('500.00')
        self.product_a.save(update_fields=['discount_price'])
        totals = calculate_totals([(self.product_a, 2)])
        # 2 × 500 = 1000 → right at the free-shipping threshold.
        self.assertEqual(totals['subtotal'], Decimal('1000.00'))
        self.assertEqual(totals['shipping'], Decimal('0.00'))

    def test_cart_page_renders_the_totals(self):
        self.client.post(f'/cart/add/{self.product_a.pk}/', {'quantity': 2})
        self.client.post(f'/cart/add/{self.product_b.pk}/', {'quantity': 1})
        html = self.client.get('/cart/').content.decode()
        for expected in ('2197.00', '109.85', '2306.85'):
            self.assertIn(expected, html)
