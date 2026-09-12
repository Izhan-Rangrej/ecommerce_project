"""
orders app — models.

    Order     -> one customer purchase: address snapshot, money totals,
                 order status and payment status
    OrderItem -> one line of the order: product, quantity, price at purchase

The crown jewel of this file is Order.place() — the single, transactional
function that turns a basket of products into an order. Everything about
"placing an order" (stock check, stock reduction, coupon usage, payment
record) happens there, so no other code can do it half-way.
"""

import secrets
from datetime import datetime

from decimal import Decimal

from django.conf import settings
from django.db import connection, models, transaction
from django.db.models import F

from products.models import Coupon, Product


class Order(models.Model):
    """A customer's completed purchase (their receipt)."""

    # ---------------------- status constants ------------------------------
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PROCESSING = 'processing', 'Processing'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders',
        help_text="The customer who placed this order.",
    )
    order_number = models.CharField(
        max_length=30, unique=True, blank=True,
        help_text="Human-friendly number, e.g. ORD-20260912-8F3A. Auto-generated.",
    )

    # ------------------------------------------------------------------
    # SHIPPING ADDRESS — stored as a SNAPSHOT, not a foreign key.
    # Why? If the customer later edits or deletes their saved address,
    # their order history must not change. These frozen copies are what
    # was actually shipped to.
    # ------------------------------------------------------------------
    billing_name = models.CharField(max_length=150)
    billing_phone = models.CharField(max_length=15)
    billing_address_1 = models.CharField(max_length=200)
    billing_address_2 = models.CharField(max_length=200, blank=True)
    billing_city = models.CharField(max_length=100)
    billing_state = models.CharField(max_length=100)
    billing_pincode = models.CharField(max_length=10)
    billing_country = models.CharField(max_length=100)
    notes = models.TextField(blank=True, help_text="Extra instructions from the customer.")

    # ------------------------------------------------------------------
    # MONEY — all amounts are SNAPSHOT values frozen at purchase time.
    # (If the product price changes next week, old orders keep their price.)
    # ------------------------------------------------------------------
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)

    # Which coupon was used (SET_NULL: a deleted coupon doesn't destroy orders)
    coupon = models.ForeignKey(
        Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders'
    )

    # ---------------------- statuses -----------------------------------
    order_status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_status']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        return self.order_number or f"Order #{self.pk}"

    # ---------------------- helpers -------------------------------------
    @property
    def total_items(self):
        """Total quantity of goods in this order (e.g. 2 chairs + 1 lamp = 3)."""
        return sum(item.quantity for item in self.items.all())

    def save(self, *args, **kwargs):
        # Auto-generate a friendly, unique order number on first save.
        if self._state.adding and not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_order_number():
        """Build 'ORD-YYYYMMDD-XXXX' and retry if (extremely rare) it collides."""
        stamp = datetime.now().strftime('%Y%m%d')
        while True:
            candidate = f'ORD-{stamp}-{secrets.token_hex(2).upper()}'
            if not Order.objects.filter(order_number=candidate).exists():
                return candidate

    # ------------------------------------------------------------------
    # THE ORDER PLACEMENT FACTORY
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def place(cls, user, items, address, payment_method='cod', coupon=None, notes=''):
        """
        Create an Order from a basket, in ONE database transaction.

        :param user:           the logged-in customer
        :param items:          iterable of (Product, quantity) pairs
        :param address:        a customers.models.Address instance to ship to
        :param payment_method: 'cod' or 'card' (see payments.models.Payment)
        :param coupon:         a validated Coupon instance, or None
        :param notes:          extra instructions from the customer

        What happens (all-or-nothing — see @transaction.atomic):
            1. Lock the product rows so two people can't both grab the
               last unit of stock (race condition).
            2. Validate stock levels and the coupon.
            3. Create the Order (with frozen totals + address snapshot).
            4. Create an OrderItem per product (with the price at purchase).
            5. Reduce product stock.
            6. Record the coupon usage.
            7. Create the Payment record.

        :raises ValueError: if the basket is empty, stock is insufficient,
                            a product disappeared, or the coupon is invalid.
                            The view shows this message to the customer.
        """
        from cart.calculations import calculate_totals

        items = list(items)
        if not items:
            raise ValueError('Your cart is empty.')

        # ---- 1. Lock the product rows for this transaction --------------
        product_ids = [product.pk for product, _ in items]
        products_qs = Product.objects.filter(pk__in=product_ids)
        # PostgreSQL: SELECT ... FOR UPDATE (real row locking).
        # SQLite locks the whole database on writes, so it doesn't support
        # this — the guard keeps the code identical on both engines.
        if connection.features.has_select_for_update:
            products_qs = products_qs.select_for_update()
        products_in_db = {p.pk: p for p in products_qs}

        # ---- 2. Validate everything BEFORE changing anything ------------
        for product, quantity in items:
            db_product = products_in_db.get(product.pk)
            if db_product is None or not db_product.active:
                raise ValueError(f"'{product.name}' is no longer available.")
            if quantity < 1:
                raise ValueError(f'Invalid quantity for {product.name}.')
            if db_product.stock < quantity:
                raise ValueError(
                    f"Sorry, only {db_product.stock} unit(s) of "
                    f"'{product.name}' left in stock."
                )

        # Re-validate the coupon against the FINAL subtotal (server-side!).
        # calculate_totals() does this, but double-check here so an invalid
        # coupon can never silently reduce the price.
        if coupon is not None:
            # A quick pre-check on the raw subtotal is enough; the exact
            # validation happens inside calculate_totals with the same code
            # the cart page uses.
            from decimal import Decimal as _D
            raw_subtotal = sum(
                (products_in_db[p.pk].final_price * q for p, q in items), _D('0.00')
            )
            is_valid, reason = coupon.validate_for_order(raw_subtotal)
            if not is_valid:
                raise ValueError(f"Coupon {coupon.code}: {reason}")

        # ---- 3. Money — computed by the SAME function the cart uses ------
        totals = calculate_totals(
            [(products_in_db[p.pk], q) for p, q in items], coupon=coupon
        )

        # ---- 4. Create the order (address is snapshotted) ----------------
        order = cls(
            user=user,
            billing_name=address.full_name,
            billing_phone=address.phone,
            billing_address_1=address.address_line_1,
            billing_address_2=address.address_line_2,
            billing_city=address.city,
            billing_state=address.state,
            billing_pincode=address.pincode,
            billing_country=address.country,
            notes=notes,
            subtotal=totals['subtotal'],
            discount_amount=totals['discount'],
            shipping_charge=totals['shipping'],
            tax_amount=totals['tax'],
            grand_total=totals['grand_total'],
            coupon=coupon,
        )
        order.save()

        # ---- 5. Order items + stock reduction ----------------------------
        for product, quantity in items:
            db_product = products_in_db[product.pk]
            unit_price = db_product.final_price
            OrderItem.objects.create(
                order=order,
                product=db_product,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=(unit_price * quantity).quantize(Decimal('0.01')),
            )
            # Guarded decrement: "stock >= quantity" makes even a race
            # impossible at the database level (0 rows update => no change).
            updated = Product.objects.filter(
                pk=db_product.pk, stock__gte=quantity
            ).update(stock=F('stock') - quantity)
            if not updated:  # pragma: no cover — defensive, should not happen
                raise ValueError(f"Stock changed for '{db_product.name}'. Try again.")

        # ---- 6. Coupon bookkeeping ---------------------------------------
        if coupon is not None:
            coupon.register_usage()

        # ---- 7. Payment record -------------------------------------------
        # Imported here (not at the top of the file) because payments.models
        # imports Order from this file — importing it at module level would
        # create a circular import and Django would crash on startup.
        from payments.models import Payment

        payment = Payment.objects.create(
            order=order,
            method=Payment.method_value(payment_method),
            amount=order.grand_total,
        )
        # COD is "paid" later, at delivery. A successful test-card payment
        # calls payment.mark_paid() from the payment view (PHASE 13).

        return order


class OrderItem(models.Model):
    """
    One line of an order: which product, how many, at what price.

    unit_price is a SNAPSHOT of the product's final price at purchase time,
    so old orders stay correct even if the product price changes later.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='order_items',
        help_text="PROTECT: a product that was ever sold can't be deleted — "
                  "order history must be preserved.",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.quantity} x {self.product}"

    def save(self, *args, **kwargs):
        # Keep the line total consistent automatically.
        self.subtotal = (self.unit_price * self.quantity).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
