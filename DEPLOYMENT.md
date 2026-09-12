# Deploying ShopSphere — Render (app) + Neon (database)

This takes you from "the site runs on my laptop" to "the site is live on
the internet with its own https:// address". It is written for **Render**
(hosting) + **Neon** (PostgreSQL), the pair this repository is configured
for out of the box.

Everything the server needs is already in the code. Since Phase 21 the
whole deployment is described in one versioned file — **`render.yaml`** —
so launching is mostly clicking, not typing.

> **How this project is shaped:** ShopSphere is a *Django monolith*. The
> HTML pages, the admin panel, the cart/checkout logic and the API are all
> one Python application. So there is no separate "frontend" to deploy:
> **Render runs the whole app** (pages *and* logic), and **Neon is its
> database**. Two services, not three.

---

## 0. The six things that change between laptop and internet

| Thing | On your laptop | On the server |
|---|---|---|
| Server process | `python manage.py runserver` | **gunicorn** (production WSGI server) |
| Database | SQLite file `db.sqlite3` | **PostgreSQL on Neon** (serverless, free tier) |
| Debug mode | `DEBUG=True` | `DEBUG=False` (activates the whole HTTPS block in `settings.py`) |
| Static files | Django serves `static/` live | `collectstatic` → hashed + gzip/brotli files, served by **whitenoise** |
| Secrets | your `.env` file | **Environment variables** in the hosting dashboard (never put your real `.env` on the server) |
| Hostname | `localhost:8000` | `https://yourapp.onrender.com` (trusted automatically — see §3) |

All of it is driven by environment variables, so the *same code* runs in
both places — only the values differ.

---

## 1. Push your code to GitHub (one time)

Render reads your code from a Git repository.

```bat
cd ecommerce_project
git add .
git commit -m "ShopSphere — deployment config (Phase 21)"
git push
```

**Expected result:** the repository on GitHub contains `manage.py`,
`Procfile`, `render.yaml`, `build.sh`, `requirements.txt`,
`.python-version`, `ecommerce_project/`, … and **not** `.env`,
`db.sqlite3`, `staticfiles/` or `venv/` (`.gitignore` handles that).

> Verify `render.yaml` and `build.sh` are both at the repository **root** —
> Render only looks there.

---

## 2. Create the Neon database FIRST

Do this before Render: the Blueprint asks you to paste the connection
string, so it has to exist already.

1. Sign in at **https://neon.tech** (free; GitHub login works).
2. **New Project** →
   - **Name:** `shopsphere`
   - **Region:** **AWS Asia Pacific (Singapore)** — `aws-ap-southeast-1`
   - **Database name:** `neondb` (the default is fine)
   - **Postgres version:** the newest offered (17+). Django 6.1 dropped
     support for Postgres 14.
3. Click **Create Project**. On the dashboard, open **Connect**.
4. Copy **two** strings:

   | Which | Looks like | Goes into |
   |---|---|---|
   | **Pooled** connection | `postgresql://neondb_owner:PASS@ep-amber-meadow-123456`**`-pooler`**`.ap-southeast-1.aws.neon.tech/neondb?sslmode=require` | `DATABASE_URL` |
   | **Direct** connection | exactly the same, but **without `-pooler`** in the hostname | `DIRECT_DATABASE_URL` |

   > **Why two?** The pooled endpoint is PgBouncer in *transaction* mode —
   > great for serving traffic, unreliable for running migrations
   > (`prepared statement "__django_migrate_1" already exists`). `build.sh`
   > migrates over the direct string and serves traffic over the pooled one.
   > `DIRECT_DATABASE_URL` is optional; leave it out and migrations just use
   > the pooled URL.

5. Keep both strings somewhere handy for the next step.

> **You do not need to split these into host/user/password/port.** That was
> the old Phase-20 advice (and it said port `6432`, which is wrong for
> Neon — Neon's pooled endpoint answers on `5432`). Phase 21 accepts the
> whole URL and parses it, which is why a password containing `@`, `/` or
> `:` no longer breaks the deploy.

---

## 3. Deploy with the Blueprint (recommended)

`render.yaml` describes the entire service — region, plan, build command,
start command, health check and every environment variable.

1. Sign in at **https://render.com**.
2. **New +** → **Blueprint** → connect your `ecommerce_project` repository.
3. Render finds `render.yaml` and shows you what it will create:
   one web service named `shopsphere`, free plan, Singapore.
4. It then **prompts you for the 7 secret values** (these are the
   `sync: false` entries — Render asks once, here, and never stores them in
   git):

   | Prompt | Paste |
   |---|---|
   | `DATABASE_URL` | the **pooled** Neon string (§2) |
   | `DIRECT_DATABASE_URL` | the **direct** Neon string (§2) |
   | `DJANGO_SUPERUSER_USERNAME` | e.g. `admin` |
   | `DJANGO_SUPERUSER_EMAIL` | your email |
   | `DJANGO_SUPERUSER_PASSWORD` | a strong password you will remember |

   Leave a field blank only if you genuinely do not want it (e.g. you will
   add the admin later). `SECRET_KEY` is **not** prompted — Render
   generates a strong random one for you (`generateValue: true`).

5. **Apply**. Render builds and deploys. Watch **Logs** until you see
   *Application deployed successfully*.

You get a URL like **`https://shopsphere.onrender.com`** (Render appends a
short suffix if that name is already taken by someone else).

### What you do NOT have to configure

`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are deliberately absent from
`render.yaml`. Render sets `RENDER_EXTERNAL_HOSTNAME` and
`RENDER_EXTERNAL_URL` on every web service, and `settings.py` trusts them
automatically — so the first deploy answers on its own subdomain with no
`DisallowedHost` 400 and no CSRF rejection on login. You only add those two
variables when you attach a **custom domain** (§5).

### What the build does

`build.sh` (called by the Blueprint) runs, in order:

```
pip install -r requirements.txt          # dependencies
manage.py collectstatic --noinput --clear # hashed + gzipped static files
manage.py migrate --noinput               # schema, over the DIRECT url
manage.py create_admin                    # superuser from env vars (idempotent)
manage.py seed_data --refresh-images      # demo catalogue (see the note below)
```

Read `build.sh` — each step has a comment explaining why it is there and in
that order. Two of them matter more than they look:

- **`collectstatic` runs before `migrate`.** With `DEBUG=False`, Django's
  manifest static storage makes *every* page 500 if the manifest is
  missing. Doing it first means a database problem can never take the CSS
  down with it.
- **`--refresh-images` is not optional on Render.** Render's filesystem is
  **ephemeral** while Neon is **persistent**. On the second deploy the
  product rows are still in the database, but `media/products/seed/*.jpg`
  has been wiped. Plain `seed_data` sees the products, decides there is
  nothing to do, and leaves the photos missing — every image on the live
  site 404s. The flag regenerates any placeholder whose file is gone.
  Photos you upload through the admin are never touched.

### Turning the demo catalogue off

`SEED_DEMO_DATA=true` (the default) loads 7 categories, 7 brands, 18
products, 3 coupons and a `demo` / `Demo@1234` customer on every deploy.
The command is idempotent — it only creates what is missing, so a re-deploy
never duplicates anything.

When you are ready to run a real catalogue, set **`SEED_DEMO_DATA=false`**
in Render → Environment. The build then skips seeding entirely and leaves
your data alone.

---

## 4. Verifying the live site

Open your `https://….onrender.com` URL and work down this list:

- [ ] home page renders **with product photos**
- [ ] `/shop/` — filters, sorting and "Page 2" work
- [ ] `/healthz/` → `{"status": "ok"}`
- [ ] `/healthz/?db=1` → `{"status": "ok", "database": "ok"}`
      (this one may take a few seconds — it deliberately wakes Neon)
- [ ] log in with `demo` / `Demo@1234`
- [ ] add to cart → checkout → Cash on Delivery → order placed
- [ ] `/admin/` → log in with the superuser you set in §3
- [ ] `/sitemap.xml` → XML, `/robots.txt` → text
- [ ] open the browser dev tools → Network → the CSS is served with
      `Content-Encoding: gzip` and a hashed filename
      (`style.2480e0e57740.css`)

Then confirm the production posture from your laptop:

```bat
python manage.py check --deploy
```

It must print **"System check identified no issues"**. (Locally it needs a
`.env` with `DEBUG=True`, otherwise the settings guard in §14 stops it.)

---

## 5. Custom domain + HTTPS (later, optional)

1. Buy a domain (Namecheap, GoDaddy, Cloudflare…).
2. Render → your service → **Settings → Custom Domain** → enter
   `shop.yourdomain.com` and add the DNS records it shows. Render issues
   the TLS certificate automatically.
3. Now add these **two** environment variables (Render → Environment).
   The `onrender.com` hostname stays trusted automatically, so you only
   list your own domain:
   ```
   ALLOWED_HOSTS=shop.yourdomain.com
   CSRF_TRUSTED_ORIGINS=https://shop.yourdomain.com
   ```
   Comma-separated if you have several (`shop.example.com,www.example.com`).
   `CSRF_TRUSTED_ORIGINS` entries **must** include `https://`.
4. **Manual Deploy**. Done — green lock.

---

## 6. What to do before you let real customers in

| Item | Why | How |
|---|---|---|
| Delete the `demo` account | `demo`/`Demo@1234` is printed in this document | `/admin/` → Users → delete `demo`; also set `SEED_DEMO_DATA=false` |
| Real product photos | the seeded tiles are generated placeholders | `/admin/` → Products → change images (see the media warning below) |
| Real prices, stock, shipping, tax | business truth | `/admin/`, plus `TAX_RATE` / `STANDARD_SHIPPING_FEE` / `FREE_SHIPPING_THRESHOLD` in `settings.py` |
| Real email (§7) | password reset + order confirmation | six environment variables |
| Razorpay **live** keys (§8) | real payments | two environment variables |
| Backups | Neon's free tier has no automatic backups | Neon → **History → Restore** rolls back to any past state (free). For real data, export periodically |

### ⚠️ Uploaded photos do not survive a deploy (free tier)

Render's free plan has an **ephemeral filesystem** and **cannot attach a
persistent Disk** (disks require a paid plan). Consequences:

- The generated **seed** images are fine — `build.sh` regenerates them on
  every deploy (`--refresh-images`).
- Photos **you upload through `/admin/`** are written to `media/`, which is
  wiped on the next deploy. The database still points at them, so they 404.

Three ways to fix it, cheapest first:

1. **Commit the images to git.** Put real photos in `static/images/products/`
   and point products at `/static/...` instead of `/media/...`. Static files
   are part of the build, so they survive every deploy. Fine for a small,
   fixed catalogue.
2. **Upgrade Render to Starter ($7/mo)** and attach a Disk. Then set
   `MEDIA_ROOT=/var/data/media` in Environment — `settings.py` already reads
   that variable, and `build.sh` needs no change. Uploads now persist.
3. **Move uploads to object storage / a CDN** (Cloudinary, S3, Cloudflare
   R2) — the proper long-term answer. When you do, remember the
   Content-Security-Policy: add the new host to **`CSP_EXTRA_IMG_SRC`**
   (comma-separated, with `https://`) or the browser will refuse to display
   every image. See `core/middleware.py`.

---

## 7. Real email (password reset, order confirmation)

Until now `EMAIL_BACKEND` is the console backend: mail is printed into
**Render → Logs** instead of being sent. That is fine for a first launch
(you can read a password-reset link straight out of the log), but not for
real customers.

Easiest free option — **Gmail app password**:

1. Google Account → Security → enable **2-Step Verification**, then
   **App passwords** → create one (copy the 16-character value).
2. Render → Environment, add:
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=abcd-efgh-ijkl-mnop
   DEFAULT_FROM_EMAIL=you@gmail.com
   ```
3. **Manual Deploy**. Test: request a password reset — the mail arrives,
   and its link points at your live domain.

Business alternatives (same six variables, different values): Brevo,
Mailgun, Amazon SES.

---

## 8. Real payments (Razorpay live mode)

The store **auto-detects**. While both Razorpay variables are empty it uses
its built-in test gateway and `PAYMENT_LIVE` stays `False` — no real money
moves. To go live:

1. Razorpay dashboard → Settings → API Keys → switch to **Live** mode
   (needs a KYC-verified business account).
2. Render → Environment:
   ```
   RAZORPAY_KEY_ID=rzp_live_...
   RAZORPAY_KEY_SECRET=...
   ```
3. **Manual Deploy**, then place one real end-to-end order.

---

## 9. After every code change

```bat
git add .
git commit -m "describe the change"
git push
```

Render sees the push and re-deploys automatically (`autoDeploy: true` in
`render.yaml`). Watch **Logs** until *Application deployed successfully*.

Editing `render.yaml` itself is also version-controlled: push the change and
Render applies it. **One exception** — `sync: false` secrets are only
prompted for during the *first* Blueprint creation. Add new secrets by hand
in the Environment tab afterwards.

---

## 10. Free-tier realities (normal, not errors)

**Render free web service**

- Sleeps after **15 minutes** with no traffic. The next request takes
  **30–60 seconds** to wake it. A visitor sees a slow first page, then
  normal speed. Only the **$7/mo Starter** plan removes this.
- 512 MB RAM, 0.1 CPU, **one instance** (cannot scale horizontally).
- Your workspace gets **750 free instance-hours/month** — enough for one
  service running continuously.
- No persistent Disk, no SSH, no one-off jobs.

**Neon free database**

- The compute **suspends after ~5 minutes** idle. The first query after
  that takes a moment — `CONN_HEALTH_CHECKS=True` (already set) makes
  Django reconnect transparently instead of erroring.
- **0.5 GB** storage — plenty for this store and its photos.
- Free-plan projects that stay **inactive for 90+ days** are subject to
  deletion. Visit the console occasionally.
- Neon's superpower here: **branching**. Before a risky migration, create a
  branch and point `DATABASE_URL` at it — a throwaway copy of production in
  one click.

**Combined effect:** after a quiet period, the very first request pays both
cold starts (Render waking + Neon waking). Expect a slow first page load,
not a failure. `/healthz/` deliberately avoids the database so Render's
health probe never trips over a sleeping Neon.

---

## 11. Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Build fails: `Could not find a version that satisfies the requirement Django>=6.1` | Python is older than 3.12. Django 6.1 needs 3.12+. `.python-version` pins **3.13** — make sure that file is committed at the repo root |
| Build fails: `Refusing to start with DEBUG=False and an insecure SECRET_KEY` | The guard from §14. Set `SECRET_KEY` in Environment (`python -c "import secrets; print(secrets.token_urlsafe(50))"`). The Blueprint generates one for you — this means it was cleared |
| First load: `DisallowedHost` / 400 | Your domain is missing from `ALLOWED_HOSTS`. On the free `onrender.com` URL this can't happen (auto-wired); for a custom domain see §5 |
| Endless redirect loop | Shouldn't happen — `SECURE_PROXY_SSL_HEADER` is set and Render always sends `X-Forwarded-Proto`. If it does, check that header in the request log |
| White 500 on every page | Database variables wrong (§2), or `migrate` never ran → read the build log |
| `Endpoint ID is not specified` connecting to Neon | `psycopg2-binary` too old (its bundled `libpq` lacks TLS SNI). `requirements.txt` floors it at **2.9.10** — check the build log for a pip downgrade |
| `SSL SYSCALL error: EOF detected`, intermittently, hours after a successful deploy | Neon suspended the compute and Django reused a dead connection. Already handled (`CONN_HEALTH_CHECKS=True`, `CONN_MAX_AGE=0` on pooled hosts). If you overrode `DB_CONN_MAX_AGE`, keep it ≤ 300 |
| `prepared statement "__django_migrate_1" already exists` during migrate | You migrated through the **pooled** URL. Set `DIRECT_DATABASE_URL` (§2) — `build.sh` uses it automatically |
| Styles missing / 404 on `style.*.css` | `collectstatic` didn't run → check the build log. It is step 1 of `build.sh` |
| **Product photos all 404 after a re-deploy** | `seed_data` ran without `--refresh-images`. `build.sh` passes it; if you typed the build command by hand, add it |
| Photos uploaded via `/admin/` vanish after a deploy | Ephemeral filesystem — see §6, three fixes |
| CSRF error on login/checkout | `CSRF_TRUSTED_ORIGINS` missing or lacking `https://` → §5 |
| Password-reset mail not arriving | Email variables not set → §7. Meanwhile the mail is printed in **Render → Logs** |
| `gunicorn` crashes: `Address already in use` | You typed a start command with a fixed port. Use `$PORT` (the Blueprint does) |
| Site is slow on the first visit after a while | Normal on the free tier — §10 |

### Reading the logs

`settings.py` now routes Django's warnings and errors to the console
(§14), so **Render → Logs** shows real tracebacks, CSRF rejections and
`DisallowedHost` attempts. Before Phase 21 those were handed to Django's
default `mail_admins` handler and silently dropped, because `ADMINS` is
empty — a live store could 500 on every request and the dashboard would
look calm. Raise verbosity temporarily with `LOG_LEVEL=DEBUG`.

---

## 12. Alternative platforms (same recipe)

The repository is not Render-specific — `Procfile`, `build.sh` and the
environment variables are portable.

- **Railway** (https://railway.app): New Project → from GitHub repo →
  Build: `./build.sh` → Start: `gunicorn ecommerce_project.wsgi:application --bind 0.0.0.0:$PORT`.
  Set the same variables. Railway offers a persistent volume, which solves
  §6 properly: mount it and set `MEDIA_ROOT`.
- **Fly.io**: has a **Mumbai (BOM)** region, the only one of the three that
  is actually in India — worth it if your customers are Indian and the
  ~100–150 ms from Singapore matters. Same `Procfile`.
- **A VPS** (DigitalOcean / Linode / Hetzner): Ubuntu + systemd + gunicorn.
  whitenoise already serves static files, so Nginx is optional. Same
  environment variables; `SECURE_PROXY_SSL_HEADER` is already set.
- **Render's own Postgres instead of Neon?** Also fine. Create
  New → PostgreSQL, then set `DATABASE_URL` from its `connectionString`.
  Note the free Render database **expires 30 days after creation**; Neon's
  free tier does not.

**Region pairing matters more than platform.** This app is server-rendered:
one page issues many small database queries, and *each* pays the app→database
round trip. Keep Render and Neon in the **same region** (both Singapore).
Render in Oregon with Neon in Singapore would add ~150 ms to *every query*.

---

## 13. Launch checklist

- [ ] Code pushed to GitHub — `render.yaml`, `build.sh`, `.python-version`
      all at the repo **root**, `.env` **not** committed
- [ ] Neon project created in **AWS Asia Pacific (Singapore)**, Postgres 17+
- [ ] Pooled **and** direct connection strings copied
- [ ] Render Blueprint applied; the 5 prompts answered
- [ ] Build log shows migrate + collectstatic + seed all succeeding
- [ ] `https://….onrender.com` loads with product photos
- [ ] `/healthz/` and `/healthz/?db=1` both return `ok`
- [ ] Full COD checkout completes as `demo` / `Demo@1234`
- [ ] `/admin/` reachable with your superuser
- [ ] `python manage.py check --deploy` prints "no issues"
- [ ] Media-persistence decision made (§6)
- [ ] Real email configured and a password reset received (§7)
- [ ] `SEED_DEMO_DATA=false` + `demo` user deleted, once real products are in
- [ ] Razorpay live keys set and one real order placed (§8)
- [ ] Custom domain + DNS + the two origin variables (§5)

---

## 14. What Phase 21 changed in the code

None of this needs you to edit anything — it is here so you know what the
configuration does and can explain it.

| File | Change | Why |
|---|---|---|
| **`render.yaml`** *(new)* | The whole service as code: region, plan, build/start commands, health check, env vars | One-click launch; no build command mistyped into a text box; re-creatable |
| **`build.sh`** *(new)* | The build as a versioned script | Ordered, commented, identical on every deploy |
| **`.python-version`** *(new)* | Pins Python **3.13** | Django 6.1 requires ≥ 3.12. Render's default moves over time — pinning makes builds reproducible |
| **`ecommerce_project/dburl.py`** *(new)* | Parses one Postgres URL into Django's six DB fields | You paste Neon's string instead of hand-splitting it. Handles percent-encoded passwords and passwords containing `@` |
| **`settings.py`** | Accepts `DATABASE_URL`, or Neon's `PG*` vars, or the old `DB_*` vars, or falls back to SQLite | One-string config; nothing existing broke |
| **`settings.py`** | `CONN_HEALTH_CHECKS=True`, `CONN_MAX_AGE=0` on pooled hosts, `DISABLE_SERVER_SIDE_CURSORS=True`, `connect_timeout` | Neon suspends idle computes and its pooler runs PgBouncer in transaction mode. Without these you get intermittent `SSL SYSCALL error: EOF detected` **in production only**, hours after a good deploy |
| **`settings.py`** | Trusts `RENDER_EXTERNAL_HOSTNAME` / `RENDER_EXTERNAL_URL` | The first deploy works with zero host configuration |
| **`settings.py`** | **Refuses to start** with `DEBUG=False` and the placeholder `SECRET_KEY` | That placeholder is public in this repo. Anyone knowing it could forge session and password-reset cookies and walk into `/admin/`. The failure was silent; now it is loud |
| **`settings.py`** | Console logging for `django.request` / `django.security` when `DEBUG=False` | Django's default mails errors to `ADMINS`, which is empty → they vanished. Now they appear in Render's logs |
| **`settings.py`** | `CompressedManifestStaticFilesStorage` | Pre-gzips static files at build time: `style.css` 62 KB → 12 KB on the wire, no per-request CPU |
| **`settings.py`** | `sslmode` downgrades to `prefer` for loopback hosts | A local Postgres has no TLS certificate; `require` rejected it. Remote hosts still force TLS |
| **`settings.py`** | `CSP_EXTRA_IMG_SRC` | Lets you move images to a CDN without the CSP silently blocking every photo (§6) |
| **`core/views.py`** | `/healthz/` endpoint — answers **without** touching the database | Render's probe would otherwise wait on both cold starts and restart healthy instances. `?db=1` does a real check for humans |
| **`requirements.txt`** | `psycopg2-binary>=2.9.10` | Neon routes connections with TLS SNI, which needs `libpq` ≥ 14. Older builds fail with `Endpoint ID is not specified` |
| **`Procfile`** | `--workers ${WEB_CONCURRENCY:-2}`, logs to stdout | Worker count configurable per environment; works on Railway/Fly/Heroku too |
| **`core/tests.py`** | +19 tests (URL parsing, health probe, CSP) → **88 total** | These are the parts that only break in production, so they are tested here instead |

### Two things worth knowing about running 2 workers

`WEB_CONCURRENCY=2` suits the free tier's 512 MB, but two in-process caches
are per-worker rather than shared:

- **The rate limiter** (`core/ratelimit.py`) keeps its buckets in process
  memory, so the effective limit is roughly doubled, and it resets on every
  deploy. Fine for launch; move it to Redis or the database if you need it
  to be exact.
- **The navbar cache** is invalidated by Django signals, which only fire in
  the worker that handled the admin change. Another worker can show a stale
  category list for up to its 5-minute TTL.

Both are cosmetic at this scale. Setting `WEB_CONCURRENCY=1` makes them
exact at the cost of throughput.
