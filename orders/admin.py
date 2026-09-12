"""
orders app — admin panel configuration.

The orders page is where a store manager does their daily work:
confirm, ship, deliver (collect COD), cancel + refund — all via
one-click actions, with the order items visible inline (read-only,
because an order is a frozen receipt).
"""

import secrets

from django.contrib import admin

from payments.models import Payment

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """
    The product lines of the order, shown under the order.
    Read-only: order lines must never be edited after purchase.
    """

    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'quantity', 'unit_price', 'subtotal')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'customer', 'item_count', 'grand_total',
        'order_status', 'payment_status', 'created_at',
    )
    list_display_links = ('order_number',)
    list_filter = ('order_status', 'payment_status', 'created_at')
    date_hierarchy = 'created_at'   # quick filter: today / this month / this year
    search_fields = (
        'order_number', 'user__username', 'billing_name',
        'billing_city', 'items__product__name',
    )
    readonly_fields = (
        'order_number', 'user',
        'billing_name', 'billing_phone', 'billing_address_1', 'billing_address_2',
        'billing_city', 'billing_state', 'billing_pincode', 'billing_country',
        'notes',
        'subtotal', 'discount_amount', 'shipping_charge', 'tax_amount',
        'grand_total',
        'coupon',
        'created_at', 'updated_at',
    )
    actions = (
        'mark_confirmed', 'mark_processing', 'mark_shipped',
        'mark_delivered', 'cancel_order',
    )

    # Orders are ONLY created through the website checkout.
    # Blocking "Add order" here prevents someone hand-crafting a fake
    # receipt in the admin (stock would never be reduced for it).
    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        # Prefetch items once per list page (performance, same idea as
        # select_related in the product admin).
        return super().get_queryset(request).prefetch_related('items')

    # ------------------------- list view helpers --------------------------
    @admin.display(description='Customer')
    def customer(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description='Items')
    def item_count(self, obj):
        return obj.total_items

    # ------------------------- status actions -----------------------------
    @admin.action(description='Mark selected orders as CONFIRMED')
    def mark_confirmed(self, request, queryset):
        n = queryset.update(order_status=Order.Status.CONFIRMED)
        self.message_user(request, f'{n} order(s) marked as Confirmed.')

    @admin.action(description='Mark selected orders as PROCESSING')
    def mark_processing(self, request, queryset):
        n = queryset.update(order_status=Order.Status.PROCESSING)
        self.message_user(request, f'{n} order(s) marked as Processing.')

    @admin.action(description='Mark selected orders as SHIPPED')
    def mark_shipped(self, request, queryset):
        n = queryset.update(order_status=Order.Status.SHIPPED)
        self.message_user(request, f'{n} order(s) marked as Shipped.')

    @admin.action(description='Mark selected orders as DELIVERED (collects COD)')
    def mark_delivered(self, request, queryset):
        """
        Delivering an order also means the courier collected the cash,
        so COD payments are marked as paid at the same time.
        """
        count = 0
        for order in queryset:
            order.order_status = Order.Status.DELIVERED
            order.save(update_fields=['order_status', 'updated_at'])
            if (
                order.payment.method == Payment.Method.COD
                and order.payment.status == Payment.Status.PENDING
            ):
                order.payment.mark_paid(transaction_id='COD-COLLECTED')
            count += 1
        self.message_user(request, f'{count} order(s) marked as Delivered.')

    @admin.action(description='CANCEL selected orders (refunds paid payments)')
    def cancel_order(self, request, queryset):
        """
        Cancelling also refunds any payment that was already made,
        and refuses to cancel delivered orders (goods are gone).
        """
        cancelled = 0
        skipped = 0
        for order in queryset:
            if order.order_status in (Order.Status.DELIVERED, Order.Status.CANCELLED):
                skipped += 1
                continue
            order.order_status = Order.Status.CANCELLED
            order.save(update_fields=['order_status', 'updated_at'])
            if order.payment.status == Payment.Status.PAID:
                order.payment.mark_refunded()
            cancelled += 1
        message = f'{cancelled} order(s) cancelled.'
        if skipped:
            message += f' {skipped} skipped (already delivered or cancelled).'
        self.message_user(request, message)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'quantity',
                    'unit_price', 'subtotal', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('order__order_number', 'product__name')
    readonly_fields = ('order', 'product', 'quantity', 'unit_price',
                       'subtotal', 'created_at')

    def has_add_permission(self, request):
        return False   # order items are created with their order

    @admin.display(description='Order')
    def order(self, obj):
        return obj.order.order_number
