# Procfile — the process list a Heroku-style platform reads to find out how
# to start the app. Render uses the `startCommand` in render.yaml instead;
# this file is kept so the same repository also deploys unchanged to
# Railway, Fly.io, Heroku-style hosts, or a plain `honcho start` locally.
#
#   $PORT              injected by the platform (Render: 10000)
#   ${WEB_CONCURRENCY:-2}   worker count, overridable per environment
#
# Do NOT hardcode a port here — the platform assigns one.
web: gunicorn ecommerce_project.wsgi:application --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-2} --timeout 120 --access-logfile - --error-logfile -
