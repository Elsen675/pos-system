import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from menu.models import Order

from .factories import make_restaurant, make_staff, make_table


class TransitionRuleTests(TestCase):
    """Modeldəki qayda: yalnız irəli, served/cancelled sondur."""

    def setUp(self):
        r = make_restaurant()
        self.order = Order.objects.create(restaurant=r, table=make_table(r), total=Decimal('1'))

    def at(self, status, pay_status='unpaid'):
        self.order.status = status
        self.order.pay_status = pay_status
        return self.order

    def test_allowed_from_each_status(self):
        expected = {
            'new': ['accepted', 'preparing', 'ready', 'served', 'cancelled'],
            'accepted': ['preparing', 'ready', 'served', 'cancelled'],
            'preparing': ['ready', 'served', 'cancelled'],
            'ready': ['served', 'cancelled'],
            'served': [],
            'cancelled': [],
        }
        for status, allowed in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self.at(status).allowed_next_statuses(), allowed)

    def test_no_backwards(self):
        self.assertFalse(self.at('served').can_transition_to('new'))
        self.assertFalse(self.at('ready').can_transition_to('preparing'))
        self.assertFalse(self.at('accepted').can_transition_to('new'))
        self.assertFalse(self.at('cancelled').can_transition_to('new'))

    def test_same_status_not_a_transition(self):
        self.assertFalse(self.at('preparing').can_transition_to('preparing'))

    def test_paid_order_cannot_be_cancelled(self):
        order = self.at('ready', pay_status='paid')
        self.assertFalse(order.can_transition_to('cancelled'))
        self.assertTrue(order.can_transition_to('served'))


class TransitionEndpointTests(TestCase):
    def setUp(self):
        self.r = make_restaurant()
        self.client.force_login(make_staff(self.r, 'isci'))
        self.order = Order.objects.create(restaurant=self.r, table=make_table(self.r), total=Decimal('5'))

    def post(self, status):
        return self.client.post(
            f'/panel/orders/{self.order.public_id}/status/',
            data=json.dumps({'status': status}), content_type='application/json',
        )

    def set_db(self, **fields):
        Order.objects.filter(pk=self.order.pk).update(**fields)

    def test_full_happy_path(self):
        for status in ['accepted', 'preparing', 'ready', 'served']:
            with self.subTest(status=status):
                self.assertEqual(self.post(status).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')

    def test_served_cannot_go_back_to_new(self):
        self.set_db(status='served')
        resp = self.post('new')
        self.assertEqual(resp.status_code, 409)
        self.assertIn('Verildi', resp.json()['error'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')

    def test_cancelled_is_final(self):
        self.set_db(status='cancelled')
        for status in ['new', 'accepted', 'served']:
            with self.subTest(status=status):
                self.assertEqual(self.post(status).status_code, 409)

    def test_paid_order_cancel_rejected_with_explanation(self):
        self.set_db(status='ready', pay_status='paid')
        resp = self.post('cancelled')
        self.assertEqual(resp.status_code, 409)
        self.assertIn('menecer', resp.json()['error'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')

    def test_stale_status_does_not_overwrite(self):
        # İşçi A köhnə "new" vəziyyətini görür; bu arada işçi B sifarişi "served" edib.
        # Şərtli UPDATE A-nın sorğusunu (new -> accepted) qəbul etmir.
        stale = Order.objects.get(pk=self.order.pk)
        self.set_db(status='served')
        with patch('menu.views.get_object_or_404', return_value=stale):
            resp = self.post('accepted')
        self.assertEqual(resp.status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')

    def test_feed_contains_allowed_next(self):
        self.set_db(status='ready')
        order = self.client.get('/panel/orders/feed/').json()['orders'][0]
        self.assertEqual(order['allowed_next'], ['served', 'cancelled'])

    def test_customer_json_has_no_allowed_next(self):
        self.assertNotIn('allowed_next', self.client.get(f'/o/{self.order.public_id}/json/').json())
