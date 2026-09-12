"""
customers app — admin panel configuration.

Includes a custom admin for Django's built-in User model: the default
User admin gets a "Profile" section (phone, birthday, avatar) so a
store manager can manage everything about a customer in ONE page.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Address, NewsletterSubscriber, UserProfile, WishlistItem

# Django ships a default admin for User. To extend it we must first
# remove (unregister) the default, then register our own below.
# (Skipping this line causes: AlreadyRegistered: model User is already registered)
admin.site.unregister(User)


# ---------------------------------------------------------------------------
# USER (Django's built-in, extended with the profile inline)
# ---------------------------------------------------------------------------
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0   # exactly one profile per user — no extra empty rows


@admin.register(User)
class ShopUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name',
                    'phone', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    @admin.display(description='Phone')
    def phone(self, obj):
        profile = getattr(obj, 'profile', None)
        return (profile.phone if profile and profile.phone else '—')


# ---------------------------------------------------------------------------
# USER PROFILE (also listed on its own)
# ---------------------------------------------------------------------------
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'date_of_birth', 'created_at')
    search_fields = ('user__username', 'user__email', 'phone')
    readonly_fields = ('created_at',)


# ---------------------------------------------------------------------------
# ADDRESS
# ---------------------------------------------------------------------------
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'label', 'full_name', 'phone',
        'city', 'state', 'pincode', 'is_default', 'created_at',
    )
    list_display_links = ('id',)
    list_filter = ('is_default', 'state', 'city')
    search_fields = ('user__username', 'full_name', 'phone', 'city', 'pincode')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='User')
    def user(self, obj):
        return obj.user.get_full_name() or obj.user.username


# ---------------------------------------------------------------------------
# WISHLIST
# ---------------------------------------------------------------------------
@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'product__name')
    readonly_fields = ('added_at',)

    @admin.display(description='User')
    def user(self, obj):
        return obj.user.get_full_name() or obj.user.username


# ---------------------------------------------------------------------------
# NEWSLETTER SUBSCRIBERS
# ---------------------------------------------------------------------------
@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('email',)
    actions = ('deactivate_selected',)

    @admin.action(description='Deactivate selected subscribers')
    def deactivate_selected(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f'{n} subscriber(s) deactivated.')
