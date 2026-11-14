from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from menu.models import Category, MenuItem, Restaurant, StaffProfile, Table


def make_restaurant(slug='dadli', days_left=30, is_active=True, name=None):
    return Restaurant.objects.create(
        name=name or slug.title(),
        slug=slug,
        is_active=is_active,
        subscription_until=timezone.localdate() + timedelta(days=days_left),
    )


def make_item(restaurant, name='Plov', price='12.50', is_available=True, category=None):
    if category is None:
        category, _ = Category.objects.get_or_create(restaurant=restaurant, name='Əsas yeməklər')
    return MenuItem.objects.create(
        category=category, name=name, price=Decimal(price), is_available=is_available
    )


def make_table(restaurant, number=1):
    return Table.objects.create(restaurant=restaurant, number=number)


def make_staff(restaurant, username='isci', password='parol-12345', **profile_kwargs):
    user = get_user_model().objects.create_user(username=username, password=password)
    StaffProfile.objects.create(user=user, restaurant=restaurant, **profile_kwargs)
    return user
