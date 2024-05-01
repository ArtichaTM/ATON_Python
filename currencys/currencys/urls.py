from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(
        pattern_name='currency:index',
        permanent=False)
    ),
    path("admin/", admin.site.urls),
    path('currency/', include('currency.urls'))
]
