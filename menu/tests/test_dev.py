from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from menu.models import StaffProfile

from .factories import make_restaurant, make_staff, make_table


class DevPagesDisabledByDefaultTests(TestCase):
    """Real konfiqurasiyada (DEBUG=False) dev səhifələri ümumiyyətlə yoxdur."""

    def test_custom_404_page(self):
        resp = self.client.get('/yoxdur/')
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, 'Səhifə tapılmadı', status_code=404)

    def test_root_and_dev_login_are_404(self):
        make_staff(make_restaurant('demo'), 'demo_isci')
        self.assertEqual(self.client.get('/').status_code, 404)
        self.assertEqual(self.client.post('/dev/login/', {'username': 'demo_isci'}).status_code, 404)
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(ROOT_URLCONF='menu.tests.dev_urlconf', DEBUG=True)
class DevPagesTests(TestCase):
    def setUp(self):
        self.demo = make_restaurant('demo')
        self.table = make_table(self.demo, 1)
        self.staff = make_staff(self.demo, 'demo_isci')
        self.manager = make_staff(self.demo, 'demo_menecer', role=StaffProfile.ROLE_MANAGER)

    def test_home_lists_table_links_and_login_buttons(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.table.get_menu_url().replace('&', '&amp;'))
        self.assertContains(resp, 'Menecer kimi daxil ol')
        self.assertContains(resp, 'İşçi kimi daxil ol')

    def test_home_without_demo_shows_hint(self):
        self.demo.delete()
        self.assertContains(self.client.get('/'), 'seed_demo')

    def test_login_as_demo_staff(self):
        resp = self.client.post('/dev/login/', {'username': 'demo_menecer'})
        self.assertRedirects(resp, '/panel/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.manager.pk)

    def test_login_requires_post(self):
        self.assertEqual(self.client.get('/dev/login/').status_code, 405)

    @override_settings(DEBUG=False)
    def test_view_itself_checks_debug(self):
        # URL qoşulu qalsa belə, DEBUG=False olanda view 404 qaytarır.
        self.assertEqual(self.client.get('/').status_code, 404)
        self.assertEqual(self.client.post('/dev/login/', {'username': 'demo_isci'}).status_code, 404)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_remote_address_rejected(self):
        resp = self.client.post('/dev/login/', {'username': 'demo_isci'}, REMOTE_ADDR='203.0.113.5')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.client.get('/', REMOTE_ADDR='203.0.113.5').status_code, 404)

    def test_requests_through_proxy_or_tunnel_rejected(self):
        # Tunel ilə gələn sorğu REMOTE_ADDR=127.0.0.1 olsa da, proksi başlığı daşıyır.
        for header in ('HTTP_X_FORWARDED_FOR', 'HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP'):
            with self.subTest(header=header):
                extra = {header: '203.0.113.5'}
                self.assertEqual(self.client.get('/', **extra).status_code, 404)
                resp = self.client.post('/dev/login/', {'username': 'demo_isci'}, **extra)
                self.assertEqual(resp.status_code, 404)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cannot_login_as_other_restaurant_staff(self):
        make_staff(make_restaurant('real'), 'real_isci')
        self.assertEqual(self.client.post('/dev/login/', {'username': 'real_isci'}).status_code, 404)

    def test_cannot_login_as_superuser_or_admin_staff(self):
        admin = get_user_model().objects.create_superuser('boss', password='parol-12345')
        StaffProfile.objects.create(user=admin, restaurant=self.demo)
        self.assertEqual(self.client.post('/dev/login/', {'username': 'boss'}).status_code, 404)
        self.staff.is_staff = True
        self.staff.save()
        self.assertEqual(self.client.post('/dev/login/', {'username': 'demo_isci'}).status_code, 404)

    def test_unknown_or_empty_username(self):
        self.assertEqual(self.client.post('/dev/login/', {'username': 'yoxdur'}).status_code, 404)
        self.assertEqual(self.client.post('/dev/login/').status_code, 404)
