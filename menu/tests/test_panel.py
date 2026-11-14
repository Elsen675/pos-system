import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from menu.models import Order

from .factories import make_restaurant, make_staff, make_table


class PanelTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.other = make_restaurant('diger')
        self.user = make_staff(self.r, 'isci')
        self.own_order = Order.objects.create(restaurant=self.r, table=make_table(self.r, 1), total=Decimal('3'))
        self.foreign_order = Order.objects.create(
            restaurant=self.other, table=make_table(self.other, 1), total=Decimal('9')
        )
        self.client.force_login(self.user)

    def set_status(self, order, status, client=None, as_json=True):
        client = client or self.client
        url = f'/panel/orders/{order.public_id}/status/'
        if as_json:
            return client.post(url, data=json.dumps({'status': status}), content_type='application/json')
        return client.post(url, {'status': status})

    def test_login_required(self):
        anon = Client()
        for url in ['/panel/', '/panel/orders/feed/']:
            resp = anon.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp['Location'].startswith('/accounts/login/'))

    def test_user_without_profile_forbidden(self):
        user = get_user_model().objects.create_user('yad', password='parol-12345')
        client = Client()
        client.force_login(user)
        self.assertEqual(client.get('/panel/').status_code, 403)
        self.assertEqual(client.get('/panel/orders/feed/').status_code, 403)

    def test_panel_page(self):
        resp = self.client.get('/panel/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dadli')

    def test_feed_only_contains_own_restaurant(self):
        data = self.client.get('/panel/orders/feed/').json()
        ids = [o['id'] for o in data['orders']]
        self.assertEqual(ids, [str(self.own_order.public_id)])
        self.assertEqual(data['orders'][0]['table'], 1)

    def test_feed_hides_old_finished_orders(self):
        self.own_order.status = 'served'
        self.own_order.save()
        Order.objects.filter(pk=self.own_order.pk).update(updated_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(self.client.get('/panel/orders/feed/').json()['orders'], [])

    def test_feed_shows_recently_finished(self):
        self.set_status(self.own_order, 'served')
        self.assertEqual(len(self.client.get('/panel/orders/feed/').json()['orders']), 1)

    def test_change_status_json(self):
        resp = self.set_status(self.own_order, 'accepted')
        self.assertEqual(resp.status_code, 200)
        self.own_order.refresh_from_db()
        self.assertEqual(self.own_order.status, 'accepted')

    def test_change_status_form(self):
        self.assertEqual(self.set_status(self.own_order, 'ready', as_json=False).status_code, 200)
        self.own_order.refresh_from_db()
        self.assertEqual(self.own_order.status, 'ready')

    def test_cannot_change_other_restaurants_order(self):
        resp = self.set_status(self.foreign_order, 'cancelled')
        self.assertEqual(resp.status_code, 404)
        self.foreign_order.refresh_from_db()
        self.assertEqual(self.foreign_order.status, 'new')

    def test_invalid_status(self):
        self.assertEqual(self.set_status(self.own_order, 'hacked').status_code, 400)

    def test_status_change_requires_post(self):
        self.assertEqual(self.client.get(f'/panel/orders/{self.own_order.public_id}/status/').status_code, 405)

    def test_status_change_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self.set_status(self.own_order, 'accepted', client=client).status_code, 403)

    def test_expired_restaurant_panel_disabled(self):
        self.r.subscription_until = timezone.localdate() - timedelta(days=1)
        self.r.save()
        self.assertEqual(self.client.get('/panel/').status_code, 503)
        self.assertEqual(self.set_status(self.own_order, 'accepted').status_code, 503)


class LoginPageTests(TestCase):
    def test_login_page_renders(self):
        resp = self.client.get('/accounts/login/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Daxil ol')

    def test_login_redirects_to_panel(self):
        make_staff(make_restaurant(), 'isci', 'parol-12345')
        resp = self.client.post('/accounts/login/', {'username': 'isci', 'password': 'parol-12345'})
        self.assertRedirects(resp, '/panel/', fetch_redirect_response=False)
