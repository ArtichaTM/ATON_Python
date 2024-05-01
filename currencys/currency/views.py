from datetime import date

from django.shortcuts import render
from django.http.response import JsonResponse


from . import forms
from .models import CurrencyInfo, CurrencyRate
from .apps import CurrencyConfig


def info_fetch(request):
    form = forms.DatesForm(request.POST)
    if not form.is_valid():
        return index(request=request, status=400)
    v = form.cleaned_data
    from_date = date(
        day=v['fromDay'],
        month=v['fromMonth'],
        year=v['fromYear']
    )
    to_date = date(
        day=v['toDay'],
        month=v['toMonth'],
        year=v['toYear']
    )
    output: list[dict[str, list[date | float] | str]] = []
    for _number in v['currencys']:
        number: int = int(_number)
        currency_info = CurrencyInfo.objects.get(number=number)
        currency_dict = dict()
        output.append(currency_dict)
        currency_dict['x'] = x = []
        currency_dict['y'] = y = []
        iterator = CurrencyRate\
            .objects\
            .filter(
                date__range=[from_date, to_date],
                currencyInfo=currency_info
            )\
            .values('date', 'value')\
            .iterator()
        for rate in iterator:
            assert isinstance(rate['date'], date)
            x.append(rate['date'].ctime())
            y.append(rate['value'])
        currency_dict['name'] = currency_info.name
        currency_dict['type'] = 'line'
    return JsonResponse(data={'info': output})


def index(request, status: int | None = None):
    if request.method == "POST":
        form = forms.DatesForm(request.POST)
        post = True
    else:
        form = forms.DatesForm()
        post = False
    currencys = CurrencyInfo.objects.values('number', 'name').order_by('name').all()
    assert CurrencyConfig.updater is not None
    return render(request, 'currency/index.html', context={
        'form': form,
        'post': post,
        'currencys': currencys,
        'updating': CurrencyConfig.updater.updating
    }, status=status)

