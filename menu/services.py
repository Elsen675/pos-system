"""Sifariş yaratma məntiqi (view-dan ayrı ki, rahat test olunsun).

Təhlükəsizlik prinsipləri:
- Müştərinin göndərdiyi heç bir qiymətə güvənmirik. Müştəri yalnız
  "hansı yeməkdən neçə ədəd" göndərir, qiyməti biz bazadan götürürük.
- Yeməklər yalnız HƏMİN restoranın menyusundan seçilə bilər (başqa restoranın
  yeməyinin id-sini göndərmək işləmir).
- Masa tokeni olmadan sifariş yoxdur: token yalnız masadakı kartda/QR-da var,
  evdən oturub saxta sifariş vermək olmur.
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MenuItem, Order, OrderItem, Table


class OrderError(Exception):
    """Müştəriyə göstəriləcək xəta. `status` HTTP status kodudur."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def find_table(restaurant, number, token):
    """Nömrə və tokenə görə masanı tapır, uyğun gəlmirsə None qaytarır.

    Tokeni `secrets.compare_digest` ilə müqayisə edirik: adi `==` ilk fərqli
    simvolda dayanır və cavab vaxtına görə tokeni hərf-hərf təxmin etmək
    nəzəri olaraq mümkündür (timing attack). compare_digest həmişə eyni
    vaxt sərf edir.
    """
    if not number or not token or not isinstance(token, str):
        return None
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    table = Table.objects.filter(restaurant=restaurant, number=number).first()
    if table is None or not secrets.compare_digest(table.token, token):
        return None
    return table


def _parse_items(raw_items):
    """[{id, qty}, ...] siyahısını yoxlayır və {id: qty} lüğəti qaytarır."""
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderError('Səbət boşdur.')
    if len(raw_items) > settings.ORDER_MAX_LINES:
        raise OrderError('Səbətdə həddən çox məhsul var.')

    quantities = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise OrderError('Səbət məlumatı düzgün deyil.')
        item_id, qty = raw.get('id'), raw.get('qty')
        # bool int-in alt sinfidir (True == 1), onu ayrıca rədd edirik.
        if isinstance(item_id, bool) or isinstance(qty, bool):
            raise OrderError('Səbət məlumatı düzgün deyil.')
        if not isinstance(item_id, int) or not isinstance(qty, int):
            raise OrderError('Səbət məlumatı düzgün deyil.')
        if qty < 1:
            raise OrderError('Say ən azı 1 olmalıdır.')
        quantities[item_id] = quantities.get(item_id, 0) + qty
        if quantities[item_id] > settings.ORDER_MAX_QTY_PER_LINE:
            raise OrderError(f'Bir məhsuldan ən çox {settings.ORDER_MAX_QTY_PER_LINE} ədəd sifariş etmək olar.')
    return quantities


def create_order(restaurant, payload):
    """Yoxlamalardan keçən sifarişi yaradır, keçməyəndə OrderError atır."""
    if not restaurant.is_service_active():
        raise OrderError('Xidmət hazırda əlçatmazdır.', status=503)
    if not isinstance(payload, dict):
        raise OrderError('Sorğu düzgün deyil.')

    table = find_table(restaurant, payload.get('table'), payload.get('token'))
    if table is None:
        raise OrderError('Masa təsdiqlənmədi. Masadakı kartı və ya QR kodu yenidən skan edin.', status=403)

    quantities = _parse_items(payload.get('items'))

    note = payload.get('note') or ''
    if not isinstance(note, str):
        raise OrderError('Qeyd düzgün deyil.')
    note = note.strip()[: settings.ORDER_NOTE_MAX_LENGTH]

    # Yalnız bu restoranın, mövcud ("bitməyib") yeməkləri.
    menu_items = {
        mi.id: mi
        for mi in MenuItem.objects.filter(
            id__in=quantities.keys(),
            category__restaurant=restaurant,
            is_available=True,
        )
    }
    if len(menu_items) != len(quantities):
        raise OrderError('Səbətdəki bəzi məhsullar artıq mövcud deyil. Menyunu yeniləyin.', status=409)

    with transaction.atomic():
        # Masa sətrini kilidləyirik (PostgreSQL-də SELECT ... FOR UPDATE).
        # Eyni masadan eyni anda gələn iki sorğu limiti birlikdə "aşa" bilməsin:
        # ikinci sorğu birincinin tranzaksiyası bitənə qədər gözləyir.
        Table.objects.select_for_update().get(pk=table.pk)
        since = timezone.now() - timedelta(minutes=settings.ORDER_RATE_WINDOW_MINUTES)
        recent_new = Order.objects.filter(table=table, status=Order.STATUS_NEW, created_at__gte=since).count()
        if recent_new >= settings.ORDER_RATE_LIMIT:
            raise OrderError(
                'Bu masadan çox sifariş gəlib. Zəhmət olmasa, bir az gözləyin və ya ofisiantı çağırın.',
                status=429,
            )

        total = sum(
            (menu_items[item_id].price * qty for item_id, qty in quantities.items()),
            Decimal('0'),
        )
        order = Order.objects.create(
            restaurant=restaurant,
            table=table,
            note=note,
            total=total,
            pay_method=Order.PAY_TABLE,
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                menu_item=menu_items[item_id],
                name=menu_items[item_id].name,
                unit_price=menu_items[item_id].price,
                quantity=qty,
            )
            for item_id, qty in quantities.items()
        )
    return order


def order_to_dict(order, include_table=False):
    """JSON cavabı üçün. Mətnlər xam qaytarılır, JS onları textContent ilə yazır."""
    data = {
        'id': str(order.public_id),
        'short_id': order.short_id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'pay_status': order.pay_status,
        'pay_status_display': order.get_pay_status_display(),
        'total': str(order.total),
        'note': order.note,
        'created_at': timezone.localtime(order.created_at).strftime('%H:%M'),
        'items': [
            {'name': i.name, 'qty': i.quantity, 'unit_price': str(i.unit_price), 'line_total': str(i.line_total)}
            for i in order.items.all()
        ],
    }
    if include_table:
        data['table'] = order.table.number
    return data
