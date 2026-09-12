"""
payments app — admin panel configuration.

Lets a store manager see every payment and, when needed:
  * mark a payment as paid manually (e.g. bank transfer, phone-confirmed COD)
  * refund a paid payment (e.g. after a customer dispute)
"""

import secrets

from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order_number', 'amount', 'method', 'status',
        'transaction_id', 'paid_at', 'created_at',
    )
    list_display_links = ('id',)
    list_filter = ('method', 'status', 'created_at')
    date_hierarchy = 'created_at'
    search_fields = ('transaction_id', 'order__order_number',
                     'order__user__username')
    readonly_fields = ('order', 'amount', 'created_at', 'updated_at')
    actions = ('mark_as_paid', 'refund_selected')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'order__user')

    @admin.display(description='Order')
    def order_number(self, obj):
        return obj.order.order_number

    # ------------------------- actions ------------------------------------
    @admin.action(description='Mark selected payments as PAID (manual)')
    def mark_as_paid(self, request, queryset):
        count = 0
        for payment in queryset:
            if payment.status == Payment.Status.PENDING:
                payment.mark_paid(
                    transaction_id='MANUAL-' + secrets.token_hex(3).upper()
                )
                count += 1
        self.message_user(request, f'{count} payment(s) marked as Paid.')

    @admin.action(description='REFUND selected payments')
    def refund_selected(self, request, queryset):
        count = 0
        for payment in queryset:
            if payment.status == Payment.Status.PAID:
                payment.mark_refunded()
                count += 1
        self.message_user(request, f'{count} payment(s) refunded.')
