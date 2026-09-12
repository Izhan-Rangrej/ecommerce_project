"""
payments app — tests (PHASE 19).

The built-in TEST gateway is deterministic, so we can assert exactly:
a valid card charges, the magic declined card declines, garbage input
is refused, and refunds succeed.
"""

from django.test import TestCase

from payments.gateway import TEST_DECLINED_CARD, charge, refund


class TestGatewayTest(TestCase):
    def test_valid_card_charges(self):
        result = charge('1500.00', '4242424242424242', 'Test User', '12/28', '123')
        self.assertTrue(result['ok'])
        self.assertTrue(result['transaction_id'].startswith('pay_'))

    def test_declined_card_is_declined(self):
        result = charge('1500.00', TEST_DECLINED_CARD, 'Test User', '12/28', '123')
        self.assertFalse(result['ok'])
        self.assertEqual(result['transaction_id'], '')
        self.assertIn('declined', result['message'])

    def test_short_card_number_is_refused(self):
        result = charge('1500.00', '4242', 'Test User', '12/28', '123')
        self.assertFalse(result['ok'])

    def test_missing_holder_name_is_refused(self):
        result = charge('1500.00', '4242424242424242', '', '12/28', '123')
        self.assertFalse(result['ok'])

    def test_spaces_in_card_number_are_ignored(self):
        result = charge('1500.00', '4242 4242 4242 4242', 'Test User', '12/28', '123')
        self.assertTrue(result['ok'])

    def test_refund_succeeds(self):
        result = refund('pay_abc123')
        self.assertTrue(result['ok'])
        self.assertEqual(result['transaction_id'], 'pay_abc123')
