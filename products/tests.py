"""
products app — tests (PHASE 19).

Covers: the listing (pagination, search, filters, sorts, facet
counts), the category page lock, the product detail page, the
search-suggest JSON endpoint, the purchase-gated review flow, and
the 404 page.
"""

from django.urls import reverse

from core.testing import StoreTestCase, add_to_cart, make_product, run_checkout_steps
from orders.models import Order
from products.models import Review


class ListingTest(StoreTestCase):
    def test_pagination_12_per_page(self):
        for i in range(13):
            make_product(f'Extra Product {i}', category=self.cat_a)
        response = self.client.get('/shop/')
        self.assertContains(response, 'of 16')          # 3 + 13
        self.assertContains(response, 'page=2')

    def test_search_by_name_category_and_brand(self):
        # 'alpha' matches Alpha Widget (name) AND Gamma Runner (its
        # brand is Alpha Co) — brand matching is part of the design.
        response = self.client.get('/shop/?q=alpha')
        self.assertContains(response, 'Alpha Widget')
        self.assertContains(response, 'Gamma Runner')
        self.assertNotContains(response, 'Beta Gadget')

        response = self.client.get('/shop/?q=sports')   # category name
        self.assertContains(response, 'Gamma Runner')
        self.assertNotContains(response, 'Alpha Widget')
        self.assertNotContains(response, 'Beta Gadget')

        response = self.client.get('/shop/?q=beta')     # brand + name
        self.assertContains(response, 'Beta Gadget')
        self.assertNotContains(response, 'Alpha Widget')
        self.assertNotContains(response, 'Gamma Runner')

    def test_category_and_brand_filters(self):
        response = self.client.get('/shop/?category=test-sports')
        self.assertContains(response, 'Gamma Runner')
        self.assertNotContains(response, 'Alpha Widget')

        response = self.client.get('/shop/?brand=beta-co')
        self.assertContains(response, 'Beta Gadget')
        self.assertNotContains(response, 'Alpha Widget')

    def test_price_filter(self):
        response = self.client.get('/shop/?min=500&max=1000')
        self.assertContains(response, 'Alpha Widget')    # 899
        self.assertNotContains(response, 'Beta Gadget')  # 399
        self.assertNotContains(response, 'Gamma Runner')  # 1499

    def test_rating_filter(self):
        Review.objects.create(product=self.product_a, user=self.customer,
                              rating=5, comment='great')
        Review.objects.create(product=self.product_b, user=self.customer,
                              rating=2, comment='meh')
        response = self.client.get('/shop/?rating=4')
        self.assertContains(response, 'Alpha Widget')
        self.assertNotContains(response, 'Beta Gadget')
        self.assertNotContains(response, 'Gamma Runner')  # no reviews

    def test_sort_price_ascending(self):
        response = self.client.get('/shop/?sort=price_asc')
        html = response.content.decode()
        self.assertLess(html.find('Beta Gadget'), html.find('Alpha Widget'))
        self.assertLess(html.find('Alpha Widget'), html.find('Gamma Runner'))

    def test_facet_counts_respond_to_other_filters(self):
        # With brand=alpha-co the Electronics facet shows 1 (only Alpha
        # Widget is electronics+alpha), Sports also 1, and the brand
        # list keeps BOTH brands (own selection excluded).
        response = self.client.get('/shop/?brand=alpha-co')
        html = response.content.decode()
        self.assertIn('Alpha Widget', html)
        self.assertNotIn('Beta Gadget', html)
        self.assertIn('Beta Co', html)   # still listed for switching

    def test_inactive_products_are_hidden(self):
        self.product_a.active = False
        self.product_a.save(update_fields=['active'])
        response = self.client.get('/shop/')
        self.assertNotContains(response, 'Alpha Widget')
        self.assertEqual(self.client.get(f'/product/{self.product_a.slug}/').status_code, 404)


class CategoryPageTest(StoreTestCase):
    def test_category_page_locks_the_category(self):
        response = self.client.get('/category/test-electronics/')
        self.assertContains(response, 'Alpha Widget')
        self.assertNotContains(response, 'Gamma Runner')
        # A category GET param cannot override the page's own category.
        response = self.client.get(
            '/category/test-electronics/?category=test-sports')
        self.assertNotContains(response, 'Gamma Runner')

    def test_filter_links_stay_on_the_category(self):
        html = self.client.get('/category/test-electronics/').content.decode()
        self.assertIn('href="/category/test-electronics/?brand=alpha-co"', html)


class DetailTest(StoreTestCase):
    def test_detail_renders_with_related(self):
        response = self.client.get(f'/product/{self.product_a.slug}/')
        self.assertContains(response, 'Alpha Widget')
        self.assertContains(response, 'Beta Gadget')      # related (same cat)
        self.assertNotContains(response, 'Gamma Runner')  # different cat
        self.assertContains(response, 'Write a review')

    def test_detail_404_for_missing_slug(self):
        self.assertEqual(
            self.client.get('/product/no-such-slug/').status_code, 404)


class SuggestEndpointTest(StoreTestCase):
    def test_suggest_returns_json_matches(self):
        response = self.client.get('/search/suggest/', {'q': 'alph'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 'alph' matches Alpha Widget (name) and Gamma Runner (brand).
        self.assertEqual(
            [x['name'] for x in data['results']],
            ['Alpha Widget', 'Gamma Runner'])
        result = data['results'][0]
        self.assertEqual(result['url'], f'/product/{self.product_a.slug}/')
        self.assertEqual(result['price'], '899.00')

    def test_suggest_needs_two_characters(self):
        self.assertEqual(
            self.client.get('/search/suggest/', {'q': 'a'}).json(),
            {'results': []})
        self.assertEqual(
            self.client.get('/search/suggest/').json(), {'results': []})

    def test_suggest_is_get_only(self):
        self.assertEqual(
            self.client.post('/search/suggest/', {'q': 'alph'}).status_code,
            405)


class ReviewFlowTest(StoreTestCase):
    """The purchase-gated review flow (PHASE 15), as permanent tests."""

    def _buy(self, client, product):
        """Log in the standard customer and buy one unit of `product`."""
        client.login(username='customer', password=self.password)
        add_to_cart(client, product, 1)
        run_checkout_steps(client, self.address, 'cod')

    def test_guest_is_sent_to_login(self):
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': 5, 'comment': 'x'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/accounts/login/'))
        self.assertIn('next=', response['Location'])

    def test_non_buyer_cannot_review(self):
        self.client.login(username='customer', password=self.password)
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': 5, 'comment': 'never bought it'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'], f'/product/{self.product_a.slug}/#reviews')
        self.assertFalse(Review.objects.filter(product=self.product_a).exists())
        html = self.client.get(f'/product/{self.product_a.slug}/').content.decode()
        self.assertIn('Only customers who purchased', html)

    def test_buyer_creates_then_updates_one_review(self):
        self._buy(self.client, self.product_a)
        self.assertEqual(Order.objects.filter(user=self.customer).count(), 1)

        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '4', 'comment': 'Solid build.'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'], f'/product/{self.product_a.slug}/#reviews')
        review = Review.objects.get(product=self.product_a, user=self.customer)
        self.assertEqual(review.rating, 4)

        created_at = review.created_at
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '5', 'comment': 'Even better on second thought.'})
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Even better on second thought.')
        self.assertEqual(review.created_at, created_at)   # update, not new row
        self.assertEqual(
            Review.objects.filter(product=self.product_a).count(), 1)

        html = self.client.get(f'/product/{self.product_a.slug}/').content.decode()
        self.assertIn('Even better on second thought.', html)
        self.assertIn('Verified purchase', html)

    def test_rating_out_of_range_rejected(self):
        self._buy(self.client, self.product_a)
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '0', 'comment': ''})
        self.assertContains(response, 'greater than or equal to 1')
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '99', 'comment': ''})
        self.assertContains(response, 'less than or equal to 5')
        self.assertFalse(Review.objects.exists())

    def test_comment_longer_than_1000_chars_rejected(self):
        self._buy(self.client, self.product_a)
        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '3', 'comment': 'x' * 1001})
        self.assertContains(response, 'at most 1000 characters')
        self.assertFalse(Review.objects.exists())

    def test_cancelled_order_does_not_grant_review_right(self):
        self._buy(self.client, self.product_a)
        order = Order.objects.get(user=self.customer)
        # Cancel through the real customer endpoint (stock goes back).
        response = self.client.post(
            f'/orders/{order.order_number}/cancel/')
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.order_status, order.Status.CANCELLED)

        response = self.client.post(
            f'/product/{self.product_a.slug}/review/',
            {'rating': '5', 'comment': 'too late'})
        html = self.client.get(f'/product/{self.product_a.slug}/').content.decode()
        self.assertIn('Only customers who purchased', html)
        self.assertFalse(Review.objects.exists())
