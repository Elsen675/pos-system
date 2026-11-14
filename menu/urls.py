from django.urls import path

from . import views

app_name = 'menu'

urlpatterns = [
    path('r/<slug:slug>/', views.menu_view, name='menu'),
    path('r/<slug:slug>/order/', views.order_create_view, name='order_create'),
    path('o/<uuid:public_id>/', views.order_status_view, name='order_status'),
    path('o/<uuid:public_id>/json/', views.order_status_json, name='order_status_json'),
    path('panel/', views.panel_view, name='panel'),
    path('panel/orders/feed/', views.panel_feed, name='panel_feed'),
    path('panel/orders/<uuid:public_id>/status/', views.panel_order_status, name='panel_order_status'),
    path('sw.js', views.service_worker, name='service_worker'),
]
