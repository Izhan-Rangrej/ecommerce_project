"""
orders app — tests (PHASE 19).

The heart of the store: the 5-step checkout flow, order placement
(stock + money math + payment record + no double submits), order
history/detail, cancellation rules, and card-payment behaviour.
"""

from decimal import Decimal

from cart.constants import CART_SESSION_KEY
from core.testing import (StoreTestCase, add_to_cart, make_product,
                          run_checkout_steps)
from orders.models import Order
from payments.models import Payment

OK_CARD = {'card_number': '4242 4242 4242 4242', 'name': 'Card Holder',
           'expiry': '12/28', 'cvv': '123'}
DECLINED_CARD = {'card_number': '4000 0000 0000 0002', 'name': 'Card Holder',
                 'expiry': '12/28', 'cvv': '123'}


class CheckoutFlowTest(StoreTestCase):
    def test_checkout_requires_login(self):
        response = self.client.get('/checkout/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_checkout_with_empty_cart_goes_to_cart(self):
        self.client.login(username='customer', password=self.password)
        response = self.client.post('/checkout/place-order/', {'notes': ''})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/cart/')
        self.assertFalse(Order.objects.exists())

    def test_cod_flow_places_order_with_correct_money_and_stock(self):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_a, 2)
        add_to_cart(self.client, self.product_b, 1)

        response = run_checkout_steps(self.client, self.address, 'cod')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/checkout/complete/ORD-'))

        order = Order.objects.get(user=self.customer)
        # --- items
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            sorted(i.quantity for i in order.items.all()), [1, 2])
        # --- frozen money: 2×899 + 1×399 = 2197, free shipping, 5% tax
        self.assertEqual(order.subtotal, Decimal('2197.00'))
        self.assertEqual(order.shipping_charge, Decimal('0.00'))
        self.assertEqual(order.tax_amount, Decimal('109.85'))
        self.assertEqual(order.grand_total, Decimal('2306.85'))
        # --- stock was decremented
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_a.stock, 8)
        self.assertEqual(self.product_b.stock, 4)
        # --- cart cleared (a double-submit can't place a second order)
        self.assertEqual(
            self.client.session.get(CART_SESSION_KEY) or {}, {})
        # --- payment record
        self.assertEqual(order.payment.method, Payment.Method.COD)
        self.assertEqual(order.payment.status, Payment.Status.PENDING)
        self.assertEqual(order.payment_status, order.PaymentStatus.PENDING)
        # --- status + numbering
        self.assertEqual(order.order_status, Order.Status.PENDING)
        self.assertTrue(order.order_number.startswith('ORD-'))

    def test_low_subtotal_pays_flat_shipping(self):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_b, 1)
        run_checkout_steps(self.client, self.address, 'cod')
        order = Order.objects.get(user=self.customer)
        self.assertEqual(order.subtotal, Decimal('399.00'))
        self.assertEqual(order.shipping_charge, Decimal('49.00'))
        self.assertEqual(order.tax_amount, Decimal('19.95'))
        self.assertEqual(order.grand_total, Decimal('467.95'))

    def test_out_of_stock_line_blocks_the_order(self):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_b, 1)
        self.product_b.stock = 0     # stock vanishes during checkout
        self.product_b.save(update_fields=['stock'])

        run_checkout_steps(self.client, self.address, 'cod')

        self.assertFalse(Order.objects.exists())
        cart = self.client.session.get(CART_SESSION_KEY) or {}
        self.assertIn(str(self.product_b.pk), cart)   # cart kept for fixing

    def test_double_submit_places_only_one_order(self):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_a, 1)
        run_checkout_steps(self.client, self.address, 'cod')
        # The cart is empty now — a repeat POST must not create order #2.
        self.client.post('/checkout/place-order/', {'notes': ''})
        self.assertEqual(Order.objects.count(), 1)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 9)     # decremented once


class CardPaymentTest(StoreTestCase):
    def _to_payment_step(self):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_a, 1)
        self.client.post('/checkout/address/', {'address_id': self.address.pk})
        self.client.post('/checkout/continue/', {'delivery': 'standard'})

    def test_valid_card_pays_and_places_order(self):
        self._to_payment_step()
        self.client.post('/checkout/continue/',
                         {'payment': 'card', **OK_CARD})
        response = self.client.post('/checkout/place-order/', {'notes': ''})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/checkout/complete/ORD-'))
        order = Order.objects.get(user=self.customer)
        payment = order.payment
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.amount, order.grand_total)
        self.assertTrue(payment.transaction_id.startswith('pay_'))

    def test_declined_card_blocks_order_and_keeps_cart(self):
        self._to_payment_step()
        # The form sees a perfectly valid 16-digit card; it is the
        # GATEWAY that declines this magic number.
        self.client.post('/checkout/continue/',
                         {'payment': 'card', **DECLINED_CARD})
        self.client.post('/checkout/place-order/', {'notes': ''})
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        cart = self.client.session.get(CART_SESSION_KEY) or {}
        self.assertIn(str(self.product_a.pk), cart)
        html = self.client.get('/checkout/').content.decode()
        self.assertIn('declined', html.lower())


class OrderManagementTest(StoreTestCase):
    def _place_one(self, product):
        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, product, 1)
        run_checkout_steps(self.client, self.address, 'cod')
        return Order.objects.get(user=self.customer)

    def test_order_list_and_detail(self):
        order = self._place_one(self.product_a)
        html = self.client.get('/orders/').content.decode()
        self.assertIn(order.order_number, html)

        html = self.client.get(
            f'/orders/{order.order_number}/').content.decode()
        self.assertIn('Alpha Widget', html)
        self.assertIn(str(order.grand_total), html)

    def test_cannot_open_someones_else_order(self):
        order = self._place_one(self.product_a)
        from core.testing import make_user
        stranger = make_user('stranger', password='OtherPass!99')
        self.client.force_login(stranger)
        self.assertEqual(
            self.client.get(f'/orders/{order.order_number}/').status_code,
            404)

    def test_cancel_pending_order_restores_stock(self):
        order = self._place_one(self.product_a)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 9)

        response = self.client.post(f'/orders/{order.order_number}/cancel/')
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.product_a.refresh_from_db()
        self.assertEqual(order.order_status, Order.Status.CANCELLED)
        self.assertEqual(self.product_a.stock, 10)      # back on the shelf

    def test_cannot_cancel_after_processing_started(self):
        order = self._place_one(self.product_a)
        order.order_status = Order.Status.SHIPPED
        order.save(update_fields=['order_status'])

        self.client.post(f'/orders/{order.order_number}/cancel/')
        order.refresh_from_db()
        self.assertEqual(order.order_status, Order.Status.SHIPPED)

    def test_cancelling_twice_is_harmless(self):
        order = self._place_one(self.product_a)
        self.client.post(f'/orders/{order.order_number}/cancel/')
        response = self.client.post(f'/orders/{order.order_number}/cancel/')
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 10)      # restored once, not twice


class CouponAtCheckoutTest(StoreTestCase):
    def test_percentage_coupon_discount_is_frozen_on_the_order(self):
        from products.models import Coupon
        coupon = Coupon.objects.create(
            code='TESTTEN', discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10.00'),
            minimum_order_amount=Decimal('1000.00'))

        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_a, 2)     # subtotal 1798
        self.client.post('/checkout/address/', {'address_id': self.address.pk})
        self.client.post('/checkout/coupon/', {'code': 'testten'})   # lowercase ok
        self.client.post('/checkout/continue/', {'delivery': 'standard'})
        self.client.post('/checkout/continue/', {'payment': 'cod'})
        response = self.client.post('/checkout/place-order/', {'notes': ''})

        order = Order.objects.get(user=self.customer)
        # 10% of 1798 = 179.80 → after 1618.20 → shipping 0, tax 80.91
        self.assertEqual(order.coupon, coupon)
        self.assertEqual(order.discount_amount, Decimal('179.80'))
        self.assertEqual(order.subtotal, Decimal('1798.00'))
        self.assertEqual(order.tax_amount, Decimal('80.91'))
        self.assertEqual(order.grand_total, Decimal('1699.11'))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertTrue(response['Location'].startswith('/checkout/complete/'))

    def test_deactivated_coupon_is_rejected_at_apply(self):
        from products.models import Coupon
        Coupon.objects.create(
            code='DEADCODE', discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10.00'), active=False)

        self.client.login(username='customer', password=self.password)
        add_to_cart(self.client, self.product_a, 2)
        self.client.post('/checkout/address/', {'address_id': self.address.pk})
        self.client.post('/checkout/coupon/', {'code': 'DEADCODE'})

        # Rejected at apply time: the code is never stored in the session.
        self.assertNotIn('coupon_code', self.client.session.get('_checkout', {}))

        # Checkout still completes — the order is placed WITHOUT the
        # discount, and the coupon stays unused.
        self.client.post('/checkout/continue/', {'delivery': 'standard'})
        self.client.post('/checkout/continue/', {'payment': 'cod'})
        self.client.post('/checkout/place-order/', {'notes': ''})

        order = Order.objects.get()
        self.assertEqual(order.coupon, None)
        self.assertEqual(order.discount_amount, Decimal('0.00'))
        coupon = Coupon.objects.get(code='DEADCODE')
        self.assertEqual(coupon.used_count, 0)
