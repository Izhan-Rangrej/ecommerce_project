"""
core/signals.py — PHASE 18: keep the cached navbar menu fresh.

The navbar's Categories dropdown is cached for 5 minutes (before this
phase, the SAME query ran on every single page load). These handlers
delete the cache entry the moment a category or product changes in
the admin, so the menu can never be stale for more than one save.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from products.models import Category, Product

# Must match the key used in core.context_processors.categories().
NAVBAR_CATEGORIES_KEY = 'navbar_categories'


@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def _category_changed(sender, instance, **kwargs):
    cache.delete(NAVBAR_CATEGORIES_KEY)


@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
def _product_changed(sender, instance, **kwargs):
    # A product can appear/disappear from a category's listing,
    # which changes the counts the dropdown shows.
    cache.delete(NAVBAR_CATEGORIES_KEY)
