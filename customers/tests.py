"""
customers app — tests (PHASE 19).

Covers: registration, login/logout, the full password-reset flow,
address book CRUD, the wishlist (login wall, no duplicates,
move-to-cart) and newsletter signups.
"""

import re

from django.core import mail
from django.test import override_settings
from django.urls import reverse

from cart.constants import CART_SESSION_KEY
from customers.models import Address, WishlistItem
from core.testing import StoreTestCase


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class CustomerAuthTest(StoreTestCase):
    # ---------------- registration ----------------
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post('/register/', {
            'username': 'newbie',
            'email': 'newbie@test.example',
            'password1': 'Str0ngPass!99',
            'password2': 'Str0ngPass!99',
        })
        self.assertRedirects(response, reverse('customers:profile'))
        self.assertTrue(self.client.session.get('_auth_user_id'))

    def test_register_rejects_duplicate_username(self):
        self.customer  # exists via setUp
        response = self.client.post('/register/', {
            'username': 'customer',
            'email': 'someone-else@test.example',
            'password1': 'Str0ngPass!99',
            'password2': 'Str0ngPass!99',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
        self.assertFalse(self.client.session.get('_auth_user_id'))

    # ---------------- login / logout ----------------
    def test_login_success_and_logout(self):
        response = self.client.post('/accounts/login/', {
            'username': 'customer', 'password': self.password,
        })
        self.assertRedirects(response, reverse('core:home'))
        self.assertTrue(self.client.session.get('_auth_user_id'))
        # Django 5+: logout is POST-only.
        response = self.client.post('/accounts/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.session.get('_auth_user_id'))

    def test_login_wrong_password_shows_error(self):
        response = self.client.post('/accounts/login/', {
            'username': 'customer', 'password': 'WrongPass!1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'correct username')
        self.assertFalse(self.client.session.get('_auth_user_id'))

    # ---------------- password reset (full flow) ----------------
    def test_password_reset_flow(self):
        response = self.client.post(
            '/accounts/password_reset/',
            {'email': self.customer.email})
        self.assertEqual(len(mail.outbox), 1)

        # The token is hidden in the session: the emailed URL 302s to a
        # set-password URL, which is where the new password is POSTed.
        match = re.search(r'https?://\S+/', mail.outbox[0].body)
        self.assertIsNotNone(match, 'reset email contains no link')
        reset_url = match.group(0)

        response = self.client.get(reset_url, follow=True)
        final_url = response.redirect_chain[-1][0]
        self.assertIn('set-password', final_url)

        response = self.client.post(final_url, {
            'new_password1': 'BrandN3wPass!77',
            'new_password2': 'BrandN3wPass!77',
        })
        self.assertEqual(response.status_code, 302)

        # The new password works, the old one no longer does.
        self.assertTrue(
            self.client.login(username='customer',
                              password='BrandN3wPass!77'))
        self.assertFalse(
            self.client.login(username='customer', password=self.password))


class AddressBookTest(StoreTestCase):
    OFFICE = {
        'label': 'Office', 'full_name': 'Cust Omer',
        'phone': '9800002222', 'address_line_1': '2 Work Road',
        'city': 'Surat', 'state': 'Gujarat', 'pincode': '395001',
        'country': 'India',
    }

    def test_add_set_default_edit_delete(self):
        self.client.login(username='customer', password=self.password)
        # setUp's address is the first one saved, so it is the default.
        self.assertTrue(self.address.is_default)

        self.client.post('/account/addresses/add/', self.OFFICE)
        office = Address.objects.get(user=self.customer, label='Office')
        self.assertFalse(office.is_default)

        # Switch the default via the dedicated endpoint.
        self.client.post(f'/account/addresses/{office.pk}/default/')
        office.refresh_from_db()
        self.address.refresh_from_db()
        self.assertTrue(office.is_default)
        self.assertFalse(self.address.is_default)

        data = dict(self.OFFICE, label='Office (updated)')
        self.client.post(f'/account/addresses/{office.pk}/edit/', data)
        office.refresh_from_db()
        self.assertEqual(office.label, 'Office (updated)')

        self.client.post(f'/account/addresses/{office.pk}/delete/')
        self.assertFalse(Address.objects.filter(pk=office.pk).exists())


class WishlistTest(StoreTestCase):
    def test_wishlist_requires_login(self):
        response = self.client.get('/wishlist/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_toggle_adds_and_never_duplicates(self):
        self.client.login(username='customer', password=self.password)
        self.client.post(f'/wishlist/toggle/{self.product_a.pk}/')
        self.client.post(f'/wishlist/toggle/{self.product_a.pk}/')
        # Toggling twice = add then remove; toggle once more = one item.
        self.client.post(f'/wishlist/toggle/{self.product_a.pk}/')
        self.assertEqual(
            WishlistItem.objects.filter(user=self.customer).count(), 1)
        cart = self.client.session.get(CART_SESSION_KEY) or {}
        self.assertNotIn(str(self.product_a.pk), cart)

    def test_move_to_cart_adds_one_and_removes_saved_item(self):
        self.client.login(username='customer', password=self.password)
        self.client.post(f'/wishlist/toggle/{self.product_b.pk}/')
        self.client.post(f'/wishlist/move-to-cart/{self.product_b.pk}/')
        cart = self.client.session.get(CART_SESSION_KEY) or {}
        self.assertEqual(cart.get(str(self.product_b.pk)), 1)
        self.assertFalse(WishlistItem.objects.filter(
            user=self.customer, product=self.product_b).exists())


class NewsletterTest(StoreTestCase):
    def test_subscribe_and_duplicate(self):
        response = self.client.post(
            '/newsletter/subscribe/', {'email': 'fan@test.example'})
        self.assertEqual(response.status_code, 302)
        from customers.models import NewsletterSubscriber
        self.assertTrue(NewsletterSubscriber.objects.filter(
            email='fan@test.example').exists())

        response = self.client.post(
            '/newsletter/subscribe/', {'email': 'fan@test.example'})
        # (assertRedirects would FOLLOW the redirect and consume the
        # message we want to assert on — so just check the Location.)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('core:about'))
        self.assertContains(self.client.get(reverse('core:about')),
                            'already subscribed')
