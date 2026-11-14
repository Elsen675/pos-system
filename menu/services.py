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

from .models import MenuItem, Order, OrderItem, ServiceCall, Table


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


CALL_RATE_LIMIT = 6          # bir masadan ...
CALL_RATE_WINDOW_MINUTES = 10  # ... bu qədər dəqiqədə ən çox bu qədər çağırış


def create_service_call(restaurant, payload):
    """Masadan "Ofisiantı çağır" / "Hesab istəyirəm".

    Qaydalar sifarişdəki kimidir: xidmət aktiv olmalıdır və masa tokeni
    düzgün olmalıdır (evdən çağırış olmasın). Əlavə olaraq:
    - Eyni masanın eyni növdə AÇIQ çağırışı varsa, yenisi yaradılmır,
      mövcud olan qaytarılır. Müştəri düyməni 10 dəfə bassa, ofisiant
      10 bildiriş almır.
    - Həll edilib yenidən çağırmaqla spam etməmək üçün vaxt limiti var.
    Qaytarır: (call, created) — created=False olanda köhnə çağırışdır.
    """
    if not restaurant.is_service_active():
        raise OrderError('Xidmət hazırda əlçatmazdır.', status=503)
    if not isinstance(payload, dict):
        raise OrderError('Sorğu düzgün deyil.')

    table = find_table(restaurant, payload.get('table'), payload.get('token'))
    if table is None:
        raise OrderError('Masa təsdiqlənmədi. Masadakı kartı və ya QR kodu yenidən skan edin.', status=403)

    kind = payload.get('kind')
    if kind not in dict(ServiceCall.KIND_CHOICES):
        raise OrderError('Çağırış növü düzgün deyil.')
    pay_hint = payload.get('pay_hint') or ''
    if kind != ServiceCall.KIND_BILL:
        pay_hint = ''
    elif pay_hint not in ('', *dict(ServiceCall.PAY_HINT_CHOICES)):
        raise OrderError('Ödəniş üsulu düzgün deyil.')

    with transaction.atomic():
        Table.objects.select_for_update().get(pk=table.pk)  # eyni anda iki sorğu üçün kilid
        existing = ServiceCall.objects.filter(table=table, kind=kind, resolved_at__isnull=True).first()
        if existing is not None:
            if pay_hint and existing.pay_hint != pay_hint:
                existing.pay_hint = pay_hint
                existing.save(update_fields=['pay_hint'])
            return existing, False

        since = timezone.now() - timedelta(minutes=CALL_RATE_WINDOW_MINUTES)
        if ServiceCall.objects.filter(table=table, created_at__gte=since).count() >= CALL_RATE_LIMIT:
            raise OrderError('Çox çağırış göndərildi. Ofisiant tezliklə yaxınlaşacaq.', status=429)

        call = ServiceCall.objects.create(restaurant=restaurant, table=table, kind=kind, pay_hint=pay_hint)
    return call, True


def resolve_service_call(call, user):
    """İşçi çağırışa cavab verdi. Şərtli UPDATE: iki işçi eyni anda bassa da bir dəfə yazılır."""
    ServiceCall.objects.filter(pk=call.pk, resolved_at__isnull=True).update(
        resolved_at=timezone.now(), resolved_by=user,
    )
    call.refresh_from_db()
    return call


def call_to_dict(call):
    return {
        'id': call.pk,
        'table': call.table.number,
        'kind': call.kind,
        'kind_display': call.get_kind_display(),
        'pay_hint_display': call.get_pay_hint_display() if call.pay_hint else '',
        'created_at': timezone.localtime(call.created_at).strftime('%H:%M'),
    }


def mark_paid_at_table(order, user, via):
    """İşçi masada pulu aldıqdan sonra sifarişi "Ödənilib" kimi qeyd edir.

    Niyə adi `order.pay_status = 'paid'; order.save()` yox?
    İki işçi eyni anda düyməni bassa (və ya bir işçi iki dəfə), hər ikisi
    köhnə "unpaid" vəziyyətini oxuyub yazardı və sonuncu birincinin
    məlumatını (kim, nə vaxt, necə) üstələyərdi. Burada isə bazaya bir
    şərtli əmr gedir:
        UPDATE ... SET pay_status='paid' WHERE id=... AND pay_status='unpaid'
    Baza bunu atomik icra edir: yalnız BİRİNCİ sorğu 1 sətir dəyişir,
    ikincisi 0 sətir dəyişir və biz ona "artıq ödənilib" deyirik.
    """
    if via not in dict(Order.PAID_VIA_CHOICES):
        raise OrderError('Ödəniş üsulu düzgün deyil.')
    # Onlayn ödənişi işçi əl ilə "ödənilib" edə bilməz: o yalnız bankın
    # təsdiqlənmiş webhook-u ilə dəyişir (bax: CLAUDE.md, ödəniş dizaynı).
    if order.pay_method != Order.PAY_TABLE:
        raise OrderError('Onlayn ödəniş paneldən qeyd edilmir.', status=409)
    if order.status == Order.STATUS_CANCELLED:
        raise OrderError('Ləğv edilmiş sifariş ödənilə bilməz.', status=409)

    updated = Order.objects.filter(
        pk=order.pk,
        pay_method=Order.PAY_TABLE,
        pay_status__in=(Order.PAY_UNPAID, Order.PAY_FAILED),
    ).exclude(status=Order.STATUS_CANCELLED).update(
        pay_status=Order.PAY_PAID,
        paid_via=via,
        paid_at=timezone.now(),
        paid_by=user,
        updated_at=timezone.now(),  # update() auto_now-u özü yeniləmir
    )
    if updated == 0:
        raise OrderError('Bu sifariş artıq ödənilib.', status=409)
    order.refresh_from_db()
    return order


def undo_table_payment(order):
    """Səhvən qeyd edilmiş masada ödənişi geri alır (yalnız menecer çağırır)."""
    updated = Order.objects.filter(
        pk=order.pk, pay_method=Order.PAY_TABLE, pay_status=Order.PAY_PAID,
    ).update(
        pay_status=Order.PAY_UNPAID, paid_via='', paid_at=None, paid_by=None,
        updated_at=timezone.now(),
    )
    if updated == 0:
        raise OrderError('Bu sifariş ödənilmiş vəziyyətdə deyil.', status=409)
    order.refresh_from_db()
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
        # Bu blok yalnız panel üçündür: işçinin adı müştəriyə göstərilmir.
        data['table'] = order.table.number
        data['allowed_next'] = order.allowed_next_statuses()
        data['pay_method'] = order.pay_method
        data['paid_via_display'] = order.get_paid_via_display() if order.paid_via else ''
        data['paid_at'] = timezone.localtime(order.paid_at).strftime('%H:%M') if order.paid_at else ''
        data['paid_by'] = order.paid_by.get_username() if order.paid_by_id else ''
    return data
