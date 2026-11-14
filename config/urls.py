from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Platforma idarəsi'
admin.site.site_title = 'Platforma idarəsi'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('menu.urls')),
]

if settings.DEBUG:
    # İstehsalda media faylları Nginx tərəfindən verilir.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Demo başlanğıc səhifəsi və şifrəsiz demo giriş — YALNIZ inkişafda.
    urlpatterns += [path('', include('menu.dev_urls'))]
