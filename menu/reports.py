"""Masa üzrə hesab və gündəlik hesabat."""
from collections import OrderedDict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone

from .models import Order, OrderItem, ScanEvent, ServiceCall, Table
from .services import OrderError

OPEN_PAY_STATUSES = (Order.PAY_UNPAID, Order.PAY_FAILED)
CENTS = Decimal('0.01')


def money(value):
    """Pul məbləğini həmişə 2 onluq rəqəmlə qaytarır (SQLite cəmi '36' qaytara bilər)."""
    return (value or Decimal('0')).quantize(CENTS)


def open_bill_orders(restaurant):
    """Masada ödəniləcək, hələ ödənilməmiş və ləğv edilməmiş sifarişlər."""
    return (
        Order.objects.filter(
            restaurant=restaurant,
            pay_method=Order.PAY_TABLE,
            pay_status__in=OPEN_PAY_STATUSES,
        )
        .exclude(status=Order.STATUS_CANCELLED)
        .select_related('table')
        .prefetch_related('items')
        .order_by('table__number', 'created_at')
    )


def open_bills_by_table(restaurant):
    """{table: {'orders': [...], 'total': Decimal}} — masa nömrəsinə görə sıralı."""
    bills = OrderedDict()
    for order in open_bill_orders(restaurant):
        bill = bills.setdefault(order.table, {'orders': [], 'total': Decimal('0')})
        bill['orders'].append(order)
        bill['total'] += order.total
    return bills


def close_table_bill(restaurant, table_number, order_ids, user, via):
    """Masanın hesabını bağlayır: göstərilən sifarişlərin hamısı "ödənilib" olur.

    `order_ids` — ofisiantın ekranda GÖRDÜYÜ sifarişlər (public_id).
    Niyə masanın "bütün" ödənilməmiş sifarişlərini götürmürük? Ofisiant
    hesabı açandan sonra masadan yeni sifariş gələ bilər; müştəri onun
    pulunu hələ verməyib, onu avtomatik "ödənilib" etmək səhv olardı.

    Hamısı bir tranzaksiyadadır: ya hamısı bağlanır, ya heç biri.
    """
    if via not in dict(Order.PAID_VIA_CHOICES):
        raise OrderError('Ödəniş üsulu düzgün deyil.')
    if not order_ids:
        raise OrderError('Bağlanacaq sifariş yoxdur.')

    table = Table.objects.filter(restaurant=restaurant, number=table_number).first()
    if table is None:
        raise OrderError('Masa tapılmadı.', status=404)

    with transaction.atomic():
        now = timezone.now()
        updated = (
            Order.objects.filter(
                restaurant=restaurant,
                table=table,
                public_id__in=order_ids,
                pay_method=Order.PAY_TABLE,
                pay_status__in=OPEN_PAY_STATUSES,
            )
            .exclude(status=Order.STATUS_CANCELLED)
            .update(pay_status=Order.PAY_PAID, paid_via=via, paid_at=now, paid_by=user, updated_at=now)
        )
        if updated != len(set(order_ids)):
            # Nəsə dəyişib (başqa işçi bir sifarişi ödəyib, ləğv edib və s.).
            # Exception tranzaksiyanı geri qaytarır (rollback): heç nə yazılmır.
            raise OrderError('Masanın hesabı bu arada dəyişib. Səhifə yenilənir, yenidən yoxlayın.', status=409)

        # Masanın açıq "Hesab istəyir" çağırışı varsa, o da həll olunur.
        ServiceCall.objects.filter(table=table, kind=ServiceCall.KIND_BILL, resolved_at__isnull=True).update(
            resolved_at=now, resolved_by=user,
        )
    return updated


def day_bounds(day):
    """Restoranın yerli vaxtı ilə günün başlanğıcı və sonu (TIME_ZONE = Asia/Baku)."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def parse_day(value):
    """?date=YYYY-MM-DD; boş və ya səhvdirsə bu gün."""
    try:
        return datetime.strptime(value or '', '%Y-%m-%d').date()
    except ValueError:
        return timezone.localdate()


def orders_for_day(restaurant, day):
    start, end = day_bounds(day)
    return Order.objects.filter(restaurant=restaurant, created_at__gte=start, created_at__lt=end)


def daily_report(restaurant, day):
    start, end = day_bounds(day)
    orders = orders_for_day(restaurant, day)
    valid = orders.exclude(status=Order.STATUS_CANCELLED)

    zero = Decimal('0')
    totals = valid.aggregate(
        count=Count('id'),
        revenue=Sum('total'),
        paid=Sum('total', filter=Q(pay_status=Order.PAY_PAID)),
        cash=Sum('total', filter=Q(pay_status=Order.PAY_PAID, paid_via=Order.PAID_VIA_CASH)),
        terminal=Sum('total', filter=Q(pay_status=Order.PAY_PAID, paid_via=Order.PAID_VIA_TERMINAL)),
        online=Sum('total', filter=Q(pay_status=Order.PAY_PAID, pay_method=Order.PAY_ONLINE)),
    )
    count = totals['count']
    revenue = money(totals['revenue'])
    paid = money(totals['paid'])

    # Ən çox satılanlar: snapshot adına görə qruplaşdırırıq (yemək sonradan
    # silinsə və ya adı dəyişsə belə həmin günün satışı düz görünür).
    top_items = (
        OrderItem.objects.filter(order__in=valid)
        .values('name')
        .annotate(qty=Sum('quantity'), amount=Sum(F('unit_price') * F('quantity')))
        .order_by('-qty', 'name')[:10]
    )

    by_hour = {row['hour']: row['n'] for row in valid.annotate(hour=ExtractHour('created_at')).values('hour').annotate(n=Count('id'))}
    hours = [{'hour': h, 'count': by_hour.get(h, 0)} for h in range(24) if by_hour.get(h)]
    max_hour = max((h['count'] for h in hours), default=0)
    for h in hours:
        h['percent'] = round(h['count'] * 100 / max_hour) if max_hour else 0

    scans = ScanEvent.objects.filter(restaurant=restaurant, created_at__gte=start, created_at__lt=end)
    calls = ServiceCall.objects.filter(restaurant=restaurant, created_at__gte=start, created_at__lt=end)

    return {
        'day': day,
        'order_count': count,
        'cancelled_count': orders.filter(status=Order.STATUS_CANCELLED).count(),
        'revenue': revenue,
        'average': money(revenue / count) if count else money(zero),
        'paid': paid,
        'paid_cash': money(totals['cash']),
        'paid_terminal': money(totals['terminal']),
        'paid_online': money(totals['online']),
        'unpaid': revenue - paid,
        'top_items': [{**row, 'amount': money(row['amount'])} for row in top_items],
        'hours': hours,
        'scans_nfc': scans.filter(source=ScanEvent.SOURCE_NFC).count(),
        'scans_qr': scans.filter(source=ScanEvent.SOURCE_QR).count(),
        'scans_other': scans.filter(source=ScanEvent.SOURCE_UNKNOWN).count(),
        'calls_waiter': calls.filter(kind=ServiceCall.KIND_WAITER).count(),
        'calls_bill': calls.filter(kind=ServiceCall.KIND_BILL).count(),
    }
