from django.shortcuts import render

from . import forms


def index(request):
    if request.method == "POST":
        form = forms.DatesForm(request.POST)
        post = True
    else:
        form = forms.DatesForm()
        post = False
    print(f"Valid: {form.is_valid()}, {form.errors}")
    return render(request, 'currency/index.html', context={'form': form, 'post': post})

