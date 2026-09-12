"""
core app — tests (PHASE 19).

Covers: security headers + cookies, rate limiting (login), custom
error pages, robots.txt / sitemap.xml, and the navbar cache signals.
"""

from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db.utils import OperationalError
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core import ratelimit
from ecommerce_project.dburl import is_pooled_host, parse_database_url
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


# ---------------------------------------------------------------------------
# PHASE 21 — deployment: connection-string parsing and the health probe.
# These are the two pieces that only matter once the store runs on a managed
# Postgres (Neon) behind a platform (Render), and both fail *silently* and
# far from the machine that made the mistake — a wrong DB password surfaces
# as a 500 on the live site, a broken health check surfaces as an instance
# Render keeps restarting. So they are tested here, not discovered there.
# ---------------------------------------------------------------------------
class DatabaseUrlParsingTest(TestCase):
    """ecommerce_project.dburl.parse_database_url — no database needed."""

    def test_neon_pooled_connection_string(self):
        cfg = parse_database_url(
            'postgresql://neondb_owner:AbCd1234'
            '@ep-amber-meadow-123456-pooler.ap-southeast-1.aws.neon.tech'
            '/neondb?sslmode=require'
        )
        self.assertEqual(cfg['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(cfg['USER'], 'neondb_owner')
        self.assertEqual(cfg['PASSWORD'], 'AbCd1234')
        self.assertEqual(
            cfg['HOST'],
            'ep-amber-meadow-123456-pooler.ap-southeast-1.aws.neon.tech')
        self.assertEqual(cfg['NAME'], 'neondb')
        self.assertEqual(cfg['PORT'], '5432')
        self.assertEqual(cfg['OPTIONS']['sslmode'], 'require')

    def test_percent_encoded_password_is_decoded(self):
        # Neon passwords routinely contain / @ : which arrive percent-encoded.
        cfg = parse_database_url('postgresql://u:p%40ss%2Fw%3Ard@h.example.com/db')
        self.assertEqual(cfg['PASSWORD'], 'p@ss/w:rd')

    def test_password_containing_a_literal_at_sign(self):
        # userinfo must be split at the LAST '@', not the first.
        cfg = parse_database_url('postgresql://u:pa@ssword@h.example.com:6432/db')
        self.assertEqual(cfg['USER'], 'u')
        self.assertEqual(cfg['PASSWORD'], 'pa@ssword')
        self.assertEqual(cfg['HOST'], 'h.example.com')
        self.assertEqual(cfg['PORT'], '6432')

    def test_postgres_scheme_alias_and_missing_port(self):
        cfg = parse_database_url('postgres://u:p@h.example.com/db')
        self.assertEqual(cfg['HOST'], 'h.example.com')
        self.assertEqual(cfg['PORT'], '5432')   # libpq default

    def test_bare_dsn_without_a_scheme(self):
        cfg = parse_database_url('u:p@h.example.com:5432/db')
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg['USER'], 'u')
        self.assertEqual(cfg['HOST'], 'h.example.com')

    def test_tls_is_forced_when_the_url_omits_it(self):
        cfg = parse_database_url('postgresql://u:p@h.example.com/db')
        self.assertEqual(cfg['OPTIONS']['sslmode'], 'require')

    def test_known_driver_params_are_forwarded(self):
        cfg = parse_database_url(
            'postgresql://u:p@h/db?sslmode=verify-full'
            '&channel_binding=require&application_name=shopsphere'
        )
        self.assertEqual(cfg['OPTIONS']['sslmode'], 'verify-full')
        self.assertEqual(cfg['OPTIONS']['channel_binding'], 'require')
        self.assertEqual(cfg['OPTIONS']['application_name'], 'shopsphere')

    def test_unknown_query_params_are_ignored(self):
        # Providers append tracking junk; libpq would reject unknown keywords.
        cfg = parse_database_url('postgresql://u:p@h/db?utm_source=console&foo=1')
        self.assertNotIn('utm_source', cfg['OPTIONS'])
        self.assertNotIn('foo', cfg['OPTIONS'])

    def test_empty_and_non_postgres_urls_return_none(self):
        for bad in ('', '   ', None, 'mysql://u:p@h/db', 'sqlite:///db.sqlite3'):
            self.assertIsNone(parse_database_url(bad), f'should reject {bad!r}')

    def test_is_pooled_host_detection(self):
        self.assertTrue(is_pooled_host(
            'ep-amber-meadow-123456-pooler.ap-southeast-1.aws.neon.tech'))
        self.assertFalse(is_pooled_host(
            'ep-amber-meadow-123456.ap-southeast-1.aws.neon.tech'))
        self.assertFalse(is_pooled_host(''))
        self.assertFalse(is_pooled_host(None))


class HealthCheckTest(TestCase):
    """/healthz/ — what Render polls to decide the instance is alive."""

    def test_returns_ok(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_is_never_cached(self):
        # A cached "ok" would keep Render routing traffic to a dead instance.
        response = self.client.get('/healthz/')
        self.assertIn('no-store', response['Cache-Control'])

    def test_does_not_touch_the_database(self):
        # The whole point: the probe must stay fast and must not have to wait
        # for Neon to wake from its 5-minute idle suspension.
        with self.assertNumQueries(0):
            self.client.get('/healthz/')

    def test_deep_check_reports_a_broken_database_without_a_500(self):
        # ?db=1 is for a human after a deploy. It must report the failure as
        # structured JSON (503), not blow up with an unhandled traceback.
        with mock.patch('django.db.connection.cursor') as cursor:
            cursor.side_effect = OperationalError('connection closed')
            response = self.client.get('/healthz/?db=1')
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body['status'], 'degraded')
        self.assertIn('OperationalError', body['database'])

    def test_is_excluded_from_robots(self):
        self.assertContains(self.client.get('/robots.txt'), 'Disallow: /healthz/')


class ContentSecurityPolicyTest(TestCase):
    """PHASE 21 — the CSP must stay locked down by default but allow a CDN
    for images once uploads move off this server (see core/middleware.py)."""

    def test_default_policy_is_unchanged(self):
        from core.middleware import _build_csp
        csp = _build_csp()
        self.assertIn("img-src 'self' data:;", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn('unsafe-inline', csp)

    def test_extra_image_origins_are_appended(self):
        from core.middleware import _build_csp
        with self.settings(CSP_EXTRA_IMG_SRC='https://res.cloudinary.com, https://cdn.example.com'):
            csp = _build_csp()
        self.assertIn("img-src 'self' data: https://res.cloudinary.com "
                      "https://cdn.example.com;", csp)

    def test_blank_and_whitespace_entries_are_ignored(self):
        from core.middleware import _build_csp
        with self.settings(CSP_EXTRA_IMG_SRC=' , ,'):
            self.assertIn("img-src 'self' data:;", _build_csp())

    def test_script_src_never_widens(self):
        # Widening images must not be able to loosen script rules.
        from core.middleware import _build_csp
        with self.settings(CSP_EXTRA_IMG_SRC='https://evil.example.com'):
            csp = _build_csp()
        self.assertIn("script-src 'self' https://cdn.jsdelivr.net;", csp)
        self.assertNotIn('evil.example.com; script', csp)
