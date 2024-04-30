from django.shortcuts import render

from . import forms
from .models import CurrencyInfo


def index(request):
    if request.method == "POST":
        form = forms.DatesForm(request.POST)
        print(request.POST)
        post = True
    else:
        form = forms.DatesForm()
        post = False
    currencys = CurrencyInfo.objects.values('number', 'name').all()
    print(f"Valid: {form.is_valid()}, {form.errors}")
    return render(request, 'currency/index.html', context={
        'form': form,
        'post': post,
        'currencys': currencys
    })

