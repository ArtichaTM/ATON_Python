from django.db.models import (
    Model,
    IntegerField,
    CharField,
    DateField,
    ForeignKey,
    FloatField,
    CASCADE
)

__all__ = ('CurrencyInfo', 'CurrencyRate')

class CurrencyInfo(Model):
    number = IntegerField(unique=True, primary_key=True)
    number_url = IntegerField(unique=True, null=False)
    code = CharField(max_length=3, null=False)
    name = CharField(max_length=80, null=False)
    country = CharField(max_length=80, null=False)


class CurrencyRate(Model):
    currencyInfo = ForeignKey(CurrencyInfo, on_delete=CASCADE, null=False)
    date = DateField(null=False)
    value = FloatField(null=False)

    class Meta:
        unique_together = ['currencyInfo', 'date']
