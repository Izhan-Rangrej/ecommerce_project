"""
products/templatetags/shop_tags.py — small helpers for the shop listing.

The `link` tag builds a URL that KEEPS the filters the customer already
selected and changes only the ones you pass — this is what makes the
filter sidebar work with zero JavaScript.

Usage:
    {# select "Electronics", keep everything else (sort, price…) #}
    <a href="{% link 'products:shop' category='electronics' %}">Electronics</a>

    {# remove the rating filter, keep everything else #}
    <a href="{% link 'products:shop' rating='' %}">clear rating</a>

    {# plain link, no changes #}
    <a href="{% link 'products:shop' %}">All products</a>

Rules:
    * passing a value  -> sets that GET param
    * passing ''       -> removes that GET param
    * `page` is always reset to 1 (filtering starts at the first page)
    * on a category page (the view passes `list_category` into the
      context) the link keeps pointing at THAT CATEGORY — the category
      lives in the URL path, so any `category` GET param is dropped
      (PHASE 16: before this, clicking a filter on /category/...
      silently jumped back to /shop/).
"""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def link(context, view_name, **params):
    request = context.get('request')

    # PHASE 16: category pages must stay category pages.
    category = context.get('list_category')
    if category is not None:
        base = reverse('products:category', args=[category.slug])
    else:
        base = reverse(view_name)

    if request is None:      # e.g. when rendering from a management command
        return base

    qs = request.GET.copy()
    for key, value in params.items():
        if value is None or value == '':
            qs.pop(key, None)        # empty value = remove the filter
        else:
            qs[key] = str(value)
    if category is not None:
        qs.pop('category', None)     # it's in the path, not the query string
    # Any FILTER change resets to page 1 — but an explicitly passed
    # `page=N` (pagination links) must survive.
    if 'page' not in params:
        qs.pop('page', None)

    encoded = qs.urlencode()
    return f'{base}?{encoded}' if encoded else base
