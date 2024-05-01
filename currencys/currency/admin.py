from django.contrib import admin

from . import models


@admin.register(models.CurrencyInfo)
class CurrencyInfoAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CurrencyRate)
class CurrencyRateAdmin(admin.ModelAdmin):
    date_hierarchy = 'date'
