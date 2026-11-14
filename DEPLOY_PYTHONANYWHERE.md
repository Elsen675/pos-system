# PythonAnywhere-ə yerləşdirmə (pulsuz test serveri)

Nəticədə sayt `https://ISTIFADECI.pythonanywhere.com` ünvanında işləyəcək.
Aşağıda `ISTIFADECI` gördüyünüz hər yerə **öz PythonAnywhere istifadəçi adınızı** yazın.

Təxmini vaxt: 20–30 dəqiqə. Hər şey brauzerdən edilir.

---

## 1. Kodu GitHub-a yükləyin (öz kompüterinizdə, bir dəfə)

1. https://github.com/new açın.
   - Repository name: `restoranlar`
   - **Private** seçin (kod sizin biznesinizdir).
   - README, .gitignore, license əlavə **etməyin**.
   - "Create repository" basın.
2. Layihə qovluğunda terminal açıb (VS Code və ya PowerShell) işlədin:
   ```
   git remote add origin https://github.com/GITHUB_ADINIZ/restoranlar.git
   git push -u origin main
   ```
   İlk dəfə brauzer açılıb GitHub girişini soruşacaq — daxil olun.

> `.env`, `db.sqlite3`, `media/`, `venv/` git-ə düşmür (bax: `.gitignore`).
> Yəni sirləriniz və yerli məlumatlarınız GitHub-a getmir.

### Serverin private repo-nu oxuması üçün token
1. https://github.com/settings/personal-access-tokens/new
2. Token name: `pythonanywhere`, Expiration: 90 gün.
3. Repository access: **Only select repositories** → `restoranlar`.
4. Permissions → Repository permissions → **Contents: Read-only**.
5. "Generate token" — tokeni kopyalayın (bir dəfə göstərilir). Aşağıda `git clone` şifrə
   soruşanda bu tokeni yapışdıracaqsınız.

---

## 2. PythonAnywhere hesabı

1. https://www.pythonanywhere.com → **Pricing & signup** → **Create a Beginner account** (pulsuz).
2. İstifadəçi adı saytın ünvanı olacaq: `ISTIFADECI.pythonanywhere.com`. Fikirləşib seçin.

---

## 3. Bash konsolunda quraşdırma

PythonAnywhere-də **Consoles → Bash** açın və əmrləri bir-bir işlədin:

```bash
git clone https://github.com/GITHUB_ADINIZ/restoranlar.git
# Username: GitHub adınız, Password: yuxarıdakı TOKEN

cd restoranlar
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### .env faylı (sirlər)
Aşağıdakı blokda **yalnız `ISTIFADECI` sözünü dəyişin**, sonra hamısını birlikdə yapışdırın.
Gizli açar avtomatik yaradılır, heç yerə yazmağa ehtiyac yoxdur.

```bash
SITE=ISTIFADECI.pythonanywhere.com
cat > .env <<EOF
DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$SITE
DJANGO_CSRF_TRUSTED_ORIGINS=https://$SITE
DJANGO_SITE_URL=https://$SITE
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_HSTS_SECONDS=3600
EOF
cat .env | grep -v SECRET   # yoxlama (açarı ekrana çıxarmırıq)
```

> `DJANGO_SECURE_SSL_REDIRECT=False` — HTTPS yönləndirməsini PythonAnywhere özü edəcək
> (6-cı addımda "Force HTTPS"). İkisi birlikdə lazım deyil.

### Baza, statik fayllar, hesablar
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py createsuperuser       # platforma admini (siz)
python manage.py seed_demo             # demo restoran, 5 masa, 2 işçi hesabı
```

`seed_demo` masa linklərini və **demo_menecer / demo_isci şifrələrini** çap edir — onları qeyd edin.
(Yenidən işlətsəniz şifrələr dəyişir.)

---

## 4. Web app yaradın

**Web** bölməsi → **Add a new web app** → Next →
**Manual configuration** seçin (⚠️ "Django" sehrbazını YOX) → **Python 3.13** → Next.

Açılan səhifədə:

| Bölmə | Dəyər |
|---|---|
| Source code | `/home/ISTIFADECI/restoranlar` |
| Working directory | `/home/ISTIFADECI/restoranlar` |
| Virtualenv | `/home/ISTIFADECI/restoranlar/venv` |

---

## 5. WSGI faylı

Web səhifəsində **WSGI configuration file** linkinə basın
(`/var/www/ISTIFADECI_pythonanywhere_com_wsgi.py`). İçindəkiləri **tamamilə silin** və bunu yazın:

```python
import os
import sys

path = '/home/ISTIFADECI/restoranlar'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

**Save** basın. (`.env` faylını `config/settings.py` özü oxuyur.)

---

## 6. Statik fayllar, şəkillər, HTTPS

Web səhifəsində **Static files** bölməsinə iki sətir əlavə edin:

| URL | Directory |
|---|---|
| `/static/` | `/home/ISTIFADECI/restoranlar/staticfiles` |
| `/media/` | `/home/ISTIFADECI/restoranlar/media` |

**Security** bölməsində **Force HTTPS** → **Enabled**.

Səhifənin yuxarısında yaşıl **Reload** düyməsini basın.

---

## 7. Yoxlama

1. `https://ISTIFADECI.pythonanywhere.com/admin/` — superuser ilə girin.
   **Masalar** siyahısında hər masanın tam NFC/QR linki var.
2. Masa linkini telefona göndərin (məs. özünüzə WhatsApp/Telegram ilə) və açın.
3. Başqa telefonda `https://ISTIFADECI.pythonanywhere.com/accounts/login/` → `demo_isci`.
4. Kompüterdə → `demo_menecer`.

Səhvlər olsa: **Web → Log files → Error log** (ən aşağıdakı sətirlər).

> Qeyd: Kökdə (`/`) səhifə yoxdur və 404 verir — bu normaldır. Şifrəsiz demo giriş
> yalnız yerli kompüterdə işləyir, serverdə həmişə söndürülüb.

### Bir neçə cihazda test planı
| Cihaz | Rol | Nə edir |
|---|---|---|
| Telefon 1 | Müştəri | Masa linki → sifariş, "Ofisiantı çağır", "Hesab istəyirəm" |
| Telefon 2 | İşçi (`demo_isci`) | Panel → "Səsi aktiv et" → statuslar, "Ödənildi", Masalar |
| Kompüter | Menecer (`demo_menecer`) | Menyu ("Bitdi", qiymət, şəkil), Hesabat |

Telefonda bildiriş üçün paneldə "🔔 Səsi aktiv et" basıb icazə verin.
Android Chrome-da panel tabı açıq qaldıqca (arxa planda da) bildiriş gəlir.
iPhone-da bildiriş yalnız sayt "Əsas ekrana əlavə et" ilə quraşdırılanda işləyir.

---

## 8. Kodu yeniləmək (hər dəfə mən dəyişiklik edəndən sonra)

Öz kompüterinizdə:
```
git push
```
PythonAnywhere Bash konsolunda:
```bash
cd ~/restoranlar
source venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```
Sonra **Web → Reload**.

---

## Pulsuz hesabın məhdudiyyətləri
- Web app pulsuz hesabda vaxtaşırı uzadılmalıdır: Web səhifəsində
  **"Run until 3 months from today"** düyməsi. Hesaba uzun müddət girilməsə dayandırıla bilər.
- Disk 512 MB — test üçün kifayətdir; şəkilləri çox böyük yükləməyin (forma 5 MB-a qədər icazə verir).
- Baza SQLite-dır. Real restoran üçün VPS + PostgreSQL + gündəlik backup (9-cu bənd) lazımdır.
  **Bu serverdə real restoranın məlumatlarını saxlamayın** — test üçündür.
