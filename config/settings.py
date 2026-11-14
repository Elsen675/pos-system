"""
Layihə tənzimləmələri.

Sirlər (SECRET_KEY və s.) koda yazılmır: `.env` faylından və ya mühit
dəyişənlərindən oxunur. `.env` git-ə düşmür (bax: .gitignore), nümunə üçün
`.env.example` faylına bax.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env faylını oxuyuruq. Artıq mühitdə olan dəyişənlər üstün tutulur
# (serverdə systemd/docker ilə verilən dəyərləri .env pozmasın).
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [x.strip() for x in os.environ.get(name, default).split(',') if x.strip()]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    # Açar olmadan işə salmırıq: təsadüfən açarsız istehsala çıxmasın.
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY təyin edilməyib. .env.example faylını .env kimi köçürün.'
    )

DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
# Saytın tam ünvanı (məs. https://istifadeci.pythonanywhere.com). NFC kartlara
# və QR kodlara yazılan linklər bununla qurulur. Boşdursa linklər nisbi olur.
SITE_URL = os.environ.get('DJANGO_SITE_URL', '').rstrip('/')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'menu',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# İnkişafda SQLite. PostgreSQL-ə keçid 9-cu bənddə (yerləşdirmə) edilir.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

if len(sys.argv) > 1 and sys.argv[1] == 'test':
    # Testlərdə sürətli (zəif) hash: real şifrə yoxdur, testlər ~5 dəfə tez keçir.
    # Real işdə yuxarıdakı standart, güclü PBKDF2 hash istifadə olunur.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

LANGUAGE_CODE = 'az'
TIME_ZONE = 'Asia/Baku'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/panel/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Cookie-lər JS-dən oxunmasın (sessiya). CSRF cookie-ni JS oxumalıdır,
# çünki sifariş fetch() ilə göndərilir və X-CSRFToken başlığı lazımdır.
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SECURE_REFERRER_POLICY = 'same-origin'

if not DEBUG:
    # İstehsalda (HTTPS arxasında):
    # - cookie-lər yalnız HTTPS ilə göndərilir (açıq Wi-Fi-də oğurlanmasın);
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # - server proksi (PythonAnywhere / Nginx) arxasındadır; HTTPS-i proksi
    #   qəbul edir və bunu X-Forwarded-Proto başlığı ilə bildirir;
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # - http:// ilə gələni https://-ə yönləndir (PythonAnywhere-də "Force HTTPS"
    #   da eyni işi görür, ona görə .env ilə söndürmək olar);
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    # - HSTS: brauzer bu saytı N saniyə yalnız HTTPS ilə açır. Əvvəlcə kiçik
    #   dəyərlə (məs. 3600) yoxlayın; səhv olsa brauzerlər saytı aça bilməz.
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # pythonanywhere.com alt domenlərinə toxunmuruq

# Xətalar konsola (PythonAnywhere-də "error log"-a) yazılır.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'django': {'handlers': ['console'], 'level': os.environ.get('DJANGO_LOG_LEVEL', 'WARNING')},
    },
}

if DEBUG:
    # İnkişafda "göndərilən" e-poçtlar konsola yazılır. Layihə hələ e-poçt
    # göndərmir; lazım olanda istehsal üçün SMTP .env-dən qurulacaq.
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.console.EmailBackend',
        },
    }

# HSTS alt domenləri və preload: hazırda sayt başqasının domenində
# (istifadeci.pythonanywhere.com) işləyir, onun alt domenlərinə qayda qoymaq
# bizim işimiz deyil. Öz domenimizə keçəndə (9-cu bənd) bunlara yenidən baxılır.
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']

# --- Biznes parametrləri ---
# Eyni masadan ORDER_RATE_WINDOW_MINUTES ərzində ən çox ORDER_RATE_LIMIT "new" sifariş.
ORDER_RATE_LIMIT = 3
ORDER_RATE_WINDOW_MINUTES = 10
ORDER_MAX_LINES = 50
ORDER_MAX_QTY_PER_LINE = 20
ORDER_NOTE_MAX_LENGTH = 500
