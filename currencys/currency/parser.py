from typing import Generator, NamedTuple
import asyncio
from logging import getLogger
from threading import Thread
from datetime import date
from dateutil.relativedelta import relativedelta
from time import perf_counter

from django.db.models import Max, Count
import bs4
import aiohttp

from .models import *
from .apps import CurrencyConfig

__all__ = ('Updater', )

URL_PERIOD: str = (
    'https://www.finmarket.ru/currency/rates/?pv=1'
    '&id={id}&bd={fromDay}&bm={fromMonth}&by={fromYear}'
    '&ed={toDay}&em={toMonth}&ey={toYear}'
)
URL_DAY: str = (
    'https://www.finmarket.ru/currency/rates/?bd={day}&bm={month}&by={year}'
)

class Updater:
    __slots__ = (
        'loop', 'session', 'update_thread',
        'delay', 'last_request_time', 'logger'
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


    def __init__(self, sleep_delay: float = 1.) -> None:
        assert isinstance(sleep_delay, float)
        assert sleep_delay >= 0
        self.loop: asyncio.AbstractEventLoop | None = None
        self.session: aiohttp.ClientSession | None = None
        self.update_thread: Thread | None = None
        self.delay = sleep_delay
        self.last_request_time: float = perf_counter()
        self.logger = getLogger('db_updater')

    def update(self) -> None:
        assert self.loop is None
        assert self.update_thread is None
        self.update_thread = Thread(target=self._update, daemon=True, name='Database updater')
        self.update_thread.start()

    async def _anti_spam(self) -> None:
        delay = self.delay - (perf_counter() - self.last_request_time)
        if delay < 0:
            return
        await asyncio.sleep(delay)
        self.last_request_time = perf_counter()

    def _update(self) -> None:
        assert self.loop is None
        assert isinstance(self.update_thread, Thread)
        assert self.session is None
        self.loop = asyncio.new_event_loop()
        self.session = aiohttp.ClientSession(loop=self.loop)

        if not CurrencyInfo.objects.count():
            self.loop.run_until_complete(self._init_codes())

        current_date: date | None = CurrencyRate.objects.aggregate(Max('date'))['date__max']
        if current_date is None:
            current_date = date(day=1, month=1, year=1992)

        # If days interval too low, better use days update than update every currency by a period
        if (date.today() - current_date).days > CurrencyInfo.objects.count():
            coroutine = self._update_by_periods(current_date)
        else:
            coroutine = self._update_by_days(current_date)

        try:
            self.loop.run_until_complete(coroutine)
        finally:
            self.loop.run_until_complete(self.session.close())
            self.session = None
            self.loop.close()
            self.loop = None

    async def _get_page(self, url: str, allow_redirects: bool = False) -> str:
        assert isinstance(self.session, aiohttp.ClientSession)
        assert '{' not in url, "Got unformatted URL"
        await self._anti_spam()
        async with self.session.get(url, allow_redirects=allow_redirects) as response:
            return await response.text(encoding='windows-1251')

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

    async def _init_codes(self) -> None:
        assert isinstance(self.loop, asyncio.AbstractEventLoop)
        page: str = await self._get_page('https://www.finmarket.ru/currency/banknotes/')
        soup = bs4.BeautifulSoup(page, features='html.parser')
        table = soup.find(name='table')
        assert isinstance(table, bs4.Tag)
        iterator = iter(table)
        for _ in range(4): next(iterator)  # Skipping two rows (they are header part)
        async with asyncio.TaskGroup() as group:
            for row in iterator:
                if row == '\n':
                    continue
                assert isinstance(row, bs4.Tag)
                name, code, number, country = row.find_all(name='td')
                a_tag = name.a
                if a_tag is None:
                    continue
                number_url = int(a_tag['href'].split('=')[1])
                name, code, number, country = name.text, code.text, number.text, country.text
                name = name.replace('\n', '').strip()
                number = int(number)
                currency_info =CurrencyInfo(
                    number=number,
                    number_url=number_url,
                    code=code,
                    name=name,
                    country=country
                )
                group.create_task(currency_info.asave())

    async def _update_currency(self, currency: CurrencyInfo, dates: list[date]) -> None:
        current_date = iter(dates)
        next_date = iter(dates)
        next(next_date)
        for date_from, date_to in zip(current_date, next_date):
            url = URL_PERIOD.format(
                id=currency.number_url,
                fromDay=date_from.day,
                fromMonth=date_from.month,
                fromYear=date_from.year,
                toDay=date_to.day,
                toMonth=date_to.month,
                toYear=date_to.year
            )
            page = await self._get_page(url)
            soup = bs4.BeautifulSoup(page, features='html.parser')
            async with asyncio.TaskGroup() as group:
                for period in self._get_period_info(soup):
                    currency_rate = CurrencyRate(
                        code=currency,
                        date=period.date,
                        value=period.rate
                    )
                    group.create_task(currency_rate.asave())


    async def _update_by_periods(self, current_date: date) -> None:
        assert isinstance(current_date, date)

        next_date = current_date + relativedelta(years=2)
        today = date.today()
        date_ranges: list[date] = []
        while next_date < today:
            date_ranges.append(current_date)
            current_date += relativedelta(years=+2) # Leap year calculation included
            next_date += relativedelta(years=2)

        pre_today = today - relativedelta(days=1)
        difference = pre_today - current_date
        if difference.days > 1:
            date_ranges.append(pre_today)

        async for currency in CurrencyInfo.objects.aiterator(chunk_size=1):
            await self._update_currency(
                currency=currency,
                dates=date_ranges
            )
            break


    async def _update_by_days(self, current_date: date) -> None:
        pass
