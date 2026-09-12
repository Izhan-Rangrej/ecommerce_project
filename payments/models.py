"""
payments app — models.

    Payment -> one payment record per order

GATEWAY-READY ARCHITECTURE (PHASE 13 builds on this):
    * Cash on Delivery works today (customer pays the courier).
    * A built-in "test card" flow works today (simulated gateway).
    * Adding a REAL gateway (Razorpay / Stripe) later means only:
        1. create the Payment with status = pending
        2. verify the gateway's webhook / callback (server-side!)
        3. call payment.mark_paid()  or  payment.mark_failed()
    * Gateway API keys live in .env (PHASE 2) — never in this file.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone

from orders.models import Order


class Payment(models.Model):
    """One record per order — how it is/was paid."""

    class Method(models.TextChoices):
        COD = 'cod', 'Cash on Delivery'
        CARD = 'card', 'Card (test mode)'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    # One payment per order (and vice versa): a clean OneToOne relationship.
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name='payment'
    )
    method = models.CharField(
        max_length=10, choices=Method.choices, default=Method.COD
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(
        max_length=100, blank=True,
        help_text="Reference number from the gateway (e.g. 'pay_ABC123'). "
                  "For COD this stays empty until the courier marks it paid.",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"Payment {self.pk} — {self.get_method_display()} — "
            f"{self.get_status_display()} — {self.amount}"
        )

    # ---------------------- helpers -------------------------------------
    @classmethod
    def method_value(cls, method_str):
        """
        Map a plain string from the checkout form ('cod' / 'card') onto a
        valid Method choice. Raises ValueError for anything else, so an
        attacker can't put a nonsense value in the payment record.
        """
        try:
            return cls.Method(method_str)
        except ValueError:
            raise ValueError(f'Unknown payment method: {method_str!r}')

    def mark_paid(self, transaction_id=''):
        """Successful payment (gateway confirmed, or COD collected)."""
        self.status = self.Status.PAID
        self.transaction_id = transaction_id
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'transaction_id', 'paid_at', 'updated_at'])
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save(update_fields=['payment_status', 'updated_at'])

    def mark_failed(self):
        """Gateway rejected the payment."""
        self.status = self.Status.FAILED
        self.save(update_fields=['status', 'updated_at'])
        self.order.payment_status = Order.PaymentStatus.FAILED
        self.order.save(update_fields=['payment_status', 'updated_at'])

    def mark_refunded(self):
        """Money returned to the customer (admin action, e.g. cancelled order)."""
        self.status = self.Status.REFUNDED
        self.save(update_fields=['status', 'updated_at'])
        self.order.payment_status = Order.PaymentStatus.REFUNDED
        self.order.save(update_fields=['payment_status', 'updated_at'])
