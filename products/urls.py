"""
products app — urls.

PHASE 7:  /shop/ listing, /category/<slug>/ pages, upgraded /product/<slug>/.
          /search/ is a legacy redirect to /shop/ (old bookmarks keep working).
"""

from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'products'

urlpatterns = [
    path('shop/', views.shop, name='shop'),
    # Legacy: everything typed at /search/ now lands on the shop listing.
    # query_string=True keeps ?q=… (Django 6.1 defaults it to False).
    # PHASE 16: JSON endpoint for the navbar search suggestions
    # (progressive enhancement — the plain GET form works without it)
    path('search/suggest/', views.search_suggest, name='search_suggest'),
    path('search/', RedirectView.as_view(
        url='/shop/', permanent=False, query_string=True
    ), name='search'),
    path('category/<slug:slug>/', views.category_detail, name='category'),
    path('product/<slug:slug>/', views.product_detail, name='detail'),
    # PHASE 15: purchase-verified review (POST only)
    path('product/<slug:slug>/review/', views.write_review, name='review_write'),
]
