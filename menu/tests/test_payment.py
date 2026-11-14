import json
from decimal import Decimal

from django.test import Client, TestCase

from menu.models import Order, StaffProfile
from menu.services import OrderError, mark_paid_at_table

from .factories import make_restaurant, make_staff, make_table


class TablePaymentTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.staff = make_staff(self.r, 'isci')
        self.manager = make_staff(self.r, 'menecer', role=StaffProfile.ROLE_MANAGER)
        self.order = Order.objects.create(restaurant=self.r, table=make_table(self.r, 1), total=Decimal('20.00'))
        self.client.force_login(self.staff)

    def pay(self, order=None, via='cash', client=None):
        order = order or self.order
        return (client or self.client).post(
            f'/panel/orders/{order.public_id}/pay/', data=json.dumps({'via': via}), content_type='application/json'
        )

    def unpay(self, client=None):
        return (client or self.client).post(f'/panel/orders/{self.order.public_id}/unpay/')

    def as_manager(self):
        client = Client()
        client.force_login(self.manager)
        return client

    # --- Ödəniş qeydi ---

    def test_staff_marks_cash_payment(self):
        resp = self.pay(via='cash')
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'paid')
        self.assertEqual(self.order.paid_via, 'cash')
        self.assertEqual(self.order.paid_by, self.staff)
        self.assertIsNotNone(self.order.paid_at)
        data = resp.json()
        self.assertEqual(data['pay_status'], 'paid')
        self.assertEqual(data['paid_via_display'], 'Nağd')
        self.assertEqual(data['paid_by'], 'isci')

    def test_terminal_payment_via_form_post(self):
        resp = self.client.post(f'/panel/orders/{self.order.public_id}/pay/', {'via': 'terminal'})
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_via, 'terminal')

    def test_payment_does_not_change_order_status(self):
        self.pay()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'new')

    def test_invalid_via_rejected(self):
        for via in ['crypto', '', None, 5]:
            with self.subTest(via=via):
                self.assertEqual(self.pay(via=via).status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'unpaid')

    def test_double_payment_rejected_and_first_record_kept(self):
        self.assertEqual(self.pay(via='cash').status_code, 200)
        resp = self.pay(via='terminal', client=self.as_manager())
        self.assertEqual(resp.status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_via, 'cash')
        self.assertEqual(self.order.paid_by, self.staff)

    def test_stale_object_cannot_double_pay(self):
        # İki işçi eyni sifarişi eyni anda açıb: hər ikisinin əlində köhnə "unpaid" obyekt var.
        stale_a = Order.objects.get(pk=self.order.pk)
        stale_b = Order.objects.get(pk=self.order.pk)
        mark_paid_at_table(stale_a, self.staff, 'cash')
        with self.assertRaises(OrderError):
            mark_paid_at_table(stale_b, self.manager, 'terminal')
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_by, self.staff)

    def test_cancelled_order_cannot_be_paid(self):
        Order.objects.filter(pk=self.order.pk).update(status='cancelled')
        self.assertEqual(self.pay().status_code, 409)

    def test_online_order_cannot_be_marked_paid_from_panel(self):
        Order.objects.filter(pk=self.order.pk).update(pay_method='online', pay_status='pending')
        self.assertEqual(self.pay().status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'pending')

    def test_failed_table_payment_can_be_retried(self):
        Order.objects.filter(pk=self.order.pk).update(pay_status='failed')
        self.assertEqual(self.pay().status_code, 200)

    def test_other_restaurants_order_404(self):
        other = make_restaurant('diger')
        foreign = Order.objects.create(restaurant=other, table=make_table(other, 1), total=Decimal('5'))
        self.assertEqual(self.pay(order=foreign).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.pay_status, 'unpaid')

    def test_pay_requires_login_post_and_csrf(self):
        self.assertEqual(Client().post(f'/panel/orders/{self.order.public_id}/pay/').status_code, 302)
        self.assertEqual(self.client.get(f'/panel/orders/{self.order.public_id}/pay/').status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(self.pay(client=csrf_client).status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'unpaid')

    def test_feed_contains_payment_info(self):
        self.pay(via='terminal')
        order = self.client.get('/panel/orders/feed/').json()['orders'][0]
        self.assertEqual(order['pay_status'], 'paid')
        self.assertEqual(order['paid_via_display'], 'Terminal')
        self.assertEqual(order['paid_by'], 'isci')
        self.assertEqual(order['pay_method'], 'table')

    def test_customer_json_shows_paid_but_not_staff_name(self):
        self.pay()
        data = Client().get(f'/o/{self.order.public_id}/json/').json()
        self.assertEqual(data['pay_status_display'], 'Ödənilib')
        self.assertNotIn('paid_by', data)

    # --- Geri alma (yalnız menecer) ---

    def test_staff_cannot_undo_payment(self):
        self.pay()
        self.assertEqual(self.unpay().status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'paid')

    def test_manager_can_undo_payment(self):
        self.pay()
        resp = self.unpay(client=self.as_manager())
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.pay_status, 'unpaid')
        self.assertEqual(self.order.paid_via, '')
        self.assertIsNone(self.order.paid_at)
        self.assertIsNone(self.order.paid_by)

    def test_undo_unpaid_order_rejected(self):
        self.assertEqual(self.unpay(client=self.as_manager()).status_code, 409)

    def test_manager_cannot_undo_online_payment(self):
        Order.objects.filter(pk=self.order.pk).update(pay_method='online', pay_status='paid')
        self.assertEqual(self.unpay(client=self.as_manager()).status_code, 409)

    def test_panel_config_reflects_role(self):
        self.assertContains(self.client.get('/panel/'), '"isManager": false')
        self.assertContains(self.as_manager().get('/panel/'), '"isManager": true')
