#!/usr/bin/env bash
# =============================================================================
# build.sh — everything Render runs to turn a git commit into a live site.
#
# Referenced from render.yaml (`buildCommand: ./build.sh`) and from
# DEPLOYMENT.md for the manual-dashboard route. Keeping it in a file rather
# than as one long dashboard string means it is versioned, reviewable, and
# identical on every deploy.
#
# Runs on Linux/macOS (Render). On Windows it is not needed — locally you run
# the same steps by hand: see README.md.
# =============================================================================

# Fail the whole build on the first error (-e), on unset variables (-u), and
# if any part of a pipe fails (-o pipefail). Without this, a failed
# `pip install` would be ignored and the service would boot half-built.
set -euo pipefail

echo "==> Python: $(python --version 2>&1)"
echo "==> Working directory: $(pwd)"

# -----------------------------------------------------------------------------
# 1. Dependencies
# -----------------------------------------------------------------------------
# --upgrade pip first: an old pip can fail to resolve newer wheels (Pillow,
# psycopg2-binary) and the resulting error message is very confusing.
echo "==> Installing dependencies"
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

# -----------------------------------------------------------------------------
# 2. Static files  (BEFORE the database steps)
# -----------------------------------------------------------------------------
# collectstatic copies our CSS/JS/images plus Django's admin assets into
# staticfiles/, where whitenoise serves them. It also writes the hashed
# manifest that CompressedManifestStaticFilesStorage needs — and with
# DEBUG=False a missing manifest makes EVERY page 500. So it runs before
# anything that could abort the build.
echo "==> Collecting static files"
python manage.py collectstatic --noinput --clear

# -----------------------------------------------------------------------------
# 3. Database schema
# -----------------------------------------------------------------------------
# Migrations run against the DIRECT (non-pooled) Neon connection when you
# have provided one. Reason: a pooled endpoint is PgBouncer in *transaction*
# mode, which discards session state between transactions. Django's
# migration executor opens long transactions and uses advisory locks, and
# through a pooler that intermittently fails with
#     prepared statement "__django_migrate_1" already exists
# or hangs on the lock. Neon's own guidance is to migrate over a direct
# connection. Serving traffic afterwards still uses the fast pooled one.
#
# If DIRECT_DATABASE_URL is not set we simply use DATABASE_URL, and if
# neither exists (local SQLite development) the variable stays empty and
# settings.py falls back to db.sqlite3.
echo "==> Applying migrations"
MIGRATE_URL="${DIRECT_DATABASE_URL:-${DATABASE_URL:-}}"
DATABASE_URL="$MIGRATE_URL" python manage.py migrate --noinput

# -----------------------------------------------------------------------------
# 4. Admin account
# -----------------------------------------------------------------------------
# Reads DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD. Idempotent: it
# creates the account on the first deploy and prints "already exists" after
# that, so it can never break a re-deploy. If the variables are absent it
# just skips with a warning.
echo "==> Ensuring admin account"
python manage.py create_admin

# -----------------------------------------------------------------------------
# 5. Demo catalogue
# -----------------------------------------------------------------------------
# SEED_DEMO_DATA=false turns this off once you are ready to run a real
# catalogue (see DEPLOYMENT.md). The command itself is idempotent — it only
# creates categories/brands/products/coupons that are missing.
#
# --refresh-images is NOT optional on Render. Its filesystem is EPHEMERAL
# while Neon is persistent, so on the second and every later deploy the
# product rows still exist in the database but media/products/seed/*.jpg has
# been wiped. Plain `seed_data` sees the products, skips them, and leaves
# the photos missing — every product image on the live site 404s. The flag
# regenerates any placeholder whose file is gone. Photos you upload through
# the admin are never touched.
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
    echo "==> Seeding demo catalogue"
    python manage.py seed_data --refresh-images
else
    echo "==> SEED_DEMO_DATA is not 'true' — skipping demo catalogue"
fi

echo "==> Build complete"
