from django.test import TestCase

from menu.models import ScanEvent

from .factories import make_item, make_restaurant, make_table


class MenuViewTests(TestCase):
    def setUp(self):
        self.r = make_restaurant('dadli')
        self.table = make_table(self.r, 3)
        self.item = make_item(self.r, 'Plov')
        self.off_item = make_item(self.r, 'Dolma', is_available=False)

    def url(self, **params):
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'/r/dadli/?{query}' if query else '/r/dadli/'

    def test_unknown_slug_404(self):
        self.assertEqual(self.client.get('/r/yoxdur/').status_code, 404)

    def test_menu_without_table_shows_items_but_no_order_buttons(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Plov')
        self.assertIsNone(resp.context['table'])
        self.assertNotContains(resp, 'id="cart"')

    def test_valid_token_sets_table_and_shows_cart(self):
        resp = self.client.get(self.url(t=3, k=self.table.token, s='n'))
        self.assertEqual(resp.context['table'], self.table)
        self.assertContains(resp, 'id="cart"')
        self.assertContains(resp, 'Masa 3')

    def test_wrong_token_does_not_set_table(self):
        resp = self.client.get(self.url(t=3, k='sehv-token', s='n'))
        self.assertIsNone(resp.context['table'])
        self.assertNotContains(resp, 'id="cart"')

    def test_garbage_table_number(self):
        resp = self.client.get(self.url(t='abc', k=self.table.token))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['table'])

    def test_token_of_other_restaurant_table_rejected(self):
        other = make_restaurant('diger')
        other_table = make_table(other, 3)
        resp = self.client.get(self.url(t=3, k=other_table.token))
        self.assertIsNone(resp.context['table'])

    def test_unavailable_item_marked(self):
        resp = self.client.get(self.url(t=3, k=self.table.token))
        self.assertContains(resp, 'Bitib')

    def test_scan_event_recorded_with_source_and_table(self):
        self.client.get(self.url(t=3, k=self.table.token, s='q'), HTTP_USER_AGENT='TestPhone')
        ev = ScanEvent.objects.get()
        self.assertEqual(ev.restaurant, self.r)
        self.assertEqual(ev.table, self.table)
        self.assertEqual(ev.source, 'q')
        self.assertEqual(ev.user_agent, 'TestPhone')

    def test_unknown_source_recorded_as_question_mark(self):
        self.client.get(self.url(s='zzz'))
        self.assertEqual(ScanEvent.objects.get().source, '?')

    def test_csrf_cookie_set(self):
        resp = self.client.get(self.url(t=3, k=self.table.token))
        self.assertIn('csrftoken', resp.cookies)

    def test_expired_subscription_returns_503_and_no_scan(self):
        expired = make_restaurant('kohne', days_left=-1)
        resp = self.client.get('/r/kohne/')
        self.assertEqual(resp.status_code, 503)
        self.assertContains(resp, 'əlçatmazdır', status_code=503)
        self.assertFalse(ScanEvent.objects.filter(restaurant=expired).exists())

    def test_inactive_restaurant_returns_503(self):
        make_restaurant('sonuk', is_active=False)
        self.assertEqual(self.client.get('/r/sonuk/').status_code, 503)

    def test_other_restaurants_items_not_shown(self):
        make_item(make_restaurant('diger'), 'GizliYemek')
        self.assertNotContains(self.client.get(self.url()), 'GizliYemek')

    def test_item_name_is_escaped(self):
        make_item(self.r, '<script>alert(1)</script>')
        resp = self.client.get(self.url(t=3, k=self.table.token))
        self.assertNotContains(resp, '<script>alert(1)</script>')
        self.assertContains(resp, '&lt;script&gt;')


class ServiceWorkerTests(TestCase):
    def test_sw_served_from_root(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/javascript')
        self.assertEqual(resp['Service-Worker-Allowed'], '/')
        self.assertContains(resp, "method !== 'GET'")
