"""Yalnız DEBUG=True olanda config/urls.py tərəfindən qoşulur."""
from django.urls import path

from . import dev_views

urlpatterns = [
    path('', dev_views.dev_home, name='dev_home'),
    path('dev/login/', dev_views.dev_login, name='dev_login'),
]
