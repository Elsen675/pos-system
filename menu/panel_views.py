"""Panel: masa üzrə hesab, tarixçə, gündəlik hesabat."""
import uuid
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .manage_views import manager_required
from .models import Order
from .reports import close_table_bill, daily_report, open_bills_by_table, orders_for_day, parse_day
from .services import OrderError
from .views import staff_required


def _base_context(request):
    return {'restaurant': request.staff_profile.restaurant, 'profile': request.staff_profile}


@require_GET
@staff_required
def tables_view(request):
    return render(request, 'menu/panel/tables.html', {
        **_base_context(request),
        'bills': open_bills_by_table(request.staff_profile.restaurant),
        'paid_via_choices': Order.PAID_VIA_CHOICES,
    })


@require_POST
@staff_required
def table_bill_close(request, number):
    raw_ids = request.POST.getlist('order')
    try:
        # Yalnız düzgün UUID-ləri qəbul edirik (zibil dəyər bazaya getməsin).
        order_ids = [uuid.UUID(value) for value in raw_ids]
    except ValueError:
        messages.error(request, 'Sorğu düzgün deyil.')
        return redirect('menu:tables')

    try:
        count = close_table_bill(
            request.staff_profile.restaurant, number, order_ids, request.user, request.POST.get('via'),
        )
    except OrderError as exc:
        messages.error(request, exc.message)
        return redirect('menu:tables')

    via_label = dict(Order.PAID_VIA_CHOICES)[request.POST['via']]
    messages.success(request, f'Masa {number}: {count} sifariş ödənildi ({via_label}).')
    return redirect('menu:tables')


def _day_nav(day):
    today = timezone.localdate()
    return {
        'day': day,
        'prev_day': day - timedelta(days=1),
        'next_day': day + timedelta(days=1) if day < today else None,
        'is_today': day == today,
    }


@require_GET
@staff_required
def history_view(request):
    day = parse_day(request.GET.get('date'))
    orders = (
        orders_for_day(request.staff_profile.restaurant, day)
        .select_related('table', 'paid_by')
        .prefetch_related('items')
        .order_by('-created_at')
    )
    status = request.GET.get('status')
    if status in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status)
    return render(request, 'menu/panel/history.html', {
        **_base_context(request),
        **_day_nav(day),
        'orders': orders,
        'status_filter': status if status in dict(Order.STATUS_CHOICES) else '',
        'status_choices': Order.STATUS_CHOICES,
        'base_url': reverse('menu:history'),
    })


@require_GET
@manager_required
def report_view(request):
    day = parse_day(request.GET.get('date'))
    return render(request, 'menu/panel/report.html', {
        **_base_context(request),
        **_day_nav(day),
        'report': daily_report(request.staff_profile.restaurant, day),
        'base_url': reverse('menu:report'),
    })
