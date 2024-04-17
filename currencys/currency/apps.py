from threading import Thread

from django.apps import AppConfig

__all__ = ('CurrencyConfig', )


class CurrencyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "currency"

    def ready(self) -> None:
        super().ready()
        from .parser import Updater
        updater = Updater()
        updater.update()
