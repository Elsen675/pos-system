import os
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']


def _random_image_path(folder, filename):
    """Yüklənən faylın adını təsadüfi UUID ilə əvəz edir.

    İstifadəçinin verdiyi ad saxlanmır: adda "../" kimi qəribə simvollar,
    şəxsi məlumat və ya eyni adlı fayllar arasında toqquşma ola bilərdi.
    Uzantı formda yoxlanılır (yalnız IMAGE_EXTENSIONS).
    """
    ext = os.path.splitext(filename)[1].lower()
    return f'{folder}/{uuid.uuid4().hex}{ext}'


def item_image_path(instance, filename):
    return _random_image_path('items', filename)


def logo_image_path(instance, filename):
    return _random_image_path('logos', filename)


def generate_table_token():
    """Masa üçün təsadüfi token.

    Default kimi funksiyanın ÖZÜNÜ veririk (`default=generate_table_token`),
    çağırışın nəticəsini yox. Belə olanda Django hər yeni masa üçün funksiyanı
    yenidən çağırır və hər masa öz tokenini alır.
    `secrets` modulu kriptoqrafik cəhətdən təhlükəsiz təsadüfi ədədlər verir
    (`random` modulundan fərqli olaraq təxmin edilə bilməz).
    """
    return secrets.token_urlsafe(8)


class Restaurant(models.Model):
    name = models.CharField('ad', max_length=120)
    slug = models.SlugField('slug', unique=True)
    logo = models.ImageField(
        'loqo', upload_to=logo_image_path, blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
    )
    is_active = models.BooleanField('aktivdir', default=True)
    # Boşdursa abunə yoxdur -> xidmət söndürülür (təhlükəsiz standart).
    subscription_until = models.DateField('abunə bitmə tarixi', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'restoran'
        verbose_name_plural = 'restoranlar'
        ordering = ['name']

    def __str__(self):
        return self.name

    def is_service_active(self):
        """Xidmət yalnız restoran aktivdirsə və abunə bitməyibsə işləyir.

        Abunə `subscription_until` günü daxil olmaqla qüvvədədir.
        """
        if not self.is_active or self.subscription_until is None:
            return False
        return self.subscription_until >= timezone.localdate()

    def get_absolute_url(self):
        return reverse('menu:menu', args=[self.slug])


class Category(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField('ad', max_length=100)
    order = models.PositiveIntegerField('sıra', default=0)

    class Meta:
        verbose_name = 'kateqoriya'
        verbose_name_plural = 'kateqoriyalar'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.restaurant} / {self.name}'


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField('ad', max_length=150)
    description = models.TextField('təsvir', blank=True)
    price = models.DecimalField(
        'qiymət', max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0'))]
    )
    image = models.ImageField(
        'şəkil', upload_to=item_image_path, blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS)],
    )
    is_available = models.BooleanField('mövcuddur', default=True)
    order = models.PositiveIntegerField('sıra', default=0)

    class Meta:
        verbose_name = 'yemək'
        verbose_name_plural = 'yeməklər'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name


class Table(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='tables')
    number = models.PositiveIntegerField('masa nömrəsi')
    token = models.CharField('token', max_length=32, unique=True, default=generate_table_token)

    class Meta:
        verbose_name = 'masa'
        verbose_name_plural = 'masalar'
        ordering = ['restaurant', 'number']
        constraints = [
            models.UniqueConstraint(fields=['restaurant', 'number'], name='unique_table_number_per_restaurant'),
        ]

    def __str__(self):
        return f'{self.restaurant} — masa {self.number}'

    def regenerate_token(self):
        """Kart oğurlansa/link yayılsa köhnə linki etibarsız etmək üçün."""
        self.token = generate_table_token()
        self.save(update_fields=['token'])

    def get_menu_url(self, source='n'):
        """Karta (source='n') və ya QR-a (source='q') yazılacaq nisbi link."""
        return f'{self.restaurant.get_absolute_url()}?t={self.number}&k={self.token}&s={source}'


class ScanEvent(models.Model):
    SOURCE_NFC = 'n'
    SOURCE_QR = 'q'
    SOURCE_UNKNOWN = '?'
    SOURCE_CHOICES = [
        (SOURCE_NFC, 'NFC'),
        (SOURCE_QR, 'QR'),
        (SOURCE_UNKNOWN, 'Naməlum'),
    ]

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='scans')
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name='scans')
    source = models.CharField('mənbə', max_length=1, choices=SOURCE_CHOICES, default=SOURCE_UNKNOWN)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'skan'
        verbose_name_plural = 'skanlar'
        ordering = ['-created_at']


class StaffProfile(models.Model):
    """İstifadəçini restorana bağlayır. Panel yalnız bu profilin restoranını göstərir."""

    ROLE_MANAGER = 'manager'
    ROLE_STAFF = 'staff'
    ROLE_CHOICES = [
        (ROLE_MANAGER, 'Menecer'),
        (ROLE_STAFF, 'İşçi'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='staff')
    # Standart dəyər ən az səlahiyyətli roldur: səhvən yaradılan hesab menyunu dəyişə bilməsin.
    role = models.CharField('rol', max_length=10, choices=ROLE_CHOICES, default=ROLE_STAFF)

    class Meta:
        verbose_name = 'işçi profili'
        verbose_name_plural = 'işçi profilləri'

    def __str__(self):
        return f'{self.user} @ {self.restaurant} ({self.get_role_display()})'

    @property
    def is_manager(self):
        return self.role == self.ROLE_MANAGER


class Order(models.Model):
    STATUS_NEW = 'new'
    STATUS_ACCEPTED = 'accepted'
    STATUS_PREPARING = 'preparing'
    STATUS_READY = 'ready'
    STATUS_SERVED = 'served'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_NEW, 'Yeni'),
        (STATUS_ACCEPTED, 'Qəbul edildi'),
        (STATUS_PREPARING, 'Hazırlanır'),
        (STATUS_READY, 'Hazırdır'),
        (STATUS_SERVED, 'Verildi'),
        (STATUS_CANCELLED, 'Ləğv edildi'),
    ]
    FINISHED_STATUSES = (STATUS_SERVED, STATUS_CANCELLED)

    PAY_TABLE = 'table'
    PAY_ONLINE = 'online'
    PAY_METHOD_CHOICES = [
        (PAY_TABLE, 'Masada'),
        (PAY_ONLINE, 'Onlayn'),
    ]

    PAY_UNPAID = 'unpaid'
    PAY_PENDING = 'pending'
    PAY_PAID = 'paid'
    PAY_FAILED = 'failed'
    PAY_REFUNDED = 'refunded'
    PAY_STATUS_CHOICES = [
        (PAY_UNPAID, 'Ödənilməyib'),
        (PAY_PENDING, 'Gözləyir'),
        (PAY_PAID, 'Ödənilib'),
        (PAY_FAILED, 'Uğursuz'),
        (PAY_REFUNDED, 'Qaytarılıb'),
    ]

    # Müştəriyə yalnız UUID göstərilir: ardıcıl id (1, 2, 3...) ilə başqasının
    # sifarişini təxmin etmək olardı, UUID-i təxmin etmək praktiki mümkün deyil.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name='orders')
    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField('status', max_length=12, choices=STATUS_CHOICES, default=STATUS_NEW)
    note = models.TextField('qeyd', blank=True)
    total = models.DecimalField('cəmi', max_digits=10, decimal_places=2, default=Decimal('0'))
    pay_method = models.CharField('ödəniş üsulu', max_length=10, choices=PAY_METHOD_CHOICES, default=PAY_TABLE)
    pay_status = models.CharField('ödəniş statusu', max_length=10, choices=PAY_STATUS_CHOICES, default=PAY_UNPAID)

    # Masada ödəniş: işçi pulu (nağd və ya POS terminal) aldıqdan sonra qeyd edir.
    # Kim və nə vaxt qeyd etdiyi saxlanılır ki, kassada uyğunsuzluq olanda yoxlamaq olsun.
    PAID_VIA_CASH = 'cash'
    PAID_VIA_TERMINAL = 'terminal'
    PAID_VIA_CHOICES = [
        (PAID_VIA_CASH, 'Nağd'),
        (PAID_VIA_TERMINAL, 'Terminal'),
    ]
    paid_via = models.CharField('necə ödənilib', max_length=10, choices=PAID_VIA_CHOICES, blank=True)
    paid_at = models.DateTimeField('ödəniş vaxtı', null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='ödənişi qeyd edən',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'sifariş'
        verbose_name_plural = 'sifarişlər'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['restaurant', 'status', 'created_at']),
            models.Index(fields=['table', 'status', 'created_at']),
        ]

    def __str__(self):
        return f'Sifariş {str(self.public_id)[:8]} — masa {self.table.number}'

    # İş axınının ardıcıllığı. Status yalnız İRƏLİ gedə bilər (addım atlamaq olar,
    # məsələn new -> ready), geri qayıtmaq olmaz. served və cancelled sondur.
    STATUS_FLOW = [STATUS_NEW, STATUS_ACCEPTED, STATUS_PREPARING, STATUS_READY, STATUS_SERVED]

    def allowed_next_statuses(self):
        """Bu sifariş hazırkı vəziyyətdən hansı statuslara keçə bilər."""
        if self.status in self.FINISHED_STATUSES:
            return []
        position = self.STATUS_FLOW.index(self.status)
        allowed = self.STATUS_FLOW[position + 1:]
        # Ödənilmiş sifarişi birbaşa ləğv etmək olmaz: əvvəlcə menecer ödənişi
        # geri almalıdır. Yoxsa "ləğv edilib, amma pul alınıb" kimi qarışıq qalar.
        if self.pay_status != self.PAY_PAID:
            allowed.append(self.STATUS_CANCELLED)
        return allowed

    def can_transition_to(self, new_status):
        return new_status in self.allowed_next_statuses()

    @property
    def short_id(self):
        return str(self.public_id)[:8]

    def get_absolute_url(self):
        return reverse('menu:order_status', args=[self.public_id])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    # Yemək silinsə belə sifariş tarixçəsi qalsın deyə SET_NULL.
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True)
    # SNAPSHOT: sifariş anındakı ad və qiymət. Menyuda qiymət sonradan dəyişsə
    # köhnə sifarişin məbləği dəyişmir.
    name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'sifariş sətri'
        verbose_name_plural = 'sifariş sətirləri'

    def __str__(self):
        return f'{self.quantity} × {self.name}'

    @property
    def line_total(self):
        return self.unit_price * self.quantity
