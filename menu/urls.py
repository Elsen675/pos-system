from django.urls import path

from . import manage_views, panel_views, views

app_name = 'menu'

urlpatterns = [
    path('r/<slug:slug>/', views.menu_view, name='menu'),
    path('r/<slug:slug>/order/', views.order_create_view, name='order_create'),
    path('r/<slug:slug>/call/', views.service_call_create, name='service_call'),
    path('o/<uuid:public_id>/', views.order_status_view, name='order_status'),
    path('o/<uuid:public_id>/json/', views.order_status_json, name='order_status_json'),
    path('panel/', views.panel_view, name='panel'),
    path('panel/orders/feed/', views.panel_feed, name='panel_feed'),
    path('panel/orders/<uuid:public_id>/status/', views.panel_order_status, name='panel_order_status'),
    path('panel/calls/<int:pk>/resolve/', views.panel_call_resolve, name='panel_call_resolve'),
    path('panel/orders/<uuid:public_id>/pay/', views.panel_order_pay, name='panel_order_pay'),
    path('panel/orders/<uuid:public_id>/unpay/', views.panel_order_unpay, name='panel_order_unpay'),
    # Masa üzrə hesab, tarixçə, hesabat
    path('panel/tables/', panel_views.tables_view, name='tables'),
    path('panel/tables/<int:number>/close/', panel_views.table_bill_close, name='table_bill_close'),
    path('panel/history/', panel_views.history_view, name='history'),
    path('panel/report/', panel_views.report_view, name='report'),
    # Menecer: menyu idarəsi
    path('panel/menu/', manage_views.menu_manage, name='menu_manage'),
    path('panel/menu/items/new/', manage_views.item_create, name='item_create'),
    path('panel/menu/items/<int:pk>/edit/', manage_views.item_edit, name='item_edit'),
    path('panel/menu/items/<int:pk>/toggle/', manage_views.item_toggle, name='item_toggle'),
    path('panel/menu/items/<int:pk>/delete/', manage_views.item_delete, name='item_delete'),
    path('panel/menu/categories/new/', manage_views.category_create, name='category_create'),
    path('panel/menu/categories/<int:pk>/edit/', manage_views.category_edit, name='category_edit'),
    path('panel/menu/categories/<int:pk>/delete/', manage_views.category_delete, name='category_delete'),
    path('sw.js', views.service_worker, name='service_worker'),
]
