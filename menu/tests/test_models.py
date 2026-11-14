from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from menu.models import Order, OrderItem, Restaurant, Table

from .factories import make_item, make_restaurant, make_table


class RestaurantServiceTests(TestCase):
    def test_active_with_future_subscription(self):
        self.assertTrue(make_restaurant(days_left=10).is_service_active())

    def test_last_day_of_subscription_is_still_active(self):
        self.assertTrue(make_restaurant(days_left=0).is_service_active())

    def test_expired_subscription(self):
        self.assertFalse(make_restaurant(days_left=-1).is_service_active())

    def test_inactive_restaurant(self):
        self.assertFalse(make_restaurant(is_active=False).is_service_active())

    def test_no_subscription_date_means_inactive(self):
        r = Restaurant.objects.create(name='X', slug='x', subscription_until=None)
        self.assertFalse(r.is_service_active())


class TableTokenTests(TestCase):
    def test_each_table_gets_unique_token(self):
        r = make_restaurant()
        tokens = {make_table(r, n).token for n in range(1, 21)}
        self.assertEqual(len(tokens), 20)
        self.assertTrue(all(len(t) >= 10 for t in tokens))

    def test_table_number_unique_per_restaurant(self):
        r = make_restaurant()
        make_table(r, 1)
        with self.assertRaises(IntegrityError):
            Table.objects.create(restaurant=r, number=1)

    def test_same_number_allowed_in_other_restaurant(self):
        make_table(make_restaurant('a'), 1)
        make_table(make_restaurant('b'), 1)  # xəta olmamalıdır

    def test_regenerate_token(self):
        t = make_table(make_restaurant())
        old = t.token
        t.regenerate_token()
        t.refresh_from_db()
        self.assertNotEqual(t.token, old)

    def test_menu_url(self):
        t = make_table(make_restaurant('dadli'), 5)
        self.assertEqual(t.get_menu_url('q'), f'/r/dadli/?t=5&k={t.token}&s=q')


class OrderItemSnapshotTests(TestCase):
    def test_line_total_and_snapshot_survive_menu_changes(self):
        r = make_restaurant()
        item = make_item(r, price='10.00')
        order = Order.objects.create(restaurant=r, table=make_table(r), total=Decimal('20.00'))
        line = OrderItem.objects.create(order=order, menu_item=item, name=item.name, unit_price=item.price, quantity=2)
        item.price = Decimal('99.00')
        item.save()
        item.delete()
        line.refresh_from_db()
        self.assertIsNone(line.menu_item)
        self.assertEqual(line.unit_price, Decimal('10.00'))
        self.assertEqual(line.line_total, Decimal('20.00'))

    def test_public_id_is_uuid_and_unique(self):
        r = make_restaurant()
        t = make_table(r)
        a = Order.objects.create(restaurant=r, table=t)
        b = Order.objects.create(restaurant=r, table=t)
        self.assertNotEqual(a.public_id, b.public_id)
        self.assertGreater(b.created_at, timezone.now() - timedelta(minutes=1))
