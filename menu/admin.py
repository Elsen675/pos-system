from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Category, MenuItem, Order, OrderItem, Restaurant, ScanEvent, StaffProfile, Table


class TableInline(admin.TabularInline):
    model = Table
    extra = 0
    fields = ('number', 'token')
    readonly_fields = ('token',)


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'subscription_until', 'service_status', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [TableInline]

    @admin.display(description='xidmət', boolean=True)
    def service_status(self, obj):
        return obj.is_service_active()


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'order')
    list_filter = ('restaurant',)
    list_editable = ('order',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available', 'order')
    list_filter = ('category__restaurant', 'is_available')
    list_editable = ('price', 'is_available', 'order')
    search_fields = ('name',)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('restaurant', 'number', 'token', 'nfc_link', 'qr_link')
    list_filter = ('restaurant',)
    readonly_fields = ('token',)
    actions = ['regenerate_tokens']

    @admin.display(description='NFC linki')
    def nfc_link(self, obj):
        # format_html dəyərləri escape edir (XSS-dən qorunma).
        url = obj.get_menu_url('n')
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)

    @admin.display(description='QR linki')
    def qr_link(self, obj):
        return obj.get_menu_url('q')

    @admin.action(description='Seçilmiş masaların tokenini yenilə (köhnə kartlar işləməyəcək!)')
    def regenerate_tokens(self, request, queryset):
        for table in queryset:
            table.regenerate_token()
        self.message_user(request, f'{queryset.count()} masanın tokeni yeniləndi.', messages.WARNING)


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'restaurant', 'table', 'source')
    list_filter = ('restaurant', 'source')
    readonly_fields = ('restaurant', 'table', 'source', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'restaurant', 'role')
    list_filter = ('restaurant', 'role')
    autocomplete_fields = ('user',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('menu_item', 'name', 'unit_price', 'quantity')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('short_id', 'restaurant', 'table', 'status', 'total', 'pay_status', 'created_at')
    list_filter = ('restaurant', 'status', 'pay_status')
    readonly_fields = ('public_id', 'restaurant', 'table', 'total', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
