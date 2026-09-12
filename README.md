# ShopSphere — Django E-commerce Website

A complete, modern, responsive e-commerce website built with **Python Django**
(server-rendered, Bootstrap 5, SQLite for development, PostgreSQL-ready).

> This README is a work-in-progress. It will be finished in the final phase
> with the full feature list, screenshots and deployment instructions.

## Current status

- [x] Phase 1 — Project setup (project + 5 apps, initial settings)
- [x] Phase 2 — Settings, `.env`, static/media configuration
- [x] Phase 3 — Database models (13 models, migrations, order engine)
- [x] Phase 4 — Admin panel (customized, actions, superuser)
- [x] Phase 5 — Base frontend design (base template, design system,
                search, product detail, cart core, wishlist, error pages)
- [x] Phase 6 — Homepage (hero, categories, featured, promo, new arrivals,
                best sellers, reviews) + `seed_data` command
- [x] Phase 7 — Product/category system (`/shop/` with filters + 5 sorts +
                pagination, `/category/<slug>/` pages, product detail gallery,
                rating distribution, reviews, related products)
- [x] Phase 8 — Authentication (register, login, logout, password
                reset/change, profile, saved addresses)
- [x] Phase 9 — Cart page (line items, quantity steppers, live totals,
                free-shipping progress, stock re-validation, remove/clear)
- [x] Phase 10 — Wishlist page (saved items, ratings, stock badges,
                move-to-cart, remove — login required)
- [x] Phase 11 — Checkout (5-step flow: address → delivery → payment →
                review → order placed; COD; stock-safe order placement)
- [x] Phase 12 — Orders (history page, order detail with status timeline,
                customer cancel with stock return + refund handling)
- [x] Phase 13 — Payments (Cash on Delivery + test-mode card gateway,
                server-side validation, transaction ids, Razorpay/Stripe-ready)
- [x] Phase 14 — Coupons (apply/validate/remove at checkout: percentage
                & fixed, minimum order, max discount cap, valid window,
                usage limits — all re-validated server-side)
- [x] Phase 15 — Reviews (purchase-verified 1–5 star ratings + comment:
                only buyers can review, one per product — resubmit to
                update, live average + per-star distribution)
- [x] Phase 16 — Search, filter & sort polish (live search suggestions,
                category-aware filter links, live facet counts)
- [x] Phase 17 — Animations & UX polish (page settle, toast & image
                fade-ins, add-to-cart feedback, smooth anchors,
                focus rings — reduced-motion safe, no-JS safe)
- [x] Phase 18 — Security & optimization (rate limiting on auth +
                order/review/newsletter actions, CSP & security headers,
                SameSite cookies, cached navbar, query audit, input
                hardening — see "Security (PHASE 18)" below)
- [x] Phase 19 — Tests, SEO & sitemap (persistent `manage.py test` suite
                in every app — 69 tests, `core/testing.py` shared factories,
                sitemap.xml + robots.txt — see "Tests (PHASE 19)" below)
- [x] Phase 20 — Deployment prep (production settings: HTTPS/HSTS/cookies,
                whitenoise static files, WSGI + gunicorn `Procfile`,
                `create_admin` command, `DEPLOYMENT.md` step-by-step guide
                for Render/Railway/VPS — see "Deployment (PHASE 20)" below)

## Deployment (PHASE 20)

The store is ready to go live. The complete, beginner-friendly launch
guide — GitHub → Render (or Railway/VPS) → Postgres → environment
variables → domain → real email → real Razorpay keys — is in
**`DEPLOYMENT.md`** at the project root. Work through its launch
checklist (section 12) and the site is public.

In short, deployment needs **no code changes** — only environment
variables (`DEBUG=False`, real `SECRET_KEY`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, the six `DB_*` Postgres values, email +
gateway keys). Everything else (HTTPS hardening, hashed static files,
gunicorn start command, admin bootstrap) is already wired in.

Verify production-readiness any time (must print "no issues"):

```bat
python manage.py check --deploy
```

## Quick start (Windows)

```bat
:: 1. create & activate the virtual environment
python -m venv venv
venv\Scripts\activate

:: 2. install dependencies
pip install -r requirements.txt

:: 3. create your local environment file (once only)
copy .env.example .env
:: then edit .env and set SECRET_KEY — generate one with:
python -c "import secrets; print(secrets.token_urlsafe(50))"

:: 4. create the database + admin account + demo catalog
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data

:: 5. run
python manage.py runserver
```

Then open:
- http://127.0.0.1:8000/          (home page — hero, categories, products)
- http://127.0.0.1:8000/shop/     (the shop: search + filters + sort + pagination)
- http://127.0.0.1:8000/category/ (pick any category, e.g. `/category/electronics/`)
- http://127.0.0.1:8000/cart/     (your cart — items, quantities, live totals)
- http://127.0.0.1:8000/wishlist/  (saved items — move to cart or remove)
- http://127.0.0.1:8000/checkout/  (5-step checkout — address, delivery,
                payment, review, order placed)
- http://127.0.0.1:8000/orders/    (your order history + detail/timeline)
- http://127.0.0.1:8000/register/ (create an account)
- http://127.0.0.1:8000/accounts/login/ (log in — a demo customer exists, see below)
- http://127.0.0.1:8000/account/  (your profile + saved addresses, when logged in)
- http://127.0.0.1:8000/admin/    (admin — log in with your superuser)
- `/search/` still works (redirects to `/shop/`)

**Demo customer (for testing):** username `demo`, password `Demo@1234`
(a real customer account with one saved address, not a superuser).

`seed_data` is idempotent (safe to re-run) and supports `--flush` to wipe
and reseed. It creates 7 categories, 7 brands, 18 products (with generated
placeholder photos in `media/products/seed/`) and 3 working coupons
(`WELCOME10`, `SAVE500`, `FLAT20`).

## Configuration (`.env`)

All secrets and environment-specific values live in `.env` (git-ignored):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | signing key for sessions/CSRF |
| `DEBUG` | dev error pages; **False** in production |
| `ALLOWED_HOSTS` | comma-separated allowed domains |
| `DB_ENGINE/NAME/USER/PASSWORD/HOST/PORT` | database (SQLite default, PostgreSQL-ready) |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | email (password reset, order mail) |
| `RAZORPAY_*` / `STRIPE_*` | payment gateway keys (PHASE 13: while empty, the
                checkout runs on the built-in test gateway) |

Switching to PostgreSQL = change `DB_ENGINE` etc. in `.env` and
`pip install psycopg2-binary`. No code changes.

## Security (PHASE 18)

| Control | Where | Notes |
|---|---|---|
| Rate limiting (in-memory, per IP + action) | `core/ratelimit.py` | login 5/5 min · password-reset 5/10 min · register 3/5 min · newsletter 5/10 min · place-order 10/10 min · reviews 10/10 min. Stores timestamps only. Per-process: for multi-worker production, swap the store for Redis — call sites don't change |
| Rate-limited login / password reset | `customers/views.py` + root `urls.py` | `ThrottledLoginView` / `ThrottledPasswordResetView` shadow the stock auth URLs |
| Content-Security-Policy | `core/middleware.py` | allows only 'self' + cdn.jsdelivr.net (Bootstrap) + Google Fonts; no 'unsafe-inline' (the site has no inline scripts) |
| X-Frame-Options DENY, nosniff, Referrer-Policy | `settings.py` | active in dev AND production |
| SameSite=Lax cookies, 2-week session | `settings.py` | CSRF hardening |
| HTTPS redirect + HSTS + secure cookies | `settings.py` | auto-activate when `DEBUG=False` |
| Search-term truncation (100 chars) | `products/views.py` | protects the DB from absurdly long `q` values |
| Navbar category menu cached 5 min | `core/context_processors.py` + `core/signals.py` | invalidated by model signals — never stale by more than one admin save |
| Server-side validation everywhere | all forms | client-side hints only; the DB is the final judge (unique constraints, validators, `Order.place` re-checks) |

## Tests (PHASE 19)

Run the full suite (69 tests, ~25 s) from the project folder:

```bat
venv\Scripts\activate
python manage.py test
```

| File | What it covers |
| --- | --- |
| `core/tests.py` | security headers, login rate limiting, 403/404/500 pages, robots.txt, sitemap.xml, navbar cache invalidation |
| `customers/tests.py` | registration, login/logout, full password-reset flow, address book, wishlist, newsletter |
| `cart/tests.py` | session cart ops, stock limits, money totals |
| `products/tests.py` | shop listing, filters, sorts, facets, category page, detail, live-suggest JSON, review flow (add/edit/delete/cancel) |
| `orders/tests.py` | full checkout (COD + card paid + card declined), stock restoration, order history/cancel, coupons |
| `payments/tests.py` | gateway success / bad number / declined (pure units — no HTTP) |

Shared fixtures live in `core/testing.py` (`StoreTestCase` + factories:
products, categories, brands, customer, address, coupon, images) — tests
create their own data, never depend on `seed_data`.

### Bugs the tests found (fixed in Phase 19)

1. **Pagination links lost `page=N`** — the `link` template tag always
   dropped the `page` param, so "Page 2" links actually pointed at page 1.
2. **Live-suggest prices** — SQLite returned `899` instead of `899.00`;
   the JSON now formats money explicitly.
3. **sitemap.xml** was served as `text/html`; now `application/xml`.

## Django 6 notes (learned the hard way)

1. **Template comments are single-line only.** `{# ... #}` must not span
   lines — a multi-line block renders as visible text (and any tag inside
   it becomes LIVE).
2. **Error views live in `urls.py`** as `handler403/404/500` attributes.
   The old `handlers403/404/500` *settings* were removed in Django 6.
3. Auth URLs (`django.contrib.auth.urls`) are **not namespaced**:
   use `{% url 'login' %}`, not `{% url 'auth:login' %}`.
4. **Management commands** are loaded as top-level modules — use absolute
   imports (`from products.models import ...`), never relative (`from .models`).
5. **`RedirectView.query_string` defaults to `False`** in Django 6 — pass
   `query_string=True` if you want `?q=…` to survive a redirect.
6. **Password-reset links are "token-hiding"**: a valid reset URL 302s to a
   `…/set-password/` URL (the real token is parked in the session so it can't
   leak via the Referer header). Always test the flow with `follow=True` and
   POST to the *final* URL, not the original one.
7. **Redirect URLs must be real URL names.** `LOGIN_REDIRECT_URL = 'home'`
   raised `NoReverseMatch` because the home view is namespaced
   (`core:home`). Use the namespaced name.
