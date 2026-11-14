from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from menu.models import StaffProfile

from .factories import make_restaurant, make_staff


class StaffRoleTests(TestCase):
    def setUp(self):
        self.r = make_restaurant()

    def test_default_role_is_staff(self):
        user = make_staff(self.r, 'isci')
        self.assertEqual(user.staff_profile.role, StaffProfile.ROLE_STAFF)
        self.assertFalse(user.staff_profile.is_manager)

    def test_manager_role(self):
        user = make_staff(self.r, 'menecer', role=StaffProfile.ROLE_MANAGER)
        self.assertTrue(user.staff_profile.is_manager)
        self.assertEqual(user.staff_profile.get_role_display(), 'Menecer')

    def test_invalid_role_fails_validation(self):
        user = get_user_model().objects.create_user('x', password='parol-12345')
        profile = StaffProfile(user=user, restaurant=self.r, role='boss')
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_panel_shows_role(self):
        for username, role, label in (('m', 'manager', 'Menecer'), ('s', 'staff', 'İşçi')):
            with self.subTest(role=role):
                user = make_staff(self.r, username, role=role)
                self.client.force_login(user)
                self.assertContains(self.client.get('/panel/'), f'<span class="role">{label}</span>', html=False)

    def test_both_roles_can_change_order_status(self):
        # Hər iki rol sifariş statusunu dəyişə bilir (menyu idarəsi isə yalnız menecerə olacaq).
        from decimal import Decimal

        from menu.models import Order

        from .factories import make_table
        order = Order.objects.create(restaurant=self.r, table=make_table(self.r), total=Decimal('1'))
        for username, role, new_status in (('m', 'manager', 'accepted'), ('s', 'staff', 'preparing')):
            with self.subTest(role=role):
                self.client.force_login(make_staff(self.r, username, role=role))
                resp = self.client.post(f'/panel/orders/{order.public_id}/status/', {'status': new_status})
                self.assertEqual(resp.status_code, 200)
