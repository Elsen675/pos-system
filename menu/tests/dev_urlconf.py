"""Testlər üçün: əsas URL-lər + dev URL-ləri (testlərdə DEBUG=False olduğu üçün
config/urls.py onları qoşmur)."""
from django.urls import include, path

from config.urls import urlpatterns as base_patterns

urlpatterns = base_patterns + [path('', include('menu.dev_urls'))]
