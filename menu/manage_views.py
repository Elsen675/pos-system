"""Menecer üçün menyu idarəsi (/panel/menu/...).

Hər view `manager_required` ilə qorunur və hər obyekt menecerin ÖZ
restoranı üzrə axtarılır (`category__restaurant=...`). Başqa restoranın
yeməyinin id-si URL-ə yazılsa belə 404 qayıdır.
"""
from functools import wraps

from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CategoryForm, MenuItemForm
from .models import Category, MenuItem
from .views import staff_required


def manager_required(view):
    """staff_required + rol yoxlaması. İşçi menyuya toxunmur (403)."""
    @staff_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.staff_profile.is_manager:
            return HttpResponseForbidden('Menyunu yalnız menecer idarə edə bilər.')
        return view(request, *args, **kwargs)
    return wrapper


def _restaurant(request):
    return request.staff_profile.restaurant


def _get_item(request, pk):
    return get_object_or_404(MenuItem, pk=pk, category__restaurant=_restaurant(request))


def _get_category(request, pk):
    return get_object_or_404(Category, pk=pk, restaurant=_restaurant(request))


@manager_required
def menu_manage(request):
    categories = Category.objects.filter(restaurant=_restaurant(request)).prefetch_related(
        Prefetch('items', queryset=MenuItem.objects.order_by('order', 'id'))
    )
    return render(request, 'menu/manage/menu.html', {
        'restaurant': _restaurant(request),
        'profile': request.staff_profile,
        'categories': categories,
    })


@require_POST
@manager_required
def item_toggle(request, pk):
    """"Bitdi" / "Var" düyməsi."""
    item = _get_item(request, pk)
    item.is_available = not item.is_available
    item.save(update_fields=['is_available'])
    state = 'yenidən mövcuddur' if item.is_available else '"bitdi" kimi işarələndi'
    messages.success(request, f'{item.name} {state}.')
    return redirect(reverse('menu:menu_manage') + f'#item-{item.pk}')


def _item_form_view(request, item=None):
    restaurant = _restaurant(request)
    if not Category.objects.filter(restaurant=restaurant).exists():
        messages.warning(request, 'Əvvəlcə ən azı bir kateqoriya yaradın.')
        return redirect('menu:category_create')

    initial = {}
    if item is None and request.GET.get('category'):
        initial['category'] = request.GET.get('category')

    form = MenuItemForm(
        request.POST or None, request.FILES or None,
        instance=item, restaurant=restaurant, initial=initial,
    )
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'{saved.name} yadda saxlanıldı.')
        return redirect(reverse('menu:menu_manage') + f'#item-{saved.pk}')
    return render(request, 'menu/manage/item_form.html', {
        'restaurant': restaurant,
        'profile': request.staff_profile,
        'form': form,
        'item': item,
    })


@manager_required
def item_create(request):
    return _item_form_view(request)


@manager_required
def item_edit(request, pk):
    return _item_form_view(request, _get_item(request, pk))


@manager_required
def item_delete(request, pk):
    item = _get_item(request, pk)
    if request.method == 'POST':
        name = item.name
        # Köhnə sifarişlər pozulmur: OrderItem ad və qiyməti özündə saxlayır,
        # menu_item isə SET_NULL olur.
        item.delete()
        messages.success(request, f'{name} menyudan silindi.')
        return redirect('menu:menu_manage')
    return render(request, 'menu/manage/confirm_delete.html', {
        'restaurant': _restaurant(request),
        'profile': request.staff_profile,
        'object_name': item.name,
        'warning': 'Köhnə sifarişlərdə bu yeməyin adı və qiyməti qalacaq. '
                   'Müvəqqəti yoxdursa, silmək əvəzinə "Bitdi" düyməsini istifadə edin.',
    })


def _category_form_view(request, category=None):
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.restaurant = _restaurant(request)  # restoranı formdan YOX, sessiyadan götürürük
        obj.save()
        messages.success(request, f'"{obj.name}" kateqoriyası yadda saxlanıldı.')
        return redirect('menu:menu_manage')
    return render(request, 'menu/manage/category_form.html', {
        'restaurant': _restaurant(request),
        'profile': request.staff_profile,
        'form': form,
        'category': category,
    })


@manager_required
def category_create(request):
    return _category_form_view(request)


@manager_required
def category_edit(request, pk):
    return _category_form_view(request, _get_category(request, pk))


@manager_required
def category_delete(request, pk):
    category = _get_category(request, pk)
    if category.items.exists():
        # CASCADE bütün yeməkləri də silərdi. Təsadüfən bütöv bölməni
        # itirməmək üçün yalnız boş kateqoriyanı silməyə icazə veririk.
        messages.error(request, 'Kateqoriyada yemək var. Əvvəlcə yeməkləri silin və ya başqa kateqoriyaya köçürün.')
        return redirect('menu:menu_manage')
    if request.method == 'POST':
        category.delete()
        messages.success(request, f'"{category.name}" kateqoriyası silindi.')
        return redirect('menu:menu_manage')
    return render(request, 'menu/manage/confirm_delete.html', {
        'restaurant': _restaurant(request),
        'profile': request.staff_profile,
        'object_name': category.name,
    })
