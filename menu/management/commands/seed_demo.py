"""Yerli inkişaf üçün demo restoran: `python manage.py seed_demo`.

Şifrə koda yazılmır: hər işə salmada təsadüfi şifrə yaradılır və ekrana çıxarılır.
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from menu.models import Category, MenuItem, Restaurant, StaffProfile, Table

MENU = {
    'Əsas yeməklər': [('Plov', '12.50', 'Şah plov, quru meyvə ilə'), ('Dolma', '9.00', ''), ('Kabab', '14.00', 'Tikə kabab')],
    'İçkilər': [('Çay (dəmlik)', '4.00', 'Limon və mürəbbə ilə'), ('Ayran', '2.00', '')],
}


class Command(BaseCommand):
    help = 'Demo restoran, masalar, menyu və işçi hesabı yaradır.'

    def handle(self, *args, **options):
        restaurant, _ = Restaurant.objects.update_or_create(
            slug='demo',
            defaults={'name': 'Demo Restoran', 'is_active': True,
                      'subscription_until': timezone.localdate() + timedelta(days=30)},
        )
        for number in range(1, 6):
            Table.objects.get_or_create(restaurant=restaurant, number=number)
        for order, (cat_name, items) in enumerate(MENU.items()):
            category, _ = Category.objects.get_or_create(restaurant=restaurant, name=cat_name, defaults={'order': order})
            for i, (name, price, desc) in enumerate(items):
                MenuItem.objects.get_or_create(
                    category=category, name=name,
                    defaults={'price': Decimal(price), 'description': desc, 'order': i},
                )

        table = restaurant.tables.get(number=1)
        self.stdout.write(self.style.SUCCESS('Demo hazırdır.'))
        self.stdout.write(f'Menyu (masa 1): {table.get_menu_url("n")}')

        for username, role in (('demo_menecer', StaffProfile.ROLE_MANAGER), ('demo_isci', StaffProfile.ROLE_STAFF)):
            password = secrets.token_urlsafe(9)
            user, _ = get_user_model().objects.get_or_create(username=username)
            user.set_password(password)
            user.save()
            StaffProfile.objects.update_or_create(user=user, defaults={'restaurant': restaurant, 'role': role})
            self.stdout.write(f'Panel: /panel/  istifadəçi: {username}  şifrə: {password}')
