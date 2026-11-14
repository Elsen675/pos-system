from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from menu.models import Order, OrderItem, ScanEvent, ServiceCall, StaffProfile
from menu.reports import close_table_bill, daily_report, day_bounds

from .factories import make_restaurant, make_staff, make_table


def make_order(restaurant, table, total, lines=(), **fields):
    order = Order.objects.create(restaurant=restaurant, table=table, total=Decimal(total), **fields)
    for name, price, qty in lines:
        OrderItem.objects.create(order=order, name=name, unit_price=Decimal(price), quantity=qty)
    return order


class TableBillTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.t1 = make_table(self.r, 1)
        self.t2 = make_table(self.r, 2)
        self.user = make_staff(self.r, 'isci')
        self.client.force_login(self.user)
        self.a = make_order(self.r, self.t1, '10.00', [('Plov', '10.00', 1)])
        self.b = make_order(self.r, self.t1, '4.00', [('Çay', '2.00', 2)], status='served')
        self.c = make_order(self.r, self.t2, '7.00')

    def close(self, number, orders, via='cash'):
        data = {'via': via, 'order': [str(o.public_id) for o in orders]}
        return self.client.post(f'/panel/tables/{number}/close/', data)

    def test_tables_page_groups_orders_and_sums(self):
        resp = self.client.get('/panel/tables/')
        self.assertEqual(resp.status_code, 200)
        bills = resp.context['bills']
        self.assertEqual(bills[self.t1]['total'], Decimal('14.00'))
        self.assertEqual(len(bills[self.t1]['orders']), 2)
        self.assertEqual(bills[self.t2]['total'], Decimal('7.00'))
        self.assertContains(resp, '14,00 ₼')

    def test_paid_cancelled_online_excluded(self):
        make_order(self.r, self.t1, '50', pay_status='paid')
        make_order(self.r, self.t1, '50', status='cancelled')
        make_order(self.r, self.t1, '50', pay_method='online', pay_status='pending')
        bills = self.client.get('/panel/tables/').context['bills']
        self.assertEqual(bills[self.t1]['total'], Decimal('14.00'))

    def test_close_bill_pays_all_seen_orders(self):
        resp = self.close(1, [self.a, self.b], via='terminal')
        self.assertRedirects(resp, '/panel/tables/', fetch_redirect_response=False)
        for order in (self.a, self.b):
            order.refresh_from_db()
            self.assertEqual(order.pay_status, 'paid')
            self.assertEqual(order.paid_via, 'terminal')
            self.assertEqual(order.paid_by, self.user)
        self.c.refresh_from_db()
        self.assertEqual(self.c.pay_status, 'unpaid')  # başqa masa toxunulmur

    def test_new_order_arriving_after_view_is_not_paid(self):
        late = make_order(self.r, self.t1, '30.00')  # ofisiant bunu görmədi
        self.close(1, [self.a, self.b])
        late.refresh_from_db()
        self.assertEqual(late.pay_status, 'unpaid')

    def test_changed_bill_rolls_back_everything(self):
        Order.objects.filter(pk=self.b.pk).update(pay_status='paid')  # başqa işçi ödədi
        resp = self.close(1, [self.a, self.b])
        self.assertEqual(resp.status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.pay_status, 'unpaid')  # rollback: heç nə yazılmadı

    def test_cannot_close_with_other_tables_order(self):
        with self.assertRaises(Exception):
            close_table_bill(self.r, 1, [self.a.public_id, self.c.public_id], self.user, 'cash')
        self.a.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual((self.a.pay_status, self.c.pay_status), ('unpaid', 'unpaid'))

    def test_other_restaurant_orders_untouched(self):
        other = make_restaurant('diger')
        foreign = make_order(other, make_table(other, 1), '5')
        self.close(1, [foreign])
        foreign.refresh_from_db()
        self.assertEqual(foreign.pay_status, 'unpaid')

    def test_invalid_input(self):
        self.client.post('/panel/tables/1/close/', {'via': 'cash', 'order': ['zibil']})
        self.close(1, [self.a], via='bitcoin')
        self.client.post('/panel/tables/1/close/', {'via': 'cash'})
        self.close(99, [self.a])
        self.a.refresh_from_db()
        self.assertEqual(self.a.pay_status, 'unpaid')

    def test_closing_bill_resolves_bill_call(self):
        call = ServiceCall.objects.create(restaurant=self.r, table=self.t1, kind='bill')
        waiter = ServiceCall.objects.create(restaurant=self.r, table=self.t1, kind='waiter')
        self.close(1, [self.a, self.b])
        call.refresh_from_db()
        waiter.refresh_from_db()
        self.assertFalse(call.is_open)
        self.assertTrue(waiter.is_open)

    def test_close_requires_post_and_login(self):
        self.assertEqual(self.client.get('/panel/tables/1/close/').status_code, 405)
        self.assertEqual(Client().get('/panel/tables/').status_code, 302)


class HistoryTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.t = make_table(self.r, 3)
        self.client.force_login(make_staff(self.r, 'isci'))
        self.today_order = make_order(self.r, self.t, '5', [('Plov', '5', 1)])
        self.old = make_order(self.r, self.t, '9', [('Dolma', '9', 1)])
        Order.objects.filter(pk=self.old.pk).update(created_at=timezone.now() - timedelta(days=2))

    def test_today_by_default(self):
        resp = self.client.get('/panel/history/')
        self.assertEqual(list(resp.context['orders']), [self.today_order])

    def test_other_day(self):
        day = (timezone.localdate() - timedelta(days=2)).isoformat()
        resp = self.client.get(f'/panel/history/?date={day}')
        self.assertEqual(list(resp.context['orders']), [self.old])
        self.assertContains(resp, 'Dolma')

    def test_status_filter_and_bad_values(self):
        Order.objects.filter(pk=self.today_order.pk).update(status='served')
        self.assertEqual(len(self.client.get('/panel/history/?status=served').context['orders']), 1)
        self.assertEqual(len(self.client.get('/panel/history/?status=new').context['orders']), 0)
        resp = self.client.get('/panel/history/?status=zzz&date=bad')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['orders']), 1)

    def test_only_own_restaurant(self):
        other = make_restaurant('diger')
        make_order(other, make_table(other, 1), '1', [('Yad yemək', '1', 1)])
        self.assertNotContains(self.client.get('/panel/history/'), 'Yad yemək')


class DailyReportTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.t = make_table(self.r, 1)
        self.manager = make_staff(self.r, 'menecer', role=StaffProfile.ROLE_MANAGER)
        self.client.force_login(self.manager)
        make_order(self.r, self.t, '20.00', [('Plov', '10.00', 2)], pay_status='paid', paid_via='cash')
        make_order(self.r, self.t, '10.00', [('Plov', '10.00', 1)], pay_status='paid', paid_via='terminal')
        make_order(self.r, self.t, '6.00', [('Çay', '2.00', 3)])
        make_order(self.r, self.t, '99.00', [('Kabab', '99.00', 1)], status='cancelled')

    def test_report_numbers(self):
        rep = daily_report(self.r, timezone.localdate())
        self.assertEqual(rep['order_count'], 3)
        self.assertEqual(rep['cancelled_count'], 1)
        self.assertEqual(rep['revenue'], Decimal('36.00'))
        self.assertEqual(rep['average'], Decimal('12.00'))
        self.assertEqual(rep['paid_cash'], Decimal('20.00'))
        self.assertEqual(rep['paid_terminal'], Decimal('10.00'))
        self.assertEqual(rep['paid'], Decimal('30.00'))
        self.assertEqual(rep['unpaid'], Decimal('6.00'))
        top = {row['name']: (row['qty'], row['amount']) for row in rep['top_items']}
        self.assertEqual(top['Plov'], (3, Decimal('30.00')))
        self.assertEqual(top['Çay'], (3, Decimal('6.00')))
        self.assertNotIn('Kabab', top)  # ləğv edilən sayılmır
        self.assertEqual(sum(h['count'] for h in rep['hours']), 3)

    def test_scans_and_calls(self):
        ScanEvent.objects.create(restaurant=self.r, source='n')
        ScanEvent.objects.create(restaurant=self.r, source='n')
        ScanEvent.objects.create(restaurant=self.r, source='q')
        ServiceCall.objects.create(restaurant=self.r, table=self.t, kind='bill')
        rep = daily_report(self.r, timezone.localdate())
        self.assertEqual((rep['scans_nfc'], rep['scans_qr'], rep['calls_bill']), (2, 1, 1))

    def test_empty_day(self):
        rep = daily_report(self.r, timezone.localdate() - timedelta(days=5))
        self.assertEqual(rep['order_count'], 0)
        self.assertEqual(rep['average'], Decimal('0'))

    def test_day_bounds_use_baku_time(self):
        # 23:30 Bakı vaxtı hələ həmin gündür (UTC-də 19:30).
        day = timezone.localdate()
        start, end = day_bounds(day)
        late = timezone.make_aware(datetime.combine(day, time(23, 30)))
        self.assertTrue(start <= late < end)
        self.assertEqual(end - start, timedelta(days=1))

    def test_report_page_manager_only(self):
        resp = self.client.get('/panel/report/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '36,00 ₼')
        staff = Client()
        staff.force_login(make_staff(self.r, 'isci'))
        self.assertEqual(staff.get('/panel/report/').status_code, 403)
        self.assertNotContains(staff.get('/panel/'), 'href="/panel/report/"')

    def test_report_only_own_restaurant(self):
        other = make_restaurant('diger')
        make_order(other, make_table(other, 1), '1000', [('Yad', '1000', 1)])
        rep = daily_report(self.r, timezone.localdate())
        self.assertEqual(rep['revenue'], Decimal('36.00'))
