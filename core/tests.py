"""
core app — tests (PHASE 19).

Covers: security headers + cookies, rate limiting (login), custom
error pages, robots.txt / sitemap.xml, and the navbar cache signals.
"""

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core import ratelimit
from core.testing import StoreTestCase, make_category, make_image
from core.views import error_403, error_404, error_500
from products.models import Category, Product


class SecurityHeadersTest(StoreTestCase):
    def test_security_headers_present(self):
        response = self.client.get('/')
        h = response.headers
        csp = h.get('Content-Security-Policy', '')
        self.assertIn("default-src 'self'", csp)
        self.assertIn('https://cdn.jsdelivr.net', csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(h.get('X-Frame-Options'), 'DENY')
        self.assertEqual(h.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(h.get('Referrer-Policy'), 'same-origin')

    def test_session_cookie_samesite_lax(self):
        response = self.client.post(
            f'/cart/add/{self.product_a.pk}/', {'quantity': 1})
        morsel = self.client.cookies.get('sessionid')
        self.assertIsNotNone(morsel)
        self.assertIn('SameSite=Lax', str(morsel))


class LoginRateLimitTest(StoreTestCase):
    def _fail_login(self, remote='1.2.3.4'):
        return self.client.post(
            '/accounts/login/',
            {'username': 'ghost-user', 'password': 'WrongPass!1'},
            REMOTE_ADDR=remote,
        )

    def test_sixth_failed_login_is_throttled(self):
        for _ in range(5):
            response = self._fail_login()
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Too many login attempts')
        response = self._fail_login()
        self.assertContains(response, 'Too many login attempts')
        self.assertFalse(self.client.session.get('_auth_user_id'))

    def test_other_ip_is_not_blocked(self):
        for _ in range(6):
            self._fail_login(remote='1.2.3.4')
        response = self._fail_login(remote='9.9.9.9')
        self.assertNotContains(response, 'Too many login attempts')

    def test_lockout_holds_even_with_correct_password(self):
        # Standard brute-force protection: once the window is full, the
        # address waits — even the right password — until it resets.
        for _ in range(5):
            self._fail_login()
        response = self.client.post('/accounts/login/', {
            'username': 'customer', 'password': self.password,
        }, REMOTE_ADDR='1.2.3.4')
        self.assertContains(response, 'Too many login attempts')
        self.assertFalse(self.client.session.get('_auth_user_id'))


class ErrorPagesTest(StoreTestCase):
    def _styled_request(self, path='/'):
        """RequestFactory requests lack session/user — the styled error
        templates (they extend base.html) need both."""
        request = RequestFactory().get(path)
        request.session = SessionStore()
        request.user = AnonymousUser()
        return request

    def test_404_handler_renders_custom_page(self):
        response = self.client.get('/no-such-page-404/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, '404', status_code=404)

    def test_403_and_500_handlers_render(self):
        r403 = error_403(self._styled_request(), exception=None)
        self.assertIsInstance(r403, HttpResponse)
        self.assertEqual(r403.status_code, 403)
        r500 = error_500(self._styled_request())
        self.assertEqual(r500.status_code, 500)
        self.assertContains(r500, '500', status_code=500)


class RobotsSitemapTest(StoreTestCase):
    def test_robots_txt(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertContains(response, 'Disallow: /admin/')
        self.assertContains(response, 'Disallow: /checkout/')
        self.assertContains(response, 'Sitemap:')

    def test_sitemap_lists_public_pages_only(self):
        inactive = Product.objects.create(
            name='Hidden Product', slug='hidden-product',
            description='x', category=self.cat_a, price='10.00',
            stock=1, sku='SKU-HIDDEN', active=False,
        )
        inactive.image.save('hidden.png', make_image('hidden.png'), save=False)
        inactive.save()

        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/xml', response['Content-Type'])
        self.assertContains(response, f'/product/{self.product_a.slug}/')
        self.assertContains(response, f'/category/{self.cat_a.slug}/')
        self.assertNotContains(response, '/product/hidden-product/')
        inactive.delete()


class NavbarCacheSignalTest(StoreTestCase):
    def test_category_change_invalidates_cache(self):
        self.client.get('/')
        self.assertIsNotNone(cache.get('navbar_categories'))
        new_cat = make_category('ZZZ Cache Test')
        self.assertIsNone(cache.get('navbar_categories'))
        self.client.get('/')
        self.assertIsNotNone(cache.get('navbar_categories'))
        new_cat.delete()
        self.assertIsNone(cache.get('navbar_categories'))
        cache.delete('navbar_categories')
