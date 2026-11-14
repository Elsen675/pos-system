from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from menu.models import MenuItem, Restaurant, StaffProfile


class SeedDemoTests(TestCase):
    def test_seed_is_idempotent(self):
        call_command('seed_demo', stdout=StringIO())
        call_command('seed_demo', stdout=StringIO())
        r = Restaurant.objects.get(slug='demo')
        self.assertTrue(r.is_service_active())
        self.assertEqual(r.tables.count(), 5)
        self.assertEqual(MenuItem.objects.filter(category__restaurant=r).count(), 5)
        self.assertEqual(StaffProfile.objects.filter(restaurant=r).count(), 1)
