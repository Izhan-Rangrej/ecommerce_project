"""
Django settings for the `ecommerce_project` project.

From PHASE 2 onwards, everything secret or environment-specific
(secret key, debug flag, database, email, payment keys) is read from
a `.env` file in the project root using the `python-dotenv` package.

That means:
  - no secrets ever live in the code (safe to commit to Git)
  - switching from SQLite to PostgreSQL = editing .env, NOT this file
  - each developer keeps their own local .env

Beginner tip: Django reads this file once when the server starts.
The development server auto-restarts when you save changes.
"""

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR points to the folder that contains `manage.py`.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from the .env file (if it exists).
# Variables already present in the real environment take precedence.
load_dotenv(BASE_DIR / '.env')

# Small helper: read a boolean-ish value ("True", "1", "yes") from .env
def env_bool(key: str, default: bool = False) -> bool:
    """'True'/'true'/'1'/'yes' -> True, anything else -> default."""
    value = os.environ.get(key, str(default)).strip().lower()
    return value in ('1', 'true', 'yes', 'on')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# ------------------------------------------------------------------
# Core security settings (all from .env)
# ------------------------------------------------------------------
# SECURITY WARNING: keep the secret key used in production secret!
# It signs sessions, CSRF tokens and password-reset tokens.
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-in-env-file')

# DEBUG=True gives helpful error pages and dev-server conveniences.
# In production you MUST set DEBUG=False in .env.
DEBUG = env_bool('DEBUG', default=False)

# ALLOWED_HOSTS is Django's security check on the "Host" header.
# While developing, accept localhost + the sandbox preview host;
# in production, list your real domains in .env
# (e.g. ALLOWED_HOSTS=shop.example.com,www.shop.example.com).
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()
]
if DEBUG:
    # Convenience for local development: allow any host while DEBUG is on
    # (needed for sandboxed previews / Docker / VS Code tunnels).
    ALLOWED_HOSTS.append('*')

# CSRF_TRUSTED_ORIGINS — the REAL browser origins the store lives on in
# production, e.g.:
#   CSRF_TRUSTED_ORIGINS=https://yourapp.onrender.com,https://shop.example.com
# Each entry must include the scheme (https://). Comma-separated, no spaces.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',         # /admin/ backend
    'django.contrib.auth',          # users, login, permissions
    'django.contrib.contenttypes',
    'django.contrib.sessions',      # session storage (used by cart + login)
    'django.contrib.messages',      # flash messages (success/error alerts)
    'django.contrib.staticfiles',   # finds CSS/JS/images

    # Third-party
    'crispy_forms',                 # smart form rendering
    'crispy_bootstrap5',            # Bootstrap 5 style for crispy forms

    # ------------------------------------------------------------------
    # Our own apps. Roles:
    #   core      -> site pages (about/contact), context processors,
    #                error pages, sitemap/robots (later)
    #   products  -> Category, Brand, Product, ProductImage, Review, Coupon
    #   customers -> UserProfile, Address, Wishlist, NewsletterSubscriber
    #   orders    -> Order, OrderItem
    #   payments  -> Payment (COD now, gateway-ready architecture)
    #   cart      -> session-based shopping cart logic (no DB model)
    # ------------------------------------------------------------------
    'core',
    'products',
    'customers',
    'orders',
    'payments',
    'cart',
]

# Crispy Forms: which CSS framework template pack to use.
# Every form in the project is rendered with Bootstrap 5 automatically.
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # PHASE 20: serves /static/ in production (hashed files from
    # collectstatic, with proper cache headers). In development it does
    # nothing — the dev server already serves static/ on its own.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # PHASE 18: adds a Content-Security-Policy header (no Django
    # setting exists for it yet) — see core/middleware.py.
    'core.middleware.SecurityHeadersMiddleware',
]

ROOT_URLCONF = 'ecommerce_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # We keep ALL shared templates in ONE folder at the project root:
        # ecommerce_project/templates/
        'DIRS': [BASE_DIR / 'templates'],
        # Also look inside each app's own templates/ folder if one exists.
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Our own (core app): available on EVERY page
                'core.context_processors.categories',      # navbar Categories menu
                'core.context_processors.cart_count',      # navbar cart badge
                'core.context_processors.wishlist_count',  # navbar wishlist badge
            ],
        },
    },
]

WSGI_APPLICATION = 'ecommerce_project.wsgi.application'

# NOTE (Django 6+): the old `handlers403/404/500` *settings* were removed.
# Custom error views are now declared as `handler403/404/500` in urls.py
# (see ecommerce_project/urls.py).


# Database
# ---------------------------------------------------------------------------
# PostgreSQL-ready: the WHOLE database config comes from .env.
#
#   Development (default):  DB_ENGINE=django.db.backends.sqlite3
#   Production:             DB_ENGINE=django.db.backends.postgresql
#                           (+ DB_NAME/USER/PASSWORD/HOST/PORT, and
#                            pip install psycopg2-binary)
#
# No code change is needed when you switch — only the .env file.
# ---------------------------------------------------------------------------
DB_ENGINE = os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3')
DB_NAME = os.environ.get('DB_NAME', '').strip()

if 'sqlite3' in DB_ENGINE:
    # For SQLite, "NAME" is a FILE PATH. Default: db.sqlite3 in project root.
    db_name = DB_NAME or str(BASE_DIR / 'db.sqlite3')
    db_options = {}
else:
    # For PostgreSQL/MySQL, "NAME" is just the database name.
    db_name = DB_NAME or 'ecommerce_db'
    # Managed Postgres services (Neon, Render, Supabase, RDS...) require an
    # encrypted connection. 'require' forces TLS; 'prefer' negotiates it.
    # Ignored entirely when you are on SQLite.
    db_options = {'sslmode': os.environ.get('DB_SSLMODE', 'require')}

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': db_name,
        'USER': os.environ.get('DB_USER', ''),       # ignored by SQLite
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),  # ignored by SQLite
        'HOST': os.environ.get('DB_HOST', ''),        # ignored by SQLite
        'PORT': os.environ.get('DB_PORT', ''),        # ignored by SQLite
        'OPTIONS': db_options,                        # e.g. sslmode for Neon
    }
}


# Password validation
# ---------------------------------------------------------------------------
# Django hashes passwords with PBKDF2 automatically — we never store them
# in plain text. These validators enforce strength on register/change.
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Authentication redirects (used from PHASE 8 onwards)
# ---------------------------------------------------------------------------
# Where Django sends people when a view requires login,
# and where it sends them after logging in / out.
# The URL *names* ('home', 'login') are defined in urls.py later.
# ---------------------------------------------------------------------------
LOGIN_URL = 'login'
# "home" lives in the core app's URL namespace, so it must be "core:home" —
# a bare "home" would raise NoReverseMatch on the first real login.
LOGIN_REDIRECT_URL = 'core:home'
LOGOUT_REDIRECT_URL = 'core:home'


# Internationalization
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'   # the store owner's local time zone

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
# STATIC_URL         -> the URL prefix the browser requests
#                       (e.g. /static/css/style.css)
# STATICFILES_DIRS   -> real folders on disk that hold our own static files
# (In production, serve static files via Nginx or `whitenoise`, not Django.)
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
# STATIC_ROOT -> where `manage.py collectstatic` copies ALL static files
# (ours + Django's own) into ONE folder for the production server to
# serve. It is GENERATED — never edit it by hand, and keep it out of
# version control (see .gitignore).
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Media files (user-uploaded files, e.g. product images from the admin)
# ---------------------------------------------------------------------------
# MEDIA_URL  -> the URL prefix the browser requests (e.g. /media/products/...jpg)
# MEDIA_ROOT -> the real folder on disk where uploads are saved
# NOTE: actually SERVING /media/ in development is wired in urls.py
# (Django never serves media in production — a web server or CDN does).
# ---------------------------------------------------------------------------
MEDIA_URL = 'media/'
# A hosting platform can point this at a different folder (e.g. a
# persistent disk) by setting MEDIA_ROOT in its environment.
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media')))


# Business / store rules
# ---------------------------------------------------------------------------
# The SINGLE source of truth for money math. Both the cart (display) and
# order placement (receipt) import these, so what the customer sees on the
# cart page is exactly what gets charged. Adjust to your real business.
# ---------------------------------------------------------------------------
TAX_RATE = Decimal('0.05')                 # 5% tax on (subtotal - discount)
STANDARD_SHIPPING_FEE = Decimal('49')      # flat shipping fee
FREE_SHIPPING_THRESHOLD = Decimal('1000')  # free shipping at/above this amount


# Payment gateway
# ---------------------------------------------------------------------------
# Gateway keys are read ONLY from .env — never hardcoded in code.
# While the keys are empty, the store runs on the built-in TEST gateway
# (payments.gateway): a simulator, no real money moves.
# ---------------------------------------------------------------------------
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
# True only when real Razorpay keys are present in .env. When it is, the
# checkout swaps the simulator for the real gateway (see payments/gateway.py).
PAYMENT_LIVE = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


# Email
# ---------------------------------------------------------------------------
# Used by: password reset emails (PHASE 8) and order-confirmation emails.
# Development default = console backend: every email is printed to your
# terminal instead of being sent. Point these at a real SMTP provider
# (Gmail, SendGrid, SES…) in .env for real mail.
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=True)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@localhost')


# Production-only security hardening
# ---------------------------------------------------------------------------
# These are no-ops while DEBUG=True (the dev server is plain HTTP).
# When you set DEBUG=False in .env, all of these activate automatically:
#   * force HTTPS
#   * cookies only sent over HTTPS
#   * HSTS header (browsers remember "this site must be HTTPS")
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# PHASE 18 — security headers that are SAFE in every mode
# (headers, not behaviour — they cost nothing in development)
# ---------------------------------------------------------------------------
X_FRAME_OPTIONS = 'DENY'                    # clickjacking protection
SECURE_CONTENT_TYPE_NOSNIFF = True          # no MIME-type sniffing
SECURE_REFERRER_POLICY = 'same-origin'      # don't leak URLs to outsiders
# Cookies refuse cross-site requests (CSRF hardening):
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
# 2-week sessions — matches the 14-day cart.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

if not DEBUG:
    # --- HTTPS ------------------------------------------------------
    # Hosting platforms (Render, Railway, ...) put the app behind a
    # reverse proxy that terminates TLS. The proxy -> app hop is plain
    # HTTP, but the proxy sends the header 'X-Forwarded-Proto: https'.
    # Tell Django to trust that header — otherwise is_secure() is
    # False and SECURE_SSL_REDIRECT would send browsers into an
    # endless redirect loop.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7      # 1 week
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # --- static files -----------------------------------------------
    # Production serves the output of `manage.py collectstatic`
    # (STATIC_ROOT). The 'Manifest' backend rewrites references to
    # hashed file names (style.9f2ab1.css), so a browser never keeps
    # using an old cached copy after you deploy new CSS/JS.
    # (Run collectstatic BEFORE setting DEBUG=False — the platform's
    # build command does this automatically.)
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND':
                'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
        },
    }
