from datetime import datetime

from django import forms

class DatesForm(forms.Form):
    __slots__ = ('dt_from', 'dt_to')

    fromDay = forms.IntegerField(min_value=1, max_value=31)
    fromMonth = forms.IntegerField(min_value=1, max_value=12)
    fromYear = forms.IntegerField(min_value=2003, max_value=datetime.now().year)
    toDay = forms.IntegerField(min_value=1, max_value=31)
    toMonth = forms.IntegerField(min_value=1, max_value=12)
    toYear = forms.IntegerField(min_value=2003, max_value=datetime.now().year)

    def clean(self) -> None:
        data = self.cleaned_data
        self.dt_from = datetime(
            day=data['fromDay'],
            month=data['fromMonth'],
            year=data['fromYear']
        )
        self.dt_to = datetime(
            day=data['toDay'],
            month=data['toMonth'],
            year=data['toYear']
        )
        if self.dt_from > self.dt_to:
            raise forms.ValidationError("From date can't be bigger than to date")
