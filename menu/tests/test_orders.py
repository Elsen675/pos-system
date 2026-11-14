import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from menu.models import Order

from .factories import make_item, make_restaurant, make_table


class OrderCreateTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.table = make_table(self.r, 2)
        self.plov = make_item(self.r, 'Plov', '12.50')
        self.cay = make_item(self.r, 'Çay', '2.00')

    def post(self, payload, slug='dadli', client=None):
        client = client or self.client
        return client.post(f'/r/{slug}/order/', data=json.dumps(payload), content_type='application/json')

    def payload(self, **overrides):
        data = {
            'table': 2,
            'token': self.table.token,
            'items': [{'id': self.plov.id, 'qty': 2}, {'id': self.cay.id, 'qty': 3}],
            'note': 'Soğansız',
        }
        data.update(overrides)
        return data

    def test_creates_order_with_server_side_total(self):
        resp = self.post(self.payload())
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal('31.00'))  # 2*12.50 + 3*2.00
        self.assertEqual(order.table, self.table)
        self.assertEqual(order.restaurant, self.r)
        self.assertEqual(order.status, 'new')
        self.assertEqual(order.pay_status, 'unpaid')
        self.assertEqual(order.note, 'Soğansız')
        self.assertEqual(resp.json()['status_url'], f'/o/{order.public_id}/')

    def test_client_supplied_prices_are_ignored(self):
        items = [{'id': self.plov.id, 'qty': 1, 'price': '0.01'}]
        self.post(self.payload(items=items, total='0.01'))
        self.assertEqual(Order.objects.get().total, Decimal('12.50'))

    def test_snapshot_copies_name_and_price(self):
        self.post(self.payload(items=[{'id': self.plov.id, 'qty': 1}]))
        self.plov.price = Decimal('50.00')
        self.plov.name = 'Yeni ad'
        self.plov.save()
        line = Order.objects.get().items.get()
        self.assertEqual(line.name, 'Plov')
        self.assertEqual(line.unit_price, Decimal('12.50'))

    def test_duplicate_lines_are_merged(self):
        items = [{'id': self.plov.id, 'qty': 1}, {'id': self.plov.id, 'qty': 2}]
        self.post(self.payload(items=items))
        line = Order.objects.get().items.get()
        self.assertEqual(line.quantity, 3)

    def test_missing_token_rejected(self):
        resp = self.post(self.payload(token=None))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Order.objects.exists())

    def test_wrong_token_rejected(self):
        self.assertEqual(self.post(self.payload(token='saxta')).status_code, 403)

    def test_token_from_other_table_rejected(self):
        other = make_table(self.r, 5)
        self.assertEqual(self.post(self.payload(token=other.token)).status_code, 403)

    def test_item_from_other_restaurant_rejected(self):
        foreign = make_item(make_restaurant('diger'), 'Yad', '1.00')
        resp = self.post(self.payload(items=[{'id': foreign.id, 'qty': 1}]))
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_unavailable_item_rejected(self):
        self.plov.is_available = False
        self.plov.save()
        self.assertEqual(self.post(self.payload()).status_code, 409)

    def test_invalid_items(self):
        bad_cases = [
            [],
            'plov',
            [{'id': self.plov.id, 'qty': 0}],
            [{'id': self.plov.id, 'qty': -3}],
            [{'id': self.plov.id, 'qty': '2'}],
            [{'id': str(self.plov.id), 'qty': 1}],
            [{'id': self.plov.id, 'qty': True}],
            [{'id': self.plov.id, 'qty': 21}],
            [{'id': self.plov.id, 'qty': 1.5}],
            ['x'],
        ]
        for items in bad_cases:
            with self.subTest(items=items):
                self.assertEqual(self.post(self.payload(items=items)).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_invalid_json(self):
        resp = self.client.post('/r/dadli/order/', data='{yox', content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_non_object_json(self):
        self.assertEqual(self.post([1, 2]).status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get('/r/dadli/order/').status_code, 405)

    def test_note_is_trimmed_to_max_length(self):
        self.post(self.payload(note='a' * 1000))
        self.assertEqual(len(Order.objects.get().note), 500)

    def test_rate_limit_three_new_orders_per_10_minutes(self):
        for _ in range(3):
            self.assertEqual(self.post(self.payload()).status_code, 201)
        resp = self.post(self.payload())
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(Order.objects.count(), 3)

    def test_rate_limit_counts_only_new_orders(self):
        for _ in range(3):
            self.post(self.payload())
        Order.objects.update(status='accepted')
        self.assertEqual(self.post(self.payload()).status_code, 201)

    def test_rate_limit_window_expires(self):
        for _ in range(3):
            self.post(self.payload())
        Order.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.post(self.payload()).status_code, 201)

    def test_rate_limit_is_per_table(self):
        other = make_table(self.r, 7)
        for _ in range(3):
            self.post(self.payload())
        self.assertEqual(self.post(self.payload(table=7, token=other.token)).status_code, 201)

    def test_expired_restaurant_rejects_orders(self):
        self.r.subscription_until = timezone.localdate() - timedelta(days=1)
        self.r.save()
        self.assertEqual(self.post(self.payload()).status_code, 503)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(self.payload(), client=client).status_code, 403)
        self.assertFalse(Order.objects.exists())

    def test_csrf_token_from_menu_page_works(self):
        client = Client(enforce_csrf_checks=True)
        client.get(f'/r/dadli/?t=2&k={self.table.token}')
        token = client.cookies['csrftoken'].value
        resp = client.post(
            '/r/dadli/order/', data=json.dumps(self.payload()),
            content_type='application/json', HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(resp.status_code, 201)


class OrderStatusPageTests(TestCase):
    def setUp(self):
        r = make_restaurant()
        self.order = Order.objects.create(restaurant=r, table=make_table(r, 4), total=Decimal('5.00'), note='<b>x</b>')

    def test_status_page(self):
        resp = self.client.get(f'/o/{self.order.public_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Masa 4')
        self.assertContains(resp, 'Yeni')
        self.assertNotContains(resp, '<b>x</b>')

    def test_status_json(self):
        self.order.status = 'preparing'
        self.order.save()
        data = self.client.get(f'/o/{self.order.public_id}/json/').json()
        self.assertEqual(data['status'], 'preparing')
        self.assertEqual(data['status_display'], 'Hazırlanır')
        self.assertEqual(data['total'], '5.00')

    def test_unknown_uuid_404(self):
        self.assertEqual(self.client.get(f'/o/{uuid.uuid4()}/').status_code, 404)
        self.assertEqual(self.client.get(f'/o/{uuid.uuid4()}/json/').status_code, 404)
