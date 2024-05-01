from django.urls import path, include

from .apps import CurrencyConfig
from . import views

app_name = CurrencyConfig.name

urlpatterns = [
    path('', views.index, name='index'),
    path('fetch', views.info_fetch, name='fetch'),
]
