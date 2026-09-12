# Deploying ShopSphere — Phase 20 guide (beginner friendly)

This document takes you from "the site runs on my laptop" to "the site is
live on the internet with its own https:// address". It is written for
**Render** (https://render.com) as the main path — it is free for a first
launch, gives you HTTPS and a subdomain automatically, and needs no
server administration. The notes at the end cover Railway and a VPS.

Nothing in this guide changes your local project. Everything the server
needs is already in the code (WSGI config, `Procfile`, production
settings). Your job is: push the code, point the server at it, and set
the environment variables.

---

## 0. The five things that change between laptop and internet

| Thing | On your laptop | On the server |
|---|---|---|
| Server process | `python manage.py runserver` | **gunicorn** (production WSGI server) |
| Database | SQLite file `db.sqlite3` | **PostgreSQL on Neon** (serverless, free tier) |
| Debug mode | `DEBUG=True` | `DEBUG=False` (activates the whole HTTPS block in `settings.py`) |
| Static files | Django serves `static/` live | `collectstatic` → hashed files in `staticfiles/`, served by **whitenoise** |
| Secrets | your `.env` file | **Environment variables** typed into the hosting dashboard (never put your real `.env` on the server) |

All of the above is driven by environment variables, so the same code
runs in both places — only the *values* differ.

---

## 1. Push your code to GitHub (one time)

Hosting platforms read your code from a GitHub repository.

```bat
cd E:\ecommerce_project
git init
git add .
git commit -m "ShopSphere — full e-commerce store (Phase 20)"
```

Then on **https://github.com/new** create an empty repository
(name: `ecommerce_project`, **do not** tick README/gitignore), and in the
CMD window:

```bat
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ecommerce_project.git
git push -u origin main
```

**Expected result:** `Branch 'main' set up to track remote branch 'main'`
and your project (with `.env`, `db.sqlite3`, `media/`, `venv/` all
excluded — `.gitignore` takes care of that) on GitHub.

> Verify: on the GitHub page you should see `manage.py`, `Procfile`,
> `requirements.txt`, `ecommerce_project/`, … and **not** `.env`.

---

## 2. Create the web service on Render

1. Sign in at https://render.com (free account, GitHub login).
2. **New → Web Service** → pick your `ecommerce_project` repository.
3. On the setup screen:
   - **Name:** anything (e.g. `shopsphere`)
   - **Region:** closest to you (e.g. Oregon / Frankfurt)
   - **Runtime:** Python
   - **Build Command:**
     ```
     pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic && python manage.py create_admin && python manage.py seed_data
     ```
   - **Start Command:** leave it as auto-detected — Render reads your
     `Procfile` and runs gunicorn for you. (If it asks, type:
     `gunicorn ecommerce_project.wsgi:application`)
4. Click **Create Web Service**. You get a free URL like
   `https://shopsphere-abc123.onrender.com`.

The build command does, in order: install packages → create the database
tables → gather static files → load the demo catalogue (18 products,
demo customer, coupons). Every future deploy repeats this automatically.

---

## 3. Database: create Neon and set the DB variables

The free tier has **no** database, so without this step the site 500s on
the first page. We use **Neon** (https://neon.tech) — a serverless
PostgreSQL with a free tier.

1. Sign in at **https://neon.tech** (free account, GitHub login works).
2. Click **Start a new project** → give it a name (e.g. `shopsphere`)
   and a region (e.g. Oregon or Frankfurt — pick the one closest to
   Render's region).
3. When the project is ready, open the **Connection Details** panel.
   You will see a **pooled connection string** that looks like:

   ```
   postgresql://neondb_owner:AbCd1234@ep-amber-meadow-123456-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

4. **Decode it** — everything between `://` and `@` is `user:password`,
   then comes the host, then `/dbname`:

   | Part of the string | Goes into |
   |---|---|
   | `neondb_owner` (before the `:`) | `DB_USER` |
   | `AbCd1234` (after the `:`, before `@`) | `DB_PASSWORD` |
   | `ep-amber-meadow-123456-pooler.us-east-2.aws.neon.tech` (after `@`, before `/`) | `DB_HOST` |
   | `neondb` (after the last `/`) | `DB_NAME` |
   | pooled endpoint → always | `DB_PORT` = `6432` |
   | `?sslmode=require` | already handled by the code (TLS is forced for any Postgres) |

5. Open your **Web Service → Environment** tab and add:

   | Variable | Value |
   |---|---|
   | `DB_ENGINE` | `django.db.backends.postgresql` |
   | `DB_NAME` | (the database name from step 4) |
   | `DB_USER` | (the user from step 4) |
   | `DB_PASSWORD` | (the password from step 4) |
   | `DB_HOST` | (the host from step 4 — keep the full string, it is NOT a domain you can shorten) |
   | `DB_PORT` | `6432` |

6. **Re-deploy** the web service (Deploy → Manual Deploy) so the build
   command runs `migrate` against Neon and creates all tables.

> **Neon free-tier behaviours (normal, not errors):**
> - The database **auto-suspends after ~5 minutes** of idle. The first
>   request after that pause takes a few extra seconds to wake it up.
> - Free storage is 0.5 GB — plenty for this store and its photos.
> - If you ever need a *second, throwaway* database to test changes,
>   Neon can **branch** your database in one click — great for trying
>   risky migrations.

> **Prefer Render's own Postgres instead?** Same idea: New → PostgreSQL,
> then set `DB_HOST` to the *internal* hostname and `DB_PORT` to `5432`
> (everything else identical).

## 4. The rest of the environment variables

Web Service → **Environment** tab, add all of these:

| Variable | Value for the free subdomain | What it does |
|---|---|---|
| `DEBUG` | `False` | switches on HTTPS hardening (settings.py production block) |
| `SECRET_KEY` | a long random string (generate locally: `python -c "import secrets; print(secrets.token_urlsafe(50))"`) | MUST differ from your laptop's |
| `ALLOWED_HOSTS` | `shopsphere-abc123.onrender.com` | the site's address (add more domains later, comma-separated) |
| `CSRF_TRUSTED_ORIGINS` | `https://shopsphere-abc123.onrender.com` | with the `https://` prefix |
| `EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` | for the first launch (mail prints to the service logs). Replace with real SMTP in step 7 |
| `DEFAULT_FROM_EMAIL` | e.g. `shopsphere@example.com` | |
| `RAZORPAY_KEY_ID` | *(leave empty for now)* | empty = built-in test gateway stays active |
| `RAZORPAY_KEY_SECRET` | *(leave empty for now)* | |

**Then Deploy → Manual Deploy once more.**

### Verifying the live site

Open your `https://….onrender.com` URL:

- [ ] home page renders with product photos
- [ ] `/shop/` filters + "Page 2" work
- [ ] log in with `demo` / `Demo@1234`
- [ ] add to cart → checkout → Cash on Delivery → order placed
- [ ] `https://….onrender.com/admin/` → log in with your superuser
      (create one on the server: see "Creating an admin on the server" below)
- [ ] `https://….onrender.com/sitemap.xml` → XML

> **Creating an admin on the server:** add these three to the
> Environment tab (the build command's `create_admin` step creates the
> account on the first deploy, and skips it afterwards — it can never
> break a re-deploy):
>
> | Variable | Value |
> |---|---|
> | `DJANGO_SUPERUSER_USERNAME` | e.g. `admin` |
> | `DJANGO_SUPERUSER_EMAIL` | e.g. `you@gmail.com` |
> | `DJANGO_SUPERUSER_PASSWORD` | a strong password you remember |
>
> (Locally you already have your own superuser from `createsuperuser` —
> this only affects the server's database.)

---

## 5. Custom domain + HTTPS (later, optional)

1. Buy a domain (Namecheap, GoDaddy, Google Domains…).
2. Render → Web Service → **Settings → Custom Domain** → enter
   `shop.yourdomain.com`, add the DNS records it shows to your
   registrar. Render issues a certificate automatically.
3. Update the two variables (add, don't replace — keep the onrender.com
   address too until DNS propagates):
   - `ALLOWED_HOSTS=shopsphere-abc123.onrender.com,shop.yourdomain.com`
   - `CSRF_TRUSTED_ORIGINS=https://shopsphere-abc123.onrender.com,https://shop.yourdomain.com`
4. Manual Deploy. Done — `https://shop.yourdomain.com` with a green lock.

---

## 6. What to do before you let real customers in

| Item | Why | How |
|---|---|---|
| Strong `SECRET_KEY` + unique per environment | session/token security | step 4 |
| Delete the demo account before going public | `demo`/`Demo@1234` is in this doc | admin → users → delete `demo` |
| Real product photos | the seeded tiles are placeholders | admin → Products → change images (they upload to `/media/`) |
| Real prices, stock, shipping fee | business truth | admin, and `STANDARD_SHIPPING_FEE` / `TAX_RATE` in `settings.py` |
| Real email (step 7) | password reset + order confirmation | below |
| Razorpay **live** keys (step 8) | real payments | below |
| Backups | Neon free tier: no automatic backups — click **History → Restore** to roll back to any past state (free); for real data, keep a periodic export | Neon project → History tab |
| Media persistence | the free tier wipes `/media/` on every deploy — re-deploys re-seed, but photos uploaded via admin are LOST | attach a **persistent Disk** (paid, ~$) mounted at `/var/data` and set `MEDIA_ROOT=/var/data/media` in Environment; or move images to Cloudinary/S3 later |

---

## 7. Real email (password reset, order confirmation)

Easiest free option — **Gmail app password**:

1. A Google account with 2FA enabled → Google Account → Security →
   **App passwords** → create one (copy the 16-character password).
2. Environment variables:
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=abcd-efgh-ijkl-mnop
   DEFAULT_FROM_EMAIL=you@gmail.com
   ```
3. Manual Deploy. Test: request a password reset — the mail arrives, and
   the reset link points at the live domain (no more "console" mail).

Free-for-business alternative: Mailgun / Amazon SES / Brevo (same six
variables, different values).

---

## 8. Real payments (Razorpay live mode)

The store auto-detects: as long as both Razorpay variables are empty it
uses the built-in **test** gateway. To go live:

1. Razorpay dashboard → Settings → API Keys → **switch to Live mode**
   (you must have a KYC-verified business account).
2. Copy the **Key ID** and **Key Secret**.
3. Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in Environment.
4. Manual Deploy. `PAYMENT_LIVE` flips to `True` and checkout talks to
   the real gateway. Keep the test numbers in mind for one last
   end-to-end order, then you're open for business.

---

## 9. After every code change

```bat
git add .
git commit -m "describe the change"
git push
```

Render sees the push and re-deploys automatically (build command runs
`migrate` + `collectstatic` + `seed_data` — the seed is idempotent, it
only fills what's missing). Watch **Deploy → Logs** until it says
*Application deployed successfully*.

---

## 10. Troubleshooting

| Symptom | Cause → fix |
|---|---|
| First load: `DisallowedHost` / 400 | domain missing from `ALLOWED_HOSTS` → step 4, re-deploy |
| Endless redirect loop | (shouldn't happen — `SECURE_PROXY_SSL_HEADER` is set) if it does: check the web service receives the `X-Forwarded-Proto` header (Render always does) |
| White 500 on every page | database variables wrong → step 3; or `migrate` never ran → check build logs |
| Styles missing / 404 on `style.*.css` | `collectstatic` didn't run (it's in the Build Command) or whitenoise missing from `requirements.txt` → re-deploy and watch the build log |
| Product photos missing after re-deploy | free tier is ephemeral → step 6 (persistent disk) |
| Password-reset mail not arriving | email variables not set → step 7; check the web service **logs** — the console backend prints the mail there |
| `psycopg2` import error | `DB_ENGINE` points to postgres but psycopg2 isn't installed → it IS in `requirements.txt`; check the build log for pip errors |
| CSRF error on login/checkout in production | `CSRF_TRUSTED_ORIGINS` missing or without `https://` → step 4/5 |
| `gunicorn` crashes with `Address already in use` | you typed a start command with a fixed port — use the `Procfile` one (`$PORT`) |
| Free web service sleeps | normal — the first request after ~15 min idle takes ~30 s to wake; a paid plan removes this |

---

## 11. Alternative platforms (same recipe)

- **Railway** (https://railway.app): New Project → from GitHub repo →
  add a **Postgres** plugin (or point the six `DB_*` at your existing
  Neon string) → set the same environment variables → Build:
  `python manage.py migrate && python manage.py collectstatic && python manage.py seed_data`
  → Start: `gunicorn ecommerce_project.wsgi:application`. Railway also
  gives you a persistent disk for `/media/` (their `$RAILWAY_VOLUME_MOUNT_PATH`).
- **VPS (DigitalOcean / Linode / AWS)**: the "professional" route —
  Ubuntu + systemd + gunicorn (whitenoise already serves the static
  files, so Nginx is optional). More control, more chores (firewalls,
  certificates, upgrades). The app side stays identical: same
  `Procfile`, same environment variables, `SECURE_PROXY_SSL_HEADER`
  already set. Happy to walk through it phase-by-phase whenever
  you want.

---

## 12. Launch checklist (tick as you go)

- [ ] Code pushed to GitHub (`.env` NOT in the repo)
- [ ] Render web service created with the Build Command from step 2
- [ ] Neon project created + six `DB_*` variables set
- [ ] `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` set
- [ ] Manual deploy finished; home page + `/shop/` + a full COD checkout work
- [ ] Admin reachable; demo account decision made (keep for now)
- [ ] Real email configured (step 7) — password reset tested
- [ ] Razorpay live keys set (step 8) — one test order placed
- [ ] Domain + DNS + the two origin variables updated (step 5)
- [ ] Backups on (Postgres) — media persistence plan decided (step 6)
