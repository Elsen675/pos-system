import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from menu.models import ServiceCall

from .factories import make_restaurant, make_staff, make_table


class ServiceCallCreateTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.table = make_table(self.r, 4)

    def call(self, **overrides):
        payload = {'table': 4, 'token': self.table.token, 'kind': 'waiter'}
        payload.update(overrides)
        return self.client.post('/r/dadli/call/', data=json.dumps(payload), content_type='application/json')

    def test_waiter_call_created(self):
        resp = self.call()
        self.assertEqual(resp.status_code, 201)
        call = ServiceCall.objects.get()
        self.assertEqual((call.table, call.kind, call.restaurant), (self.table, 'waiter', self.r))
        self.assertTrue(call.is_open)

    def test_bill_with_pay_hint(self):
        self.call(kind='bill', pay_hint='card')
        self.assertEqual(ServiceCall.objects.get().pay_hint, 'card')

    def test_pay_hint_ignored_for_waiter(self):
        self.call(kind='waiter', pay_hint='cash')
        self.assertEqual(ServiceCall.objects.get().pay_hint, '')

    def test_repeated_press_does_not_duplicate(self):
        self.assertEqual(self.call().status_code, 201)
        resp = self.call()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['created'])
        self.assertEqual(ServiceCall.objects.count(), 1)

    def test_repeated_bill_updates_pay_hint(self):
        self.call(kind='bill', pay_hint='cash')
        self.call(kind='bill', pay_hint='card')
        self.assertEqual(ServiceCall.objects.get().pay_hint, 'card')

    def test_waiter_and_bill_are_separate(self):
        self.call(kind='waiter')
        self.call(kind='bill')
        self.assertEqual(ServiceCall.objects.count(), 2)

    def test_new_call_allowed_after_resolve(self):
        self.call()
        ServiceCall.objects.update(resolved_at=timezone.now())
        self.assertEqual(self.call().status_code, 201)

    def test_rate_limit(self):
        for _ in range(6):
            self.assertEqual(self.call().status_code, 201)
            ServiceCall.objects.update(resolved_at=timezone.now())
        self.assertEqual(self.call().status_code, 429)

    def test_rate_limit_window_expires(self):
        for _ in range(6):
            self.call()
            ServiceCall.objects.update(resolved_at=timezone.now())
        ServiceCall.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.call().status_code, 201)

    def test_wrong_or_missing_token(self):
        self.assertEqual(self.call(token='saxta').status_code, 403)
        self.assertEqual(self.call(token=None).status_code, 403)
        self.assertFalse(ServiceCall.objects.exists())

    def test_invalid_kind_and_pay_hint(self):
        self.assertEqual(self.call(kind='dance').status_code, 400)
        self.assertEqual(self.call(kind='bill', pay_hint='crypto').status_code, 400)

    def test_bad_json(self):
        resp = self.client.post('/r/dadli/call/', data='{x', content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post('/r/dadli/call/', data='[1]', content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_expired_restaurant(self):
        self.r.subscription_until = timezone.localdate() - timedelta(days=1)
        self.r.save()
        self.assertEqual(self.call().status_code, 503)

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        resp = client.post('/r/dadli/call/', data=json.dumps({'table': 4, 'token': self.table.token, 'kind': 'waiter'}),
                           content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_menu_shows_call_buttons_only_with_table(self):
        self.assertNotContains(self.client.get('/r/dadli/'), 'Ofisiantı çağır')
        self.assertContains(self.client.get(f'/r/dadli/?t=4&k={self.table.token}'), 'Ofisiantı çağır')


class ServiceCallPanelTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.table = make_table(self.r, 4)
        self.user = make_staff(self.r, 'isci')
        self.client.force_login(self.user)
        self.call = ServiceCall.objects.create(restaurant=self.r, table=self.table, kind='bill', pay_hint='cash')
        other = make_restaurant('diger')
        self.foreign = ServiceCall.objects.create(restaurant=other, table=make_table(other, 1), kind='waiter')

    def test_feed_contains_only_own_open_calls(self):
        calls = self.client.get('/panel/orders/feed/').json()['calls']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['table'], 4)
        self.assertEqual(calls[0]['kind_display'], 'Hesab istəyir')
        self.assertEqual(calls[0]['pay_hint_display'], 'Nağd')

    def test_resolve(self):
        resp = self.client.post(f'/panel/calls/{self.call.pk}/resolve/')
        self.assertEqual(resp.status_code, 200)
        self.call.refresh_from_db()
        self.assertFalse(self.call.is_open)
        self.assertEqual(self.call.resolved_by, self.user)
        self.assertEqual(self.client.get('/panel/orders/feed/').json()['calls'], [])

    def test_double_resolve_keeps_first(self):
        self.client.post(f'/panel/calls/{self.call.pk}/resolve/')
        first = ServiceCall.objects.get(pk=self.call.pk).resolved_at
        other = Client()
        other.force_login(make_staff(self.r, 'isci2'))
        self.assertEqual(other.post(f'/panel/calls/{self.call.pk}/resolve/').status_code, 200)
        self.call.refresh_from_db()
        self.assertEqual(self.call.resolved_at, first)
        self.assertEqual(self.call.resolved_by, self.user)

    def test_cannot_resolve_other_restaurants_call(self):
        self.assertEqual(self.client.post(f'/panel/calls/{self.foreign.pk}/resolve/').status_code, 404)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_open)

    def test_resolve_requires_login_and_post(self):
        self.assertEqual(Client().post(f'/panel/calls/{self.call.pk}/resolve/').status_code, 302)
        self.assertEqual(self.client.get(f'/panel/calls/{self.call.pk}/resolve/').status_code, 405)
