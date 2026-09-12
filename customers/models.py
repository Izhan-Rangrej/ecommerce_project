"""
customers app — models.

Everything about the *people* on the site:

    UserProfile           -> extra info attached to Django's built-in User
    Address               -> saved shipping addresses (a user can have several)
    WishlistItem          -> products a user saved for later
    NewsletterSubscriber  -> emails from the home page signup form

Django already gives us a `User` model (username, email, hashed password).
Instead of changing it, we attach a OneToOne `UserProfile` — a clean,
standard pattern that keeps Django's auth system untouched.
"""

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver


# ---------------------------------------------------------------------------
# USER PROFILE (OneToOne with the built-in User)
# ---------------------------------------------------------------------------
class UserProfile(models.Model):
    """
    One extra record per customer: phone number, birthday, avatar.

    Access from anywhere:  my_user.profile.phone
    (works because of related_name='profile' below)
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile'
    )
    phone = models.CharField(max_length=15, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'user profile'

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"Profile of {name}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Signal: whenever a NEW User is saved, automatically create their profile.

    This means a customer never hits a missing-profile error — the profile
    exists from the moment the account does (register or admin-created user).
    """
    if created:
        UserProfile.objects.create(user=instance)


# ---------------------------------------------------------------------------
# ADDRESSES
# ---------------------------------------------------------------------------
class Address(models.Model):
    """
    A saved shipping address. A user can have many (Home, Office, ...),
    and exactly one should be marked as default for checkout.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses',
        help_text="Deleting a user deletes their saved addresses.",
    )
    label = models.CharField(
        max_length=50, blank=True,
        help_text="A nickname, e.g. 'Home' or 'Office'.",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    address_line_1 = models.CharField(max_length=200)
    address_line_2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']  # default address first

    def __str__(self):
        prefix = self.label or 'Address'
        return f"{prefix} — {self.city}"

    def save(self, *args, **kwargs):
        # Nice UX: the user's very first saved address becomes the default
        # automatically, so checkout has something to preselect.
        if self._state.adding and not self.user.addresses.exists():
            self.is_default = True
        super().save(*args, **kwargs)

    @classmethod
    def set_default(cls, address):
        """
        Make `address` the user's default and clear the flag on all others.
        Done in one transaction so we never end up with two defaults.
        """
        with transaction.atomic():
            cls.objects.filter(user=address.user, is_default=True).exclude(
                pk=address.pk
            ).update(is_default=False)
            address.is_default = True
            address.save(update_fields=['is_default'])


# ---------------------------------------------------------------------------
# WISHLIST
# ---------------------------------------------------------------------------
class WishlistItem(models.Model):
    """
    One saved product on a user's wishlist.
    The unique constraint below is what makes "prevent duplicate wishlist
    items" guaranteed at the database level, not just in the code.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist'
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='wishlist_items'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'],
                name='unique_product_in_wishlist',
            )
        ]

    def __str__(self):
        return f"{self.user} wants {self.product}"


# ---------------------------------------------------------------------------
# NEWSLETTER SUBSCRIBERS
# ---------------------------------------------------------------------------
class NewsletterSubscriber(models.Model):
    """
    An email address from the home page newsletter form.
    `unique=True` means the same email can only subscribe once.
    """

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email
