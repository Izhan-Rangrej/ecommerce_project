from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # PHASE 18: register the cache-invalidation signals
        # (importing the module fires the @receiver decorators).
        import core.signals  # noqa: F401
