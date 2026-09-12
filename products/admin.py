"""
products app — admin panel configuration.

Start the server and open http://127.0.0.1:8000/admin/ to see everything
in this file: search boxes, filters, sortable columns, photo thumbnails,
inline gallery editing and one-click actions.

Every @admin.register(SomeModel) line tells Django:
"use MY custom admin UI for this model".
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Brand, Category, Coupon, Product, ProductImage, Review


# ---------------------------------------------------------------------------
# CATEGORY
# ---------------------------------------------------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'product_count', 'image_thumb', 'active', 'created_at')
    list_display_links = ('name',)
    list_filter = ('active',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}   # slug fills itself from name
    readonly_fields = ('created_at',)

    @admin.display(description='Photo')
    def image_thumb(self, obj):
        """Small thumbnail in the list view (format_html escapes = XSS-safe)."""
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" width="48" height="48" '
                'style="object-fit: cover; border-radius: 6px;">',
                obj.image.url, obj.name,
            )
        return '—'


# ---------------------------------------------------------------------------
# BRAND
# ---------------------------------------------------------------------------
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    list_display_links = ('name',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at',)


# ---------------------------------------------------------------------------
# PRODUCT
# ---------------------------------------------------------------------------
class ProductImageInline(admin.TabularInline):
    """Extra gallery photos, edited directly on the product edit page."""

    model = ProductImage
    extra = 0   # start with no empty rows; click "Add" to add


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'product_thumb', 'name', 'category', 'brand',
        'final_price_display', 'stock', 'featured', 'active',
    )
    list_display_links = ('name',)
    # Editable straight from the list view (fast stock/flag updates):
    list_editable = ('stock', 'featured', 'active')
    list_filter = ('category', 'brand', 'featured', 'active', 'created_at')
    search_fields = ('name', 'sku', 'description', 'category__name', 'brand__name')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    inlines = (ProductImageInline,)
    date_hierarchy = 'created_at'   # month/day picker at the top of the list
    actions = ('make_featured', 'make_not_featured', 'activate', 'deactivate')

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'sku', 'category', 'brand'),
        }),
        ('Pricing & stock', {
            'fields': ('price', 'discount_price', 'stock'),
        }),
        ('Content', {
            'fields': ('short_description', 'description'),
        }),
        ('Media', {
            'fields': ('image',),
        }),
        ('Flags', {
            'fields': ('featured', 'active'),
        }),
        ('Timestamps (automatic)', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),   # hidden by default, click to expand
        }),
    )

    def get_queryset(self, request):
        # select_related = 2 queries total instead of 2 per row (performance!)
        return super().get_queryset(request).select_related('category', 'brand')

    # ------------------------- list view helpers --------------------------
    @admin.display(description='Photo')
    def product_thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" width="48" height="48" '
                'style="object-fit: cover; border-radius: 6px;">',
                obj.image.url, obj.name,
            )
        return '—'

    @admin.display(description='Price')
    def final_price_display(self, obj):
        """Shows crossed-out original price + sale price + % badge."""
        if obj.is_on_sale:
            return format_html(
                '<s>{}</s> <b>{}</b> '
                '<span style="color:#e11d48; font-weight:700">-{}%</span>',
                obj.price, obj.discount_price, obj.discount_percentage,
            )
        return obj.price

    # ------------------------- bulk actions --------------------------------
    @admin.action(description='Mark selected products as FEATURED')
    def make_featured(self, request, queryset):
        n = queryset.update(featured=True)
        self.message_user(request, f'{n} product(s) marked as featured.')

    @admin.action(description='Remove FEATURED flag from selection')
    def make_not_featured(self, request, queryset):
        n = queryset.update(featured=False)
        self.message_user(request, f'{n} product(s) no longer featured.')

    @admin.action(description='Activate selected products')
    def activate(self, request, queryset):
        n = queryset.update(active=True)
        self.message_user(request, f'{n} product(s) activated.')

    @admin.action(description='Deactivate selected products (hide from site)')
    def deactivate(self, request, queryset):
        n = queryset.update(active=False)
        self.message_user(request, f'{n} product(s) deactivated — hidden from the website.')


# ---------------------------------------------------------------------------
# REVIEW (with a 1-5 star filter)
# ---------------------------------------------------------------------------
class RatingFilter(admin.SimpleListFilter):
    """Adds a dropdown filter in the right sidebar: rating = 1 / 2 / 3 / 4 / 5."""

    title = 'rating'
    parameter_name = 'rating'

    def lookups(self, request, model_admin):
        return [(r, f'{r} star(s)') for r in range(1, 6)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(rating=int(self.value()))
        return queryset


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'stars', 'comment', 'created_at')
    list_filter = (RatingFilter, 'product__category')
    search_fields = ('product__name', 'user__username', 'comment')
    readonly_fields = ('created_at',)

    @admin.display(description='Rating')
    def stars(self, obj):
        return '★' * obj.rating + '☆' * (5 - obj.rating)

    @admin.display(description='Comment')
    def comment(self, obj):
        return (obj.comment or '')[:80] or '—'


# ---------------------------------------------------------------------------
# COUPON
# ---------------------------------------------------------------------------
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount_type', 'discount_value', 'minimum_order_amount',
        'maximum_discount', 'valid_to', 'usage_info', 'active',
    )
    list_display_links = ('code',)
    list_filter = ('discount_type', 'active')
    list_editable = ('active',)   # quick pause/resume a coupon
    search_fields = ('code',)
    readonly_fields = ('used_count', 'created_at')

    fieldsets = (
        (None, {
            'fields': ('code', 'discount_type', 'discount_value', 'active'),
        }),
        ('Limits', {
            'fields': ('minimum_order_amount', 'maximum_discount',
                       'usage_limit', 'used_count'),
        }),
        ('Validity window', {
            'fields': ('valid_from', 'valid_to'),
        }),
        ('Meta (automatic)', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Usage')
    def usage_info(self, obj):
        limit = str(obj.usage_limit) if obj.usage_limit is not None else '∞'
        return f'{obj.used_count} / {limit}'
