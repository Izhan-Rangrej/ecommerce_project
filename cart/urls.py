"""
cart app — urls.

    /cart/                        the cart page (GET)
    /cart/add/<id>/               add to cart (POST)
    /cart/update/<id>/            change a line's quantity (POST)
    /cart/remove/<id>/            remove a line (POST)
    /cart/clear/                  empty the cart (POST)

Only the PAGE is a GET — everything else is an action, so all the other
endpoints are POST-only (the views use @require_POST).
"""

from django.urls import path

from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_page, name='page'),
    path('add/<int:product_id>/', views.add_to_cart, name='add'),
    path('update/<int:product_id>/', views.update_quantity, name='update'),
    path('remove/<int:product_id>/', views.remove_from_cart, name='remove'),
    path('clear/', views.clear_cart, name='clear'),
]
