from typing import Generator, NamedTuple
from logging import getLogger
from threading import Thread
from datetime import date
from dateutil.relativedelta import relativedelta
from time import perf_counter, sleep

from django.db.models import Max, Min
import requests
import bs4

from .forms import DatesForm
from .models import *
from .apps import CurrencyConfig

__all__ = ('Updater', )

URL_PERIOD: str = (
    'https://www.finmarket.ru/currency/rates/?'
    'id=10148&pv=1&cur={number}&bd={fromDay}&bm={fromMonth}&by={fromYear}'
    '&ed={toDay}&em={toMonth}&ey={toYear}'
)
URL_DAY: str = (
    'https://www.finmarket.ru/currency/rates/?id=10148&bd={day}&bm={month}&by={year}'
)

class UniqueException(Exception):
    __slots__ = ('info',)
    def __init__(self, *args: object, info: dict) -> None:
        super().__init__(*args)
        assert isinstance(info, dict)
        self.info = info

class Updater:
    MINIMUM_DATE = date(year=1992, month=1, day=1)
    __slots__ = (
        'session', 'update_thread', 'delay',
        'last_request_time', 'logger', 'force_day_update'
    )

    class DayInfo(NamedTuple):
        code: str
        name: str
        amount: int
        rate: float
        change: float
    class PeriodInfo(NamedTuple):
        date: date
        amount: int
        rate: float
        change: float

    def __init__(self, sleep_delay: float = 1., force_day_update: bool = False) -> None:
        assert isinstance(sleep_delay, float)
        assert sleep_delay >= 0
        self.session = None
        self.update_thread: Thread | None = None
        self.delay = sleep_delay
        self.last_request_time: float = perf_counter()
        self.force_day_update = force_day_update
        self.logger = getLogger('db_updater')

    @property
    def updating(self) -> bool:
        return self.session is not None

    def update(self) -> None:
        assert self.update_thread is None
        self.update_thread = Thread(
            target=self._update,
            name='Database updater',
            daemon=True
        )
        self.update_thread.start()

    def _anti_spam(self) -> None:
        delay = self.delay - (perf_counter() - self.last_request_time)
        if delay < 0:
            self.last_request_time = perf_counter()
            return
        sleep(delay)
        self.last_request_time = perf_counter()

    def _update_except(self) -> None:
        from django.db import connection
        table_name = f"{CurrencyConfig.name}_{CurrencyInfo.__qualname__.lower()}"
        if table_name not in connection.introspection.table_names():
            self.logger.warning(" No tables found. Exiting")
            return

        self.logger.info("Started updating")

        if not CurrencyInfo.objects.count():
            self.logger.warning("Updating codes. This message should happen once")
            self._init_codes()
            self.logger.info("Finished updating codes")

        values = CurrencyInfo.objects.values_list('number', 'name').all()
        DatesForm.declared_fields['currencys'].choices = tuple(values)

        self._recheck_currencys()

    def _update(self) -> None:
        assert isinstance(self.update_thread, Thread)
        assert self.session is None
        self.session = requests.Session()

        try:
            self._update_except()
        finally:
            assert self.session is not None
            self.session.close()
            self.session = None

    def _get_page(self, url: str, allow_redirects: bool = False) -> bs4.BeautifulSoup:
        assert self.session is not None
        assert '{' not in url, "Got unformatted URL"
        self._anti_spam()
        with self.session.get(url, allow_redirects=allow_redirects) as response:
            response.encoding = 'windows-1251'
            page = response.text
            soup = bs4.BeautifulSoup(page, features='html.parser')
            return soup

    def _recheck_currencys(self) -> None:
        assert hasattr(CurrencyRate, 'currencyInfo')
        assert hasattr(CurrencyRate, 'date')

        all_ids: set[int] = {i['number'] for i in CurrencyInfo.objects.values('number')}
        _info_ids = CurrencyRate.objects\
            .values('currencyInfo')\
            .annotate(date_max=Max('date'))
        all_max_date: date | None = next(iter(CurrencyRate.objects
            .aggregate(Max('date'))
            .values()
        ))
        if all_max_date is None:
            all_max_date = self.MINIMUM_DATE
        info_ids: dict[int, date] = {
            i['currencyInfo']: i['date_max'] \
            for i in _info_ids
        }

        for id in all_ids:
            maximum_date = info_ids.get(id, self.MINIMUM_DATE)
            assert isinstance(maximum_date, date)
            id_difference = (all_max_date - maximum_date).days
            self.logger.info(
                f"Difference for {id} between max "
                f"and today is {id_difference} days "
                f"({all_max_date} - {maximum_date})"
                )
            if id_difference > 1:
                self.logger.warning(
                    f"Currency with id={id} last date {maximum_date} differs "
                    f"from all CurrencyRates maximum date {all_max_date}"
                    f" by {id_difference} days. "
                    "Previous update interrupted? "
                    "Server was shutdown for too long?"
                )
                currency_info = CurrencyInfo.objects.get(number=id)
                dates = self.date_periods(
                    from_date=maximum_date + relativedelta(days=1),
                    to_date=all_max_date
                )
                self._update_currency(
                    currency=currency_info,
                    dates=dates
                )
                self.logger.info(
                    f"Currency {currency_info.name} ({id}) updated "
                    f"to max among all currency infos ({all_max_date})"
                )
            else:
                self.logger.info(
                    f"Currency with id={id} last date {maximum_date} differs "
                    f"from all CurrencyRates maximum date {all_max_date}"
                    f" by {id_difference} days. No update required"
                )

        target_date = date.today() - relativedelta(days=1)
        _minimum_date: list[date] = [i[0] for i in CurrencyRate.objects
            .values('currencyInfo')
            .annotate(date_max=Max('date'))
            .values_list('date_max')
        ]
        if _minimum_date:
            minimum_date: date = min(_minimum_date)
        else:
            minimum_date: date = all_max_date
        difference = (target_date - minimum_date).days
        self.logger.info(f'Difference between maximum date and today are {difference} days')
        """
        If difference between dates bigger than length of all ids better use
        update by a periods. Else better use update by days
        Reason: Update by days make requests for each day, while update
            by periods make requests for each currency. So actually we compare
            amount of requests that needs to be made
        """
        if difference > len(all_ids):
            # Update by periods advantageous
            self.logger.info("Decided to update by periods")
            self._update_by_periods(from_date=minimum_date, ids=all_ids)
        else:
            # Update by days advantageous
            self.logger.info("Decided to update by days")
            self._update_by_days(date_starting=minimum_date, date_target=target_date)
        self.logger.info("Updating finished")

    def _get_day_info(self, soup: bs4.BeautifulSoup) -> Generator[DayInfo, None, None]:
        tbody = soup.find(name='tbody')
        assert isinstance(tbody, bs4.Tag)
        for i in tbody:
            code, name, amount, rate, change = (column.text for column in i)
            amount = int(amount.replace('\xa0', ''))
            rate = float(rate.replace(',', '.')) / amount
            change = float(change.replace(',', '.')) / amount
            yield self.DayInfo(
                code=code,
                name=name,
                amount=amount,
                rate=rate,
                change=change
            )

    def _get_period_info(self, soup: bs4.BeautifulSoup) -> Generator[PeriodInfo, None, None]:
        table = soup.find(name='table', attrs={'class': 'karramba'})
        assert isinstance(table, bs4.Tag)
        tbody = table.tbody
        assert isinstance(tbody, bs4.Tag)
        for tr in tbody:
            rate_str, amount, rate, change = tr
            rate_str = tuple(map(int, rate_str.text.split('.')))
            rate_date = date(day=rate_str[0], month=rate_str[1], year=rate_str[2])
            amount = int(amount.text.replace('\xa0', ''))
            rate = float(rate.text.replace(',', '.').replace('\xa0', ''))
            change = float(change.text.replace(',', '.').replace('\xa0', ''))
            yield self.PeriodInfo(
                date=rate_date,
                amount=amount,
                rate=rate,
                change=change
            )

    def _init_codes(self) -> None:
        # Getting latest day info
        day_variable = self._get_page(URL_DAY.format(
            day=1,
            month=1,
            year=2024,
        ))
        assert isinstance(day_variable, bs4.BeautifulSoup)
        day_variable = self._get_day_info(day_variable)
        available_codes: set[str] = {i.code for i in day_variable}

        # Getting all banknotes
        soup = self._get_page('https://www.finmarket.ru/currency/banknotes/')
        table = soup.find(name='table')
        assert isinstance(table, bs4.Tag)
        iterator = iter(table)
        for _ in range(4): next(iterator)  # Skipping two rows (they are header part)
        currency_infos: list[CurrencyInfo] = []
        for row in iterator:
            if row == '\n':
                continue
            assert isinstance(row, bs4.Tag)
            name, code, number, country = row.find_all(name='td')
            assert isinstance(name, bs4.Tag)
            assert isinstance(code, bs4.Tag)
            assert isinstance(number, bs4.Tag)
            assert isinstance(country, bs4.Tag)
            a_tag = name.a
            if a_tag is None:
                continue
            assert isinstance(a_tag, bs4.Tag)
            assert isinstance(a_tag['href'], str)
            number_url = int(a_tag['href'].split('=')[1])
            name, code, number, country = name.text, code.text, number.text, country.text
            assert isinstance(name, str)
            assert isinstance(code, str)
            if code not in available_codes:
                continue
            name = name.replace('\n', '').strip()
            number = int(number)
            currency_info = CurrencyInfo(
                number=number,
                number_url=number_url,
                code=code,
                name=name,
                country=country
            )
            currency_infos.append(currency_info)
        assert currency_infos, "How currency_infos can be empty?"
        CurrencyInfo.objects.bulk_create(
            currency_infos,
            ignore_conflicts=False,
            update_conflicts=False
        )

    def _update_currency(self, currency: CurrencyInfo, dates: list[date]) -> None:
        current_date = iter(dates)
        next_date = iter(dates)
        next(next_date)
        currency_rates: list[CurrencyRate] = []
        for date_from, date_to in zip(current_date, next_date):
            self.logger.debug(f"Updating {currency.number} {date_from}->{date_to}")
            date_from_sec = date_from.toordinal()
            date_to_sec = date_to.toordinal()
            date_to -= relativedelta(days=1)
            if date_from == date_to:
                continue
            assert date_to > date_from
            url = URL_PERIOD.format(
                number=currency.number_url,
                fromDay=date_from.day,
                fromMonth=date_from.month,
                fromYear=date_from.year,
                toDay=date_to.day,
                toMonth=date_to.month,
                toYear=date_to.year
            )
            soup = self._get_page(url)
            for period in self._get_period_info(soup):
                assert date_from_sec <= period.date.toordinal() <= date_to_sec, (
                    "period date received from _get_period_info() is not in range: "
                    f"{date_from} <= {period.date} <= {date_to}"
                )
                currency_rate = CurrencyRate(
                    currencyInfo=currency,
                    date=period.date,
                    value=period.rate
                )
                currency_rates.append(currency_rate)
        assert currency_rates, "How currency_rates can be empty?"
        CurrencyRate.objects.bulk_create(
            currency_rates,
            ignore_conflicts=False,
            update_conflicts=False
        )

    @staticmethod
    def date_periods(from_date: date, to_date: date | None = None) -> list[date]:
        """ Generates dates from_date to to_date with maximum interval up to 2 years (364 days)
        :param from_date: Starting date (inclusive)
        :param to_date: Ending date (inclusive)
        :return: List of dates from_date to to_date with
            maximum interval up to 364 days
            and
            both dates inclusive
        """
        assert isinstance(from_date, date)
        assert to_date is None or isinstance(to_date, date)
        today = date.today()-relativedelta(days=1) if to_date is None else to_date
        difference = (today - from_date).days
        if difference < 0:
            raise RuntimeError("Dates are misplaced")
        assert (today - from_date).days >= 1, (
            f"Difference between dates {today} and {from_date} "
            f"can't be below 1 day (difference={(today - from_date).days})"
        )
        current_date = from_date
        next_date = current_date + relativedelta(years=2)
        date_ranges: list[date] = []
        while next_date < today:
            date_ranges.append(current_date)
            current_date += relativedelta(years=2) # Leap year calculation included
            next_date += relativedelta(years=2)
        date_ranges.append(today)

        if len(date_ranges) == 1:
            date_ranges.insert(0, from_date)

        return date_ranges

    def _update_by_periods(
            self,
            from_date: date,
            ids: set[int]
        ) -> None:
        assert isinstance(from_date, date)
        assert isinstance(ids, set)
        self.logger.info("DB-Updater: Updating by periods")

        date_ranges = self.date_periods(from_date)
        self.logger.info(f"Updating from {date_ranges[0]} to {date_ranges[-1]}")
        for id in ids:
            assert isinstance(id, int)
            self._update_currency(
                currency=CurrencyInfo.objects.get(pk=id),
                dates=date_ranges
            )

    def _update_by_days(self, date_starting: date, date_target: date) -> None:
        assert isinstance(date_starting, date)
        while date_starting != date_target:
            self.logger.debug(f"Updating day {date_starting}")
            url = URL_DAY.format(
                day=date_starting.day,
                month=date_starting.month,
                year=date_starting.year,
            )
            soup = self._get_page(url)
            currency_rates: list[CurrencyRate] = []
            for currency in self._get_day_info(soup):
                try:
                    currency_info = CurrencyInfo.objects.get(code=currency.code)
                except CurrencyInfo.DoesNotExist:
                    self.logger.info(
                        f"Currency {currency.name} doesn't exist in DB, "
                        "but usually it's okay"
                    )
                    continue
                currency_rate = CurrencyRate(
                    currencyInfo=currency_info,
                    date=date_starting,
                    value=currency.rate/currency.amount
                )
                currency_rates.append(currency_rate)
            CurrencyRate.objects.bulk_create(
                currency_rates,
                ignore_conflicts=True,
                update_conflicts=False
            )
            currency_rates.clear()
            date_starting += relativedelta(days=1)
