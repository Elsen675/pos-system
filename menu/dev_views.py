"""YALNIZ İNKİŞAF ÜÇÜN: demo başlanğıc səhifəsi və şifrəsiz demo giriş.

Şifrəsiz giriş təhlükəli şeydir, ona görə bir neçə qat qoruma var:
1. Bu URL-lər yalnız DEBUG=True olanda qeydiyyata alınır (config/urls.py).
2. View-un özü də DEBUG-u yoxlayır. URL səhvən istehsalda qoşulsa belə
   404 qaytarır. Buna "defense in depth" deyilir: bir qoruma səhv olsa,
   o biri işləyir.
3. Sorğu yalnız bu kompüterdən (127.0.0.1 / ::1) gələndə qəbul olunur.
4. Yalnız `demo` restoranının işçi profilləri ilə giriş olar.
   Superuser və staff (admin) hesablarına bu yolla girmək olmaz.
"""
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Restaurant, StaffProfile

DEMO_SLUG = 'demo'
LOOPBACK = {'127.0.0.1', '::1'}


def _ensure_dev_request(request):
    if not settings.DEBUG or request.META.get('REMOTE_ADDR') not in LOOPBACK:
        raise Http404


@require_GET
def dev_home(request):
    _ensure_dev_request(request)
    restaurant = Restaurant.objects.filter(slug=DEMO_SLUG).first()
    profiles = []
    tables = []
    if restaurant is not None:
        tables = list(restaurant.tables.all())
        profiles = list(
            StaffProfile.objects.filter(restaurant=restaurant).select_related('user').order_by('role')
        )
    return render(request, 'menu/dev_home.html', {
        'restaurant': restaurant,
        'tables': tables,
        'profiles': profiles,
    })


@require_POST
def dev_login(request):
    _ensure_dev_request(request)
    user = (
        get_user_model().objects
        .filter(
            username=request.POST.get('username', ''),
            staff_profile__restaurant__slug=DEMO_SLUG,
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        .first()
    )
    if user is None:
        raise Http404
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('menu:panel')
