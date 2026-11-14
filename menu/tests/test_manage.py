import shutil
import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from menu.forms import MAX_IMAGE_SIZE_MB
from menu.models import Category, MenuItem, Order, OrderItem, StaffProfile

from .factories import make_item, make_restaurant, make_staff, make_table

TEMP_MEDIA = tempfile.mkdtemp()


def png_file(name='plov.png', size=(20, 20)):
    buf = BytesIO()
    Image.new('RGB', size, (200, 80, 40)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class MenuManageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.r = make_restaurant('dadli')
        self.cat = Category.objects.create(restaurant=self.r, name='Əsas')
        self.item = make_item(self.r, 'Plov', '12.50', category=self.cat)
        self.manager = make_staff(self.r, 'menecer', role=StaffProfile.ROLE_MANAGER)
        self.client.force_login(self.manager)

        self.other = make_restaurant('diger')
        self.other_cat = Category.objects.create(restaurant=self.other, name='Yad')
        self.other_item = make_item(self.other, 'Yad yemək', '1.00', category=self.other_cat)

    def item_data(self, **overrides):
        data = {
            'category': self.cat.pk, 'name': 'Dolma', 'description': 'Üzüm yarpağında',
            'price': '9.00', 'is_available': 'on', 'order': 1,
        }
        data.update(overrides)
        return data

    # --- Giriş və rollar ---

    def test_manager_sees_menu_page(self):
        resp = self.client.get('/panel/menu/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Plov')
        self.assertNotContains(resp, 'Yad yemək')

    def test_staff_cannot_touch_menu(self):
        staff = Client()
        staff.force_login(make_staff(self.r, 'isci'))
        urls_get = ['/panel/menu/', '/panel/menu/items/new/', f'/panel/menu/items/{self.item.pk}/edit/',
                    '/panel/menu/categories/new/']
        for url in urls_get:
            with self.subTest(url=url):
                self.assertEqual(staff.get(url).status_code, 403)
        self.assertEqual(staff.post(f'/panel/menu/items/{self.item.pk}/toggle/').status_code, 403)
        self.assertEqual(staff.post(f'/panel/menu/items/{self.item.pk}/delete/').status_code, 403)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_available)

    def test_staff_panel_has_no_menu_link_manager_has(self):
        staff = Client()
        staff.force_login(make_staff(self.r, 'isci'))
        self.assertNotContains(staff.get('/panel/'), 'href="/panel/menu/"')
        self.assertContains(self.client.get('/panel/'), 'href="/panel/menu/"')

    def test_anonymous_redirected_to_login(self):
        resp = Client().get('/panel/menu/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    # --- "Bitdi" düyməsi ---

    def test_toggle_available(self):
        resp = self.client.post(f'/panel/menu/items/{self.item.pk}/toggle/')
        self.assertRedirects(resp, f'/panel/menu/#item-{self.item.pk}', fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_available)
        self.client.post(f'/panel/menu/items/{self.item.pk}/toggle/')
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_available)

    def test_toggled_item_shows_as_finished_for_customer(self):
        self.client.post(f'/panel/menu/items/{self.item.pk}/toggle/')
        self.assertContains(Client().get('/r/dadli/'), 'Bitib')

    def test_toggle_requires_post_and_csrf(self):
        self.assertEqual(self.client.get(f'/panel/menu/items/{self.item.pk}/toggle/').status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.manager)
        self.assertEqual(csrf.post(f'/panel/menu/items/{self.item.pk}/toggle/').status_code, 403)

    def test_cannot_toggle_other_restaurants_item(self):
        self.assertEqual(self.client.post(f'/panel/menu/items/{self.other_item.pk}/toggle/').status_code, 404)
        self.other_item.refresh_from_db()
        self.assertTrue(self.other_item.is_available)

    # --- Yemək yaratma / redaktə ---

    def test_create_item_with_image(self):
        resp = self.client.post('/panel/menu/items/new/', self.item_data(image=png_file('mənim şəklim.png')))
        self.assertEqual(resp.status_code, 302)
        item = MenuItem.objects.get(name='Dolma')
        self.assertEqual(item.price, Decimal('9.00'))
        self.assertEqual(item.category, self.cat)
        # Fayl adı təsadüfi UUID-dir, istifadəçinin adı saxlanmır.
        self.assertRegex(item.image.name, r'^items/[0-9a-f]{32}\.png$')

    def test_edit_price_and_name(self):
        resp = self.client.post(
            f'/panel/menu/items/{self.item.pk}/edit/', self.item_data(name='Şah plov', price='15.75')
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, 'Şah plov')
        self.assertEqual(self.item.price, Decimal('15.75'))

    def test_price_change_does_not_affect_old_orders(self):
        order = Order.objects.create(restaurant=self.r, table=make_table(self.r), total=Decimal('12.50'))
        OrderItem.objects.create(order=order, menu_item=self.item, name='Plov', unit_price=Decimal('12.50'), quantity=1)
        self.client.post(f'/panel/menu/items/{self.item.pk}/edit/', self.item_data(name='Plov', price='20.00'))
        self.assertEqual(order.items.get().unit_price, Decimal('12.50'))

    def test_invalid_prices_rejected(self):
        for price in ['-1', 'abc', '', '1234567.00']:
            with self.subTest(price=price):
                resp = self.client.post(f'/panel/menu/items/{self.item.pk}/edit/', self.item_data(price=price))
                self.assertEqual(resp.status_code, 200)  # forma xəta ilə qayıdır
        self.item.refresh_from_db()
        self.assertEqual(self.item.price, Decimal('12.50'))

    def test_cannot_put_item_into_other_restaurants_category(self):
        resp = self.client.post('/panel/menu/items/new/', self.item_data(category=self.other_cat.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MenuItem.objects.filter(name='Dolma').exists())

    def test_cannot_edit_other_restaurants_item(self):
        self.assertEqual(self.client.get(f'/panel/menu/items/{self.other_item.pk}/edit/').status_code, 404)
        resp = self.client.post(f'/panel/menu/items/{self.other_item.pk}/edit/', self.item_data())
        self.assertEqual(resp.status_code, 404)
        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.name, 'Yad yemək')

    def test_form_only_lists_own_categories(self):
        resp = self.client.get('/panel/menu/items/new/')
        self.assertContains(resp, 'Əsas')
        self.assertNotContains(resp, '>Yad<')

    def test_fake_image_rejected(self):
        fake = SimpleUploadedFile('virus.png', b'<?php echo 1; ?>', content_type='image/png')
        resp = self.client.post('/panel/menu/items/new/', self.item_data(image=fake))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MenuItem.objects.filter(name='Dolma').exists())

    def test_disallowed_extension_rejected(self):
        buf = BytesIO()
        Image.new('RGB', (10, 10)).save(buf, format='GIF')
        gif = SimpleUploadedFile('a.gif', buf.getvalue(), content_type='image/gif')
        resp = self.client.post('/panel/menu/items/new/', self.item_data(image=gif))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MenuItem.objects.filter(name='Dolma').exists())

    def test_too_large_image_rejected(self):
        self.assertEqual(MAX_IMAGE_SIZE_MB, 5)
        with patch('menu.forms.MAX_IMAGE_SIZE_MB', 0):  # istənilən fayl "böyük" sayılsın
            resp = self.client.post('/panel/menu/items/new/', self.item_data(image=png_file()))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MB-dan böyük')
        self.assertFalse(MenuItem.objects.filter(name='Dolma').exists())

    def test_create_item_without_categories_redirects(self):
        Category.objects.filter(restaurant=self.r).delete()
        resp = self.client.get('/panel/menu/items/new/')
        self.assertRedirects(resp, '/panel/menu/categories/new/', fetch_redirect_response=False)

    def test_item_name_escaped_in_manage_page(self):
        make_item(self.r, '<img src=x onerror=alert(1)>', category=self.cat)
        resp = self.client.get('/panel/menu/')
        self.assertNotContains(resp, '<img src=x onerror=alert(1)>')

    # --- Silmə ---

    def test_delete_item_keeps_order_history(self):
        order = Order.objects.create(restaurant=self.r, table=make_table(self.r), total=Decimal('12.50'))
        line = OrderItem.objects.create(order=order, menu_item=self.item, name='Plov', unit_price=Decimal('12.50'), quantity=1)
        self.assertEqual(self.client.get(f'/panel/menu/items/{self.item.pk}/delete/').status_code, 200)
        self.client.post(f'/panel/menu/items/{self.item.pk}/delete/')
        self.assertFalse(MenuItem.objects.filter(pk=self.item.pk).exists())
        line.refresh_from_db()
        self.assertIsNone(line.menu_item)
        self.assertEqual(line.name, 'Plov')

    def test_cannot_delete_other_restaurants_item(self):
        self.assertEqual(self.client.post(f'/panel/menu/items/{self.other_item.pk}/delete/').status_code, 404)
        self.assertTrue(MenuItem.objects.filter(pk=self.other_item.pk).exists())

    # --- Kateqoriyalar ---

    def test_create_category_belongs_to_own_restaurant(self):
        # Formda restaurant sahəsi yoxdur; göndərilsə belə nəzərə alınmır.
        self.client.post('/panel/menu/categories/new/', {'name': 'İçkilər', 'order': 2, 'restaurant': self.other.pk})
        self.assertEqual(Category.objects.get(name='İçkilər').restaurant, self.r)

    def test_rename_category(self):
        self.client.post(f'/panel/menu/categories/{self.cat.pk}/edit/', {'name': 'İsti yeməklər', 'order': 0})
        self.cat.refresh_from_db()
        self.assertEqual(self.cat.name, 'İsti yeməklər')

    def test_cannot_edit_other_restaurants_category(self):
        resp = self.client.post(f'/panel/menu/categories/{self.other_cat.pk}/edit/', {'name': 'x', 'order': 0})
        self.assertEqual(resp.status_code, 404)

    def test_non_empty_category_cannot_be_deleted(self):
        self.client.post(f'/panel/menu/categories/{self.cat.pk}/delete/')
        self.assertTrue(Category.objects.filter(pk=self.cat.pk).exists())
        self.assertTrue(MenuItem.objects.filter(pk=self.item.pk).exists())

    def test_empty_category_can_be_deleted(self):
        empty = Category.objects.create(restaurant=self.r, name='Boş')
        self.client.post(f'/panel/menu/categories/{empty.pk}/delete/')
        self.assertFalse(Category.objects.filter(pk=empty.pk).exists())
