"""
core app — urls (site pages, newsletter, error handlers live here).
"""

from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('newsletter/subscribe/', views.newsletter_subscribe,
         name='newsletter_subscribe'),

    # PHASE 19: SEO files (sitemap + robots)
    path('sitemap.xml', views.sitemap_xml, name='sitemap'),
    path('robots.txt', views.robots_txt, name='robots'),
]
