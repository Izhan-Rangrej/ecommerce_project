"""
customers app — urls.

PHASE 8 consolidated this app's routes into ONE urlconf (included once,
at the site root):

    /wishlist/toggle/<id>/          (PHASE 5 — path unchanged)
    /register/                      new account
    /account/                       profile (edit details)
    /account/change-password/       change password
    /account/addresses/…            address book (list/add/edit/delete/default)

Login, logout and password RESET live at /accounts/… — that's Django's
built-in auth urls (see the root urls.py); PHASE 8 restyles those pages
by overriding their default templates.
"""

from django.urls import path

from . import views

app_name = 'customers'

urlpatterns = [
    # PHASE 5 (path unchanged on purpose — main.js calls it directly)
    path('wishlist/toggle/<int:product_id>/', views.wishlist_toggle,
         name='wishlist_toggle'),

    # PHASE 10 — the wishlist page + row actions
    path('wishlist/', views.wishlist_page, name='wishlist_page'),
    path('wishlist/remove/<int:product_id>/', views.wishlist_remove,
         name='wishlist_remove'),
    path('wishlist/move-to-cart/<int:product_id>/', views.wishlist_move_to_cart,
         name='wishlist_move'),

    # PHASE 8 — registration
    path('register/', views.register, name='register'),

    # PHASE 8 — account area
    path('account/', views.profile, name='profile'),
    path('account/change-password/', views.change_password,
         name='change_password'),
    path('account/addresses/', views.address_list, name='addresses'),
    path('account/addresses/add/', views.address_add, name='address_add'),
    path('account/addresses/<int:pk>/edit/', views.address_edit,
         name='address_edit'),
    path('account/addresses/<int:pk>/default/', views.address_set_default,
         name='address_set_default'),
    path('account/addresses/<int:pk>/delete/', views.address_delete,
         name='address_delete'),
]
