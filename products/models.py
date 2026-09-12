"""
products app — models.

Everything about the catalog lives here:

    Category      -> groups of products (Electronics, Fashion, ...)
    Brand         -> who makes the product (Acme, Nordica, ...)
    Product       -> the thing we actually sell
    ProductImage  -> extra gallery photos for a product
    Review        -> a customer's 1–5 star rating + comment
    Coupon        -> a discount code applied at checkout

Relationships:
    Product  --> Category   (ForeignKey, CASCADE)
    Product  --> Brand      (ForeignKey, SET_NULL)
    ProductImage --> Product (ForeignKey, CASCADE)
    Review   --> Product + User (unique pair: one review per customer per product)
"""

import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------
class Category(models.Model):
    """A product group, shown on the home page and used to filter the shop."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(
        max_length=120, unique=True, blank=True,
        help_text="SEO-friendly URL part, e.g. 'home-furniture'. Auto-generated if left empty.",
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True)
    active = models.BooleanField(
        default=True,
        help_text="Inactive categories are hidden from the website (but stay in admin).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate the slug from the name: "Home & Furniture" -> "home-furniture"
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def product_count(self):
        """How many active products this category currently holds."""
        return self.products.filter(active=True).count()


# ---------------------------------------------------------------------------
# BRANDS
# ---------------------------------------------------------------------------
class Brand(models.Model):
    """A manufacturer/label. Optional on a product, but useful for filtering."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------------------------
class Product(models.Model):
    """A single sellable item."""

    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(
        max_length=220, unique=True, blank=True,
        help_text="SEO-friendly URL part, auto-generated from the name if empty.",
    )
    short_description = models.CharField(
        max_length=300, blank=True,
        help_text="One or two lines shown on product cards and at the top of the detail page.",
    )
    description = models.TextField(help_text="Full description shown on the product page.")

    # Relationships
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='products',
        help_text="Deleting a category also deletes its products.",
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products',
        help_text="If a brand is deleted, its products simply keep their other data.",
    )

    # Identification
    sku = models.CharField(
        max_length=64, unique=True, blank=True,
        help_text="Stock Keeping Unit. Auto-generated if left empty.",
    )

    # Money (stored as Decimal — NEVER use floats for money in Python/Django)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Original price (shown crossed-out when on sale).",
    )
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Sell price during a sale. Leave empty when there is no discount.",
    )

    # Stock
    stock = models.PositiveIntegerField(
        default=0,
        help_text="Units available. 0 = out of stock (cannot be added to cart).",
    )

    # Media
    image = models.ImageField(
        upload_to='products/',
        help_text="Main product photo (JPEG/PNG/WebP, a few hundred KB is enough).",
    )

    # Flags
    featured = models.BooleanField(
        default=False, help_text="Show on the home page 'Featured products' section.",
    )
    active = models.BooleanField(
        default=True, help_text="Inactive products are hidden from the website.",
    )

    # Timestamps (managed by Django automatically)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Speeds up the shop page filters/sorting:
        indexes = [
            models.Index(fields=['price']),
            models.Index(fields=['featured', 'active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate SEO slug from the name (only if the admin left it empty)
        if not self.slug:
            self.slug = slugify(self.name)
        # Auto-generate a SKU if the admin left it empty, e.g. "SKU-3F9A21C4"
        if not self.sku:
            self.sku = 'SKU-' + secrets.token_hex(4).upper()
        super().save(*args, **kwargs)

    def clean(self):
        """
        Business rules checked in forms AND in the admin (model-level
        validation is the safety net — the UI can never be trusted alone).
        """
        if self.discount_price is not None:
            if self.discount_price < 0:
                raise ValidationError({'discount_price': 'Price cannot be negative.'})
            if self.discount_price >= self.price:
                raise ValidationError(
                    {'discount_price': 'Discount price must be lower than the original price.'}
                )

    # ------------------------- handy helpers ------------------------------
    @property
    def is_on_sale(self):
        """True when a valid discount price exists."""
        return (
            self.discount_price is not None
            and self.price is not None
            and self.discount_price < self.price
        )

    @property
    def final_price(self):
        """The price the customer actually pays (discount price if on sale)."""
        if self.is_on_sale:
            return self.discount_price
        return self.price

    @property
    def discount_percentage(self):
        """e.g. 25 for a 25% discount — used for the red '-25%' badge."""
        if self.is_on_sale and self.price:
            return int(round((self.price - self.discount_price) * 100 / self.price))
        return 0

    @property
    def is_available(self):
        """True when the product can be bought right now."""
        return self.active and self.stock > 0


# ---------------------------------------------------------------------------
# PRODUCT GALLERY IMAGES (extra photos besides the main `Product.image`)
# ---------------------------------------------------------------------------
class ProductImage(models.Model):
    """An additional photo in the product detail page gallery."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='images',
        help_text="Deleting a product also deletes its gallery photos.",
    )
    image = models.ImageField(upload_to='products/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'product images'
        ordering = ['id']

    def __str__(self):
        return f"Image for {self.product.name}"


# ---------------------------------------------------------------------------
# REVIEWS (ratings)
# ---------------------------------------------------------------------------
class Review(models.Model):
    """A 1–5 star rating + optional comment left by a customer on a product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews',
        help_text="Deleting a product also deletes its reviews.",
    )
    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='reviews',
        help_text="The customer who wrote the review.",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1 to 5 stars.",
    )
    comment = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        # Business rule: one review per customer per product.
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'user'],
                name='unique_review_per_user_per_product',
            )
        ]

    def __str__(self):
        return f"{self.user} rated {self.product} {self.rating}/5"


# ---------------------------------------------------------------------------
# COUPONS
# ---------------------------------------------------------------------------
class Coupon(models.Model):
    """
    A discount code applied at checkout.

    Supports:
      * percentage discount  (e.g. 10% off, optionally capped)
      * fixed amount discount (e.g. ₹200 off)
    And enforces:
      * active flag
      * validity window (valid_from / valid_to)
      * minimum order amount
      * total usage limit
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed amount'

    code = models.CharField(
        max_length=50, unique=True,
        help_text="The code customers type in, e.g. SAVE20. Stored in UPPERCASE.",
    )
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENTAGE
    )
    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Percentage (e.g. 10) or fixed amount (e.g. 200), depending on type.",
    )
    minimum_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text="Coupon only applies when the cart subtotal is at least this much.",
    )
    maximum_discount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="For percentage coupons: cap the discount at this amount. Empty = no cap.",
    )
    valid_from = models.DateTimeField(
        null=True, blank=True, help_text="Coupon becomes usable at this moment (empty = immediately)."
    )
    valid_to = models.DateTimeField(
        null=True, blank=True, help_text="Coupon stops working after this moment (empty = never)."
    )
    active = models.BooleanField(default=True)
    usage_limit = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Total number of times this coupon can ever be used. Empty = unlimited.",
    )
    used_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()}: {self.discount_value})"

    def save(self, *args, **kwargs):
        # Codes are case-insensitive for customers; store them uppercase.
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def clean(self):
        if (
            self.discount_type == self.DiscountType.PERCENTAGE
            and self.discount_value > 100
        ):
            raise ValidationError(
                {'discount_value': 'Percentage discount cannot be more than 100.'}
            )

    # ------------------------- business logic ------------------------------
    def validate_for_order(self, subtotal):
        """
        The single entry point used by the cart and checkout.
        Returns (is_valid: bool, reason: str) — reason is '' when valid.
        """
        now = timezone.now()

        if not self.active:
            return False, 'This coupon is not active.'
        if self.valid_from and now < self.valid_from:
            return False, 'This coupon is not valid yet.'
        if self.valid_to and now > self.valid_to:
            return False, 'This coupon has expired.'
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, 'This coupon has reached its usage limit.'
        if subtotal < self.minimum_order_amount:
            return False, (
                f'Minimum order amount for this coupon is '
                f'{"₹" + str(self.minimum_order_amount)}.'
            )
        return True, ''

    def calculate_discount(self, subtotal):
        """How much this coupon takes off `subtotal` (never more than the subtotal)."""
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * self.discount_value / Decimal('100')
        else:  # FIXED
            discount = min(self.discount_value, subtotal)

        # Optional cap for percentage coupons
        if self.maximum_discount is not None:
            discount = min(discount, self.maximum_discount)

        return min(discount, subtotal).quantize(Decimal('0.01'))

    def register_usage(self):
        """Call once when a coupon is actually used in an order.

        Uses an F() expression so two simultaneous checkouts can't both
        read "3 used" and both bump it to 4 (race condition).
        """
        Coupon.objects.filter(pk=self.pk).update(used_count=models.F('used_count') + 1)
