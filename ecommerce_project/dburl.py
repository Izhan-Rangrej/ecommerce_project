"""
ecommerce_project/dburl.py — turn ONE Postgres connection string into the
six separate fields Django's `DATABASES` setting expects.

Why this file exists
--------------------
Managed Postgres providers (Neon, Render, Supabase, Railway…) hand you a
single URL that looks like this:

    postgresql://neondb_owner:AbC%2F123@ep-amber-meadow-123456-pooler
                .ap-southeast-1.aws.neon.tech/neondb?sslmode=require

Django does not accept a URL — it wants:

    ENGINE / NAME / USER / PASSWORD / HOST / PORT / OPTIONS

Splitting that string by hand is the single most common cause of a broken
first deploy (a password containing `@` or `/`, a forgotten `-pooler`
suffix, a missing port). So we do it once, here, with a proper URL parser,
and unit-test it (see `core/tests.py::DatabaseUrlParsingTest`).

Deliberately dependency-free: `urllib.parse` is in the standard library,
so this adds nothing to requirements.txt.
"""

from urllib.parse import parse_qsl, unquote, urlparse

# ---------------------------------------------------------------------------
# Query-string parameters that are safe (and useful) to forward to the
# database driver. Everything else in the URL's query string is ignored —
# providers add their own tracking params and we must not pass junk to
# libpq, which would raise a connection error.
# ---------------------------------------------------------------------------
_FORWARDED_PARAMS = frozenset({
    'sslmode',            # require / verify-full / disable …  (Neon needs TLS)
    'sslrootcert',        # path to a CA bundle
    'sslcert',
    'sslkey',
    'channel_binding',    # SCRAM channel binding (Neon sometimes sets this)
    'connect_timeout',    # seconds to wait while establishing the connection
    'application_name',   # shows up in Postgres' pg_stat_activity
    'options',            # raw server options, e.g. '-c statement_timeout=…'
    'target_session_attrs',
})

# libpq's own default; used when the URL omits the port.
_DEFAULT_POSTGRES_PORT = '5432'

# Schemes we recognise as "this is a PostgreSQL URL".
_POSTGRES_SCHEMES = frozenset({'postgres', 'postgresql', 'postgis'})


def parse_database_url(url):
    """
    Parse a PostgreSQL connection URL into a Django `DATABASES` entry.

    Returns a dict ready to be used as `DATABASES['default']`, or `None`
    when `url` is empty or is not a recognisable Postgres URL (so the
    caller can fall back to SQLite without crashing).

    Handles the real-world messiness:
      * percent-encoded passwords   (`p%40ss` -> `p@ss`, `a%2Fb` -> `a/b`)
      * passwords containing `@`    (userinfo is split at the LAST `@`)
      * `postgres://` and `postgresql://` spellings
      * a missing port              (defaults to 5432)
      * `?sslmode=require` and friends -> forwarded into OPTIONS
    """
    if not url or not url.strip():
        return None

    url = url.strip()

    # `urlparse` needs a scheme to find the network location. A bare
    # "user:pass@host/db" (which people do paste) would parse as a path,
    # so normalise it first.
    if '://' not in url:
        url = 'postgresql://' + url

    parsed = urlparse(url)

    if parsed.scheme.lower() not in _POSTGRES_SCHEMES:
        return None

    host = parsed.hostname
    if not host:
        return None

    # urlparse splits the userinfo at the LAST '@', so a password that itself
    # contains '@' survives intact. It does NOT percent-decode, though, so we
    # do that here: providers hand out passwords whose '/', ':' and '@'
    # arrive as %2F, %3A and %40, and libpq needs the literal characters.
    # (A genuine '%' in a password arrives as %25 and decodes correctly too.)
    user = unquote(parsed.username) if parsed.username else ''
    password = unquote(parsed.password) if parsed.password else ''

    # The database name is the path minus its leading '/'.
    name = (parsed.path or '').lstrip('/') or ''

    options = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in _FORWARDED_PARAMS:
            options[key] = value

    # Neon (and every other managed provider) requires an encrypted
    # connection. If the URL didn't say, insist on TLS anyway.
    options.setdefault('sslmode', 'require')

    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': name,
        'USER': user,
        'PASSWORD': password,
        'HOST': host,
        'PORT': str(parsed.port or _DEFAULT_POSTGRES_PORT),
        'OPTIONS': options,
    }


def is_pooled_host(host):
    """
    True when the hostname points at a connection POOLER rather than the
    database itself.

    Neon's pooled endpoint contains `-pooler`
    (ep-amber-meadow-123456-pooler.ap-southeast-1.aws.neon.tech);
    other providers use `pooler.`, `-pooler.` or the pgbouncer port 6432.

    Why it matters: a pooler runs PgBouncer in *transaction* mode, which
    cannot carry server-side cursors or session state between queries.
    Django must be told (see `settings.py` -> DISABLE_SERVER_SIDE_CURSORS).
    """
    if not host:
        return False
    host = host.lower()
    return 'pooler' in host or 'pgbouncer' in host
