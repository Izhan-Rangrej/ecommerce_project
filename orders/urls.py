"""
orders app — urls (PHASE 11: checkout).

This app is mounted at the site root (see the root urls.py), so the
paths below are absolute:

    /checkout/                          the 5-step checkout (GET)
    /checkout/step/<n>/                 jump to step n — "Back" + stepper (GET)
    /checkout/address/                  pick or create the shipping address (POST)
    /checkout/continue/                 confirm the delivery / payment step (POST)
    /checkout/place-order/              place the order (POST)
    /checkout/complete/<order_number>/  step 5 — "order placed" screen (GET)

PHASE 12:
    /orders/                      order history (GET)
    /orders/<order_number>/       order detail + status timeline (GET)
    /orders/<order_number>/cancel/ customer cancel, pending orders (POST)
"""

from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    # PHASE 11 — the 5-step checkout
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/step/<int:step>/', views.checkout_step, name='checkout_step'),
    path('checkout/address/', views.checkout_address, name='checkout_address'),
    path('checkout/continue/', views.checkout_continue, name='checkout_continue'),
    path('checkout/coupon/', views.checkout_coupon, name='checkout_coupon'),
    path('checkout/place-order/', views.place_order, name='place_order'),
    path('checkout/complete/<str:order_number>/', views.order_complete,
         name='order_complete'),

    # PHASE 12 — order history + detail + cancel
    path('orders/', views.order_list, name='order_list'),
    path('orders/<str:order_number>/', views.order_detail,
         name='order_detail'),
    path('orders/<str:order_number>/cancel/', views.order_cancel,
         name='order_cancel'),
]
