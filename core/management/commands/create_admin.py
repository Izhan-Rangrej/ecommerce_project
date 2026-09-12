"""
Management command:  python manage.py create_admin

Creates the admin (superuser) account from environment variables, and
does NOTHING when the account already exists (idempotent — safe to run
on every deploy):

    DJANGO_SUPERUSER_USERNAME=admin
    DJANGO_SUPERUSER_EMAIL=admin@example.com
    DJANGO_SUPERUSER_PASSWORD=SomeStrongPassword

Hosting platforms store these as environment variables and the build
command runs this step before seed_data. Locally it simply skips when
the variables are not set, so it can never interfere with development.
"""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create the admin superuser from DJANGO_SUPERUSER_* env vars (idempotent).'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    'create_admin: DJANGO_SUPERUSER_USERNAME / _PASSWORD '
                    'not set in the environment — skipped.'
                )
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                f'Admin "{username}" already exists — nothing to do.'
            )
            return

        User.objects.create_superuser(username, email, password)
        self.stdout.write(
            self.style.SUCCESS(f'Admin superuser "{username}" created.')
        )
