from django import forms

from .models import Category, MenuItem

MAX_IMAGE_SIZE_MB = 5


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'order']


class MenuItemForm(forms.ModelForm):
    """Menecerin yemək formu.

    `restaurant` mütləq verilməlidir: kateqoriya siyahısı yalnız həmin
    restoranın kateqoriyaları ilə məhdudlaşdırılır. ModelChoiceField
    göndərilən id-ni bu siyahıda yoxlayır, ona görə menecer brauzerdə
    HTML-i dəyişib başqa restoranın kateqoriya id-sini göndərsə, form
    "düzgün seçim deyil" xətası verir.
    """

    class Meta:
        model = MenuItem
        fields = ['category', 'name', 'description', 'price', 'image', 'is_available', 'order']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'}),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}),
        }
        labels = {'is_available': 'Mövcuddur (bitməyib)'}

    def __init__(self, *args, restaurant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(restaurant=restaurant)
        self.fields['category'].empty_label = None
        self.fields['price'].help_text = 'Manatla, məsələn 12.50'

    def clean_image(self):
        image = self.cleaned_data.get('image')
        # Yeni fayl yüklənibsə ölçüsünü yoxlayırıq. Faylın həqiqətən şəkil
        # olduğunu ImageField özü Pillow ilə yoxlayır (adı .jpg olan mətn
        # faylı keçmir), uzantını isə modeldəki FileExtensionValidator.
        if image and hasattr(image, 'size') and image.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(f'Şəkil {MAX_IMAGE_SIZE_MB} MB-dan böyük olmamalıdır.')
        return image
