import json
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Category, MenuItem, Order, Restaurant, ScanEvent, ServiceCall, StaffProfile
from .services import (
    OrderError,
    call_to_dict,
    create_order,
    create_service_call,
    resolve_service_call,
    find_table,
    mark_paid_at_table,
    order_to_dict,
    undo_table_payment,
)


def service_unavailable(request, restaurant):
    """Abunəsi bitmiş / deaktiv restoran üçün 503 səhifəsi."""
    return render(request, 'menu/service_unavailable.html', {'restaurant': restaurant}, status=503)


# ---------------------------------------------------------------------------
# Müştəri tərəfi
# ---------------------------------------------------------------------------

@require_GET
@ensure_csrf_cookie  # Səhifədəki JS sifarişi POST edəndə CSRF tokeni cookie-dən götürür.
def menu_view(request, slug):
    restaurant = get_object_or_404(Restaurant, slug=slug)
    if not restaurant.is_service_active():
        return service_unavailable(request, restaurant)

    table = find_table(restaurant, request.GET.get('t'), request.GET.get('k'))
    source = request.GET.get('s')
    if source not in (ScanEvent.SOURCE_NFC, ScanEvent.SOURCE_QR):
        source = ScanEvent.SOURCE_UNKNOWN

    ScanEvent.objects.create(
        restaurant=restaurant,
        table=table,
        source=source,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
    )

    categories = (
        Category.objects.filter(restaurant=restaurant)
        .prefetch_related(Prefetch('items', queryset=MenuItem.objects.order_by('order', 'id')))
    )
    order_context = None
    if table is not None:
        order_context = {
            'orderUrl': reverse('menu:order_create', args=[restaurant.slug]),
            'callUrl': reverse('menu:service_call', args=[restaurant.slug]),
            'table': table.number,
            'token': table.token,
        }
    return render(request, 'menu/menu.html', {
        'restaurant': restaurant,
        'categories': categories,
        'table': table,
        'order_context': order_context,
    })


@require_POST
def order_create_view(request, slug):
    """POST JSON: {table, token, items: [{id, qty}], note}.

    CSRF yoxlaması Django middleware tərəfindən edilir (csrf_exempt YOXDUR).
    """
    restaurant = get_object_or_404(Restaurant, slug=slug)
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Sorğu düzgün deyil.'}, status=400)

    try:
        order = create_order(restaurant, payload)
    except OrderError as exc:
        return JsonResponse({'error': exc.message}, status=exc.status)

    return JsonResponse(
        {'id': str(order.public_id), 'status_url': order.get_absolute_url(), 'total': str(order.total)},
        status=201,
    )


@require_POST
def service_call_create(request, slug):
    """POST JSON: {table, token, kind: waiter|bill, pay_hint?: cash|card}."""
    restaurant = get_object_or_404(Restaurant, slug=slug)
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Sorğu düzgün deyil.'}, status=400)
    try:
        call, created = create_service_call(restaurant, payload)
    except OrderError as exc:
        return JsonResponse({'error': exc.message}, status=exc.status)
    return JsonResponse({'id': call.pk, 'kind': call.kind, 'created': created}, status=201 if created else 200)


@require_GET
def order_status_view(request, public_id):
    order = get_object_or_404(Order.objects.select_related('restaurant', 'table'), public_id=public_id)
    return render(request, 'menu/order_status.html', {
        'order': order,
        'items': order.items.all(),
    })


@require_GET
@never_cache
def order_status_json(request, public_id):
    order = get_object_or_404(Order.objects.select_related('table'), public_id=public_id)
    return JsonResponse(order_to_dict(order))


@require_GET
def service_worker(request):
    """Service worker kökdən (/sw.js) verilməlidir ki, bütün sayta təsir etsin."""
    response = render(request, 'menu/sw.js', content_type='application/javascript')
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


# ---------------------------------------------------------------------------
# Restoran paneli
# ---------------------------------------------------------------------------

def staff_required(view):
    """Girişi və StaffProfile-ı yoxlayır, `request.staff_profile` təyin edir.

    Panel sorğularının hamısı `request.staff_profile.restaurant` üzrə
    süzülür: işçi yalnız öz restoranının məlumatını görür.
    """
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        profile = (
            StaffProfile.objects.select_related('restaurant')
            .filter(user=request.user)
            .first()
        )
        if profile is None:
            return HttpResponseForbidden('Bu hesab heç bir restorana bağlı deyil.')
        if not profile.restaurant.is_service_active():
            return service_unavailable(request, profile.restaurant)
        request.staff_profile = profile
        return view(request, *args, **kwargs)
    return wrapper


@require_GET
@staff_required
def panel_view(request):
    return render(request, 'menu/panel.html', {
        'restaurant': request.staff_profile.restaurant,
        'profile': request.staff_profile,
        'panel_config': {
            'statusChoices': Order.STATUS_CHOICES,
            'paidViaChoices': Order.PAID_VIA_CHOICES,
            # Yalnız düyməni göstərib-gizlətmək üçündür. Əsl yoxlama serverdədir:
            # işçi JS-i dəyişib düyməni çıxarsa belə server 403 qaytarır.
            'isManager': request.staff_profile.is_manager,
        },
    })


# Bitmiş sifarişlər paneldə bu qədər müddət görünür.
FINISHED_VISIBLE_HOURS = 3


@require_GET
@never_cache
@staff_required
def panel_feed(request):
    restaurant = request.staff_profile.restaurant
    since = timezone.now() - timedelta(hours=FINISHED_VISIBLE_HOURS)
    active = Order.objects.filter(restaurant=restaurant).exclude(status__in=Order.FINISHED_STATUSES)
    recent_finished = Order.objects.filter(
        restaurant=restaurant, status__in=Order.FINISHED_STATUSES, updated_at__gte=since
    )
    orders = (
        (active | recent_finished)
        .select_related('table', 'paid_by')
        .prefetch_related('items')
        .order_by('-created_at')[:200]
    )
    calls = (
        ServiceCall.objects.filter(restaurant=restaurant, resolved_at__isnull=True)
        .select_related('table')
    )
    return JsonResponse({
        'calls': [call_to_dict(c) for c in calls],
        'orders': [order_to_dict(o, include_table=True) for o in orders],
        'server_time': timezone.localtime().strftime('%H:%M:%S'),
    })


@require_POST
@staff_required
def panel_order_status(request, public_id):
    # Sifarişi HƏM public_id, HƏM də işçinin restoranı ilə axtarırıq.
    # Başqa restoranın sifarişinin UUID-i bilinsə belə 404 qaytarılır.
    order = get_object_or_404(Order, public_id=public_id, restaurant=request.staff_profile.restaurant)

    try:
        new_status = _read_field(request, 'status')
    except ValueError:
        return JsonResponse({'error': 'Sorğu düzgün deyil.'}, status=400)

    if new_status not in dict(Order.STATUS_CHOICES):
        return JsonResponse({'error': 'Naməlum status.'}, status=400)

    if not order.can_transition_to(new_status):
        if new_status == Order.STATUS_CANCELLED and order.pay_status == Order.PAY_PAID:
            message = 'Ödənilmiş sifariş ləğv edilə bilməz. Əvvəlcə menecer ödənişi geri almalıdır.'
        else:
            message = f'"{order.get_status_display()}" statusundan bu statusa keçmək olmaz.'
        return JsonResponse({'error': message}, status=409)

    # Şərtli UPDATE: yalnız status hələ də bizim oxuduğumuz kimidirsə dəyişirik.
    # Başqa işçi bu arada statusu dəyişibsə (məs. "Verildi" edib), 0 sətir
    # dəyişir və köhnə məlumata əsaslanan keçid baş vermir.
    conditions = {'pk': order.pk, 'status': order.status}
    query = Order.objects.filter(**conditions)
    if new_status == Order.STATUS_CANCELLED:
        query = query.exclude(pay_status=Order.PAY_PAID)
    updated = query.update(status=new_status, updated_at=timezone.now())
    if updated == 0:
        return JsonResponse({'error': 'Sifariş bu arada dəyişib. Səhifə yenilənir.'}, status=409)
    order.refresh_from_db()
    return JsonResponse(order_to_dict(order, include_table=True))


def _read_field(request, name):
    """JSON və ya adi form POST-dan bir sahəni oxuyur. Pozuq JSON-da ValueError."""
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError from exc
        if not isinstance(data, dict):
            raise ValueError
        return data.get(name)
    return request.POST.get(name)


@require_POST
@staff_required
def panel_order_pay(request, public_id):
    """Masada ödənişi qeyd edir (nağd / terminal). Hər iki rol edə bilər."""
    order = get_object_or_404(Order, public_id=public_id, restaurant=request.staff_profile.restaurant)
    try:
        via = _read_field(request, 'via')
    except ValueError:
        return JsonResponse({'error': 'Sorğu düzgün deyil.'}, status=400)
    try:
        order = mark_paid_at_table(order, request.user, via)
    except OrderError as exc:
        return JsonResponse({'error': exc.message}, status=exc.status)
    return JsonResponse(order_to_dict(order, include_table=True))


@require_POST
@staff_required
def panel_call_resolve(request, pk):
    """İşçi çağırışa cavab verdi ("Həll edildi"). Hər iki rol edə bilər."""
    call = get_object_or_404(ServiceCall, pk=pk, restaurant=request.staff_profile.restaurant)
    call = resolve_service_call(call, request.user)
    return JsonResponse({'id': call.pk, 'resolved': True})


@require_POST
@staff_required
def panel_order_unpay(request, public_id):
    """Səhvən qeyd edilmiş ödənişi geri alır. YALNIZ menecer.

    İşçi pulu alıb ödənişi "geri ala" bilsəydi, sifariş ödənilməmiş görünər
    və pul itərdi. Ona görə bu hüquq yalnız menecerdədir.
    """
    if not request.staff_profile.is_manager:
        return JsonResponse({'error': 'Bunu yalnız menecer edə bilər.'}, status=403)
    order = get_object_or_404(Order, public_id=public_id, restaurant=request.staff_profile.restaurant)
    try:
        order = undo_table_payment(order)
    except OrderError as exc:
        return JsonResponse({'error': exc.message}, status=exc.status)
    return JsonResponse(order_to_dict(order, include_table=True))
