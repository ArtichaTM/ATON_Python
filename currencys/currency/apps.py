from django.apps import AppConfig

__all__ = ('CurrencyConfig', )


class CurrencyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "currency"
    updater = None

    def ready(self) -> None:
        super().ready()
        from .parser import Updater
        self.__class__.updater = Updater()
        self.__class__.updater.update()
