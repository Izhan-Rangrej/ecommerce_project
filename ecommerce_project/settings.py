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
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from django.core.exceptions import ImproperlyConfigured

from ecommerce_project.dburl import is_pooled_host, parse_database_url

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
_INSECURE_SECRET_KEY_DEFAULT = 'django-insecure-change-me-in-env-file'
SECRET_KEY = os.environ.get('SECRET_KEY', _INSECURE_SECRET_KEY_DEFAULT)

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

# ---------------------------------------------------------------------------
# Render auto-wiring (PHASE 21)
# ---------------------------------------------------------------------------
# Render sets these two variables FOR YOU on every web service, at build
# time AND at runtime:
#     RENDER_EXTERNAL_HOSTNAME = shopsphere-abc123.onrender.com
#     RENDER_EXTERNAL_URL      = https://shopsphere-abc123.onrender.com
# Trusting them means the very first deploy answers on its free subdomain
# without you having to type the domain anywhere — no DisallowedHost 400,
# no CSRF rejection on login. Your own ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS
# entries are still added on top (that's how a custom domain joins in).
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '').strip()

if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

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

# Same idea as above: Render's own https:// subdomain is trusted
# automatically, so POST forms (login, add-to-cart, checkout) work on the
# first deploy. Django requires the scheme, which RENDER_EXTERNAL_URL has.
if RENDER_EXTERNAL_URL and RENDER_EXTERNAL_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(RENDER_EXTERNAL_URL)


# ---------------------------------------------------------------------------
# Refuse to launch with a known-insecure secret key (PHASE 21)
# ---------------------------------------------------------------------------
# The placeholder above is committed in this repository, so it is public.
# If a production site ever ran with it, anyone could forge session and
# password-reset cookies and walk into /admin/ as you. That failure is
# silent — the site looks perfectly healthy — so we make it loud instead.
#
# Deliberately NOT enforced while DEBUG=True (local development) or for
# offline management commands that never serve a request to a browser.
_OFFLINE_MANAGEMENT_COMMANDS = {
    'test', 'collectstatic', 'makemigrations', 'showmigrations',
    'diffsettings', 'help', 'check', 'compilemessages', 'makemessages',
}
# First non-flag argument of the process: 'migrate', 'runserver', 'test', …
# For gunicorn/WSGI it is something like 'ecommerce_project.wsgi:application',
# which is NOT in the set above — so serving traffic is always checked.
_current_command = next(
    (arg for arg in sys.argv[1:] if not arg.startswith('-')), ''
)

if (
    not DEBUG
    and _current_command not in _OFFLINE_MANAGEMENT_COMMANDS
    and (
        not SECRET_KEY.strip()
        or SECRET_KEY == _INSECURE_SECRET_KEY_DEFAULT
        or SECRET_KEY.startswith('django-insecure-')
    )
):
    raise ImproperlyConfigured(
        'Refusing to start with DEBUG=False and an insecure SECRET_KEY.\n'
        'The placeholder key is public in this repository, so anyone could '
        'forge session and password-reset cookies.\n\n'
        'Generate a strong one and set it in the environment:\n'
        '  python -c "import secrets; print(secrets.token_urlsafe(50))"\n\n'
        'On Render: Dashboard -> your service -> Environment -> SECRET_KEY\n'
        '(the bundled render.yaml generates one for you automatically).\n'
        'Locally: put SECRET_KEY=... in your .env file.'
    )


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
# PostgreSQL-ready, and configured for **Neon** out of the box.
#
# THREE ways to point the store at a database, checked in this order:
#
#   1. DATABASE_URL  (RECOMMENDED — what Neon gives you)
#        DATABASE_URL=postgresql://user:pass@ep-xxx-pooler
#                       .ap-southeast-1.aws.neon.tech/neondb?sslmode=require
#      Paste the whole string. Nothing to split, nothing to get wrong.
#
#   2. PG* variables (the spelling Neon's own docs use)
#        PGHOST / PGDATABASE / PGUSER / PGPASSWORD / PGPORT
#
#   3. DB_* variables (the original local-development spelling)
#        DB_ENGINE / DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT
#
#   With none of the three set you get SQLite — zero-config local dev.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
# Neon also gives you a DIRECT (non-pooled) string — same, without
# `-pooler` in the hostname. `build.sh` uses it for `migrate`, because
# running migrations through PgBouncer's transaction pooling is the classic
# source of "prepared statement already exists" errors.
DIRECT_DATABASE_URL = os.environ.get('DIRECT_DATABASE_URL', '').strip()

PGHOST = os.environ.get('PGHOST', '').strip()
DB_ENGINE = os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3')
DB_NAME = os.environ.get('DB_NAME', '').strip()


def _postgres_from_pg_vars():
    """Build a Postgres config from Neon's PG* variables, or None."""
    if not PGHOST:
        return None
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('PGDATABASE', '').strip() or 'neondb',
        'USER': os.environ.get('PGUSER', '').strip(),
        'PASSWORD': os.environ.get('PGPASSWORD', ''),
        'HOST': PGHOST,
        'PORT': os.environ.get('PGPORT', '5432').strip() or '5432',
        'OPTIONS': {'sslmode': os.environ.get('DB_SSLMODE', 'require')},
    }


def _database_config():
    """Pick the first configuration source that is actually set."""
    # 1. one full connection string (Neon / Render / Supabase / Railway)
    from_url = parse_database_url(DATABASE_URL)
    if from_url:
        return from_url

    # 2. Neon's documented PG* spelling
    from_pg = _postgres_from_pg_vars()
    if from_pg:
        return from_pg

    # 3. explicit DB_* spelling — SQLite by default
    if 'sqlite3' in DB_ENGINE:
        # For SQLite, "NAME" is a FILE PATH. Default: db.sqlite3 in root.
        return {
            'ENGINE': DB_ENGINE,
            'NAME': DB_NAME or str(BASE_DIR / 'db.sqlite3'),
            'USER': '', 'PASSWORD': '', 'HOST': '', 'PORT': '',
            'OPTIONS': {},
        }

    # For PostgreSQL/MySQL, "NAME" is just the database name.
    return {
        'ENGINE': DB_ENGINE,
        'NAME': DB_NAME or 'ecommerce_db',
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
        'OPTIONS': {'sslmode': os.environ.get('DB_SSLMODE', 'require')},
    }


_db = _database_config()

# ---------------------------------------------------------------------------
# Serverless-Postgres connection handling (PHASE 21)
# ---------------------------------------------------------------------------
# Neon is *serverless*: it suspends the compute after ~5 minutes of
# inactivity and drops every open connection. A pooled endpoint additionally
# puts PgBouncer in *transaction* mode between you and the database.
# Both facts need Django settings that a normal long-lived Postgres
# doesn't. Getting them wrong shows up as intermittent
# `SSL SYSCALL error: EOF detected` / `server closed the connection
# unexpectedly` in production — hours after a successful deploy, which is
# what makes it so confusing.
# ---------------------------------------------------------------------------
if 'postgresql' in _db['ENGINE']:
    _pooled = is_pooled_host(_db.get('HOST', ''))

    # --- TLS ------------------------------------------------------------
    # Neon and every other managed provider require an encrypted connection,
    # so 'require' is the right default for a remote host. A Postgres on your
    # own laptop (or in a local Docker container) usually has no certificate,
    # and 'require' would reject it outright — so for a loopback host we
    # downgrade to 'prefer', which still upgrades to TLS when the server
    # offers it. An explicit DB_SSLMODE always wins over both.
    _db_host = _db.get('HOST', '')
    _loopback = _db_host in ('localhost', '127.0.0.1', '::1', '') or \
        _db_host.startswith('/')          # a Unix socket path
    _explicit_sslmode = os.environ.get('DB_SSLMODE', '').strip()
    if _explicit_sslmode:
        _db['OPTIONS']['sslmode'] = _explicit_sslmode
    elif _loopback and _db['OPTIONS'].get('sslmode') == 'require':
        _db['OPTIONS']['sslmode'] = 'prefer'

    # PgBouncer in transaction mode hands a *different* server connection to
    # each transaction, so a named (server-side) cursor created in one
    # transaction is gone by the next. Django must not use them.
    # Costs nothing here: this project never calls .iterator() on huge
    # querysets. Overridable with DB_DISABLE_SERVER_SIDE_CURSORS=False.
    _db['DISABLE_SERVER_SIDE_CURSORS'] = env_bool(
        'DB_DISABLE_SERVER_SIDE_CURSORS', default=True
    )

    # Before reusing a connection, ping it and reconnect if it is dead.
    # This is Neon's own recommendation and the direct fix for the
    # "EOF detected" error after the compute wakes from idle.
    _db['CONN_HEALTH_CHECKS'] = env_bool('DB_CONN_HEALTH_CHECKS', default=True)

    # How long (seconds) one connection may be reused across requests.
    # 0 = open per request and close it again — the safest value with a
    # pooler in front, and cheap because PgBouncer does the real pooling.
    # Neon's rule: never exceed the scale-to-zero delay (300s default).
    _db['CONN_MAX_AGE'] = int(os.environ.get(
        'DB_CONN_MAX_AGE', '0' if _pooled else '60'
    ))

    # Fail the connection attempt in bounded time instead of hanging a
    # gunicorn worker while Neon cold-starts.
    _db['OPTIONS'].setdefault('connect_timeout', '10')

# Tell the rest of the project (and the tests) what we ended up with.
DB_IS_POSTGRES = 'postgresql' in _db['ENGINE']
DB_IS_POOLED = DB_IS_POSTGRES and is_pooled_host(_db.get('HOST', ''))

DATABASES = {'default': _db}


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
# Extra origins the Content-Security-Policy may load IMAGES from. Leave
# empty while product photos are served from our own /media/; fill it in
# (comma-separated, WITH https://) when you move uploads to a CDN or object
# storage, or the browser will refuse every image. See core/middleware.py.
CSP_EXTRA_IMG_SRC = os.environ.get('CSP_EXTRA_IMG_SRC', '')
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
    # PHASE 21: the *Compressed* variant additionally writes a .gz (and
    # .br where possible) next to every file at build time, so whitenoise
    # serves pre-compressed bytes with no CPU cost per request. On the
    # free tier's 5 GB of included bandwidth that is a real saving.
    # (Run collectstatic BEFORE setting DEBUG=False — the platform's
    # build command does this automatically.)
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND':
                'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }


# ---------------------------------------------------------------------------
# Logging (PHASE 21)
# ---------------------------------------------------------------------------
# Render shows you whatever the process writes to stdout/stderr — and
# nothing else. Django's *default* logging sends 500-level errors to the
# `mail_admins` handler, which silently drops them when ADMINS is empty.
# So out of the box a live store could be throwing errors on every request
# and the dashboard would look perfectly calm.
#
# This routes warnings/errors to the console instead. Skipped while
# DEBUG=True: the dev server already prints tracebacks, and the test suite
# would be buried in noise.
# ---------------------------------------------------------------------------
if not DEBUG:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '[{levelname}] {asctime} {name} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
        },
        'loggers': {
            # Every failed request, with its traceback -> Render logs.
            'django.request': {
                'handlers': ['console'],
                'level': 'ERROR',
                'propagate': False,
            },
            # Security warnings (e.g. a disallowed Host header).
            'django.security': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': ['console'],
                # Keep at WARNING: DEBUG-level here would print every query.
                'level': os.environ.get('SQL_LOG_LEVEL', 'WARNING'),
                'propagate': False,
            },
        },
    }
