from typing import Generator, NamedTuple
import asyncio
from threading import Thread
from datetime import date, timedelta

from django.db.models import Max, Count
import bs4
import aiohttp

from .models import *
from .apps import CurrencyConfig

__all__ = ('Updater', )

URL_PERIOD: str = (
    'https://www.finmarket.ru/currency/rates/'
    '?cur={id}&bd={fromDay}&bm={fromMonth}&by={fromYear}'
    '&ed={toDay}&em={toMonth}&ey={toYear}'
)
URL_DAY: str = (
    'https://www.finmarket.ru/currency/rates/?bd={day}&bm={month}&by={year}'
)

class Updater:
    __slots__ = ('loop', 'session', 'update_thread')

    class DayInfo(NamedTuple):
        code: str
        name: str
        amount: int
        course: float
        change: float

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.session: aiohttp.ClientSession | None = None
        self.update_thread: Thread | None = None

    def update(self) -> None:
        assert self.loop is None
        assert self.update_thread is None
        self.update_thread = Thread(target=self._update, daemon=True, name='Database updater')
        self.update_thread.start()

    def _update(self) -> None:
        assert self.loop is None
        assert isinstance(self.update_thread, Thread)
        assert self.session is None
        self.loop = asyncio.new_event_loop()
        self.session = aiohttp.ClientSession(loop=self.loop)

        current_date: date | None = CurrencyCourse.objects.aggregate(Max('date'))['date__max']
        if current_date is None:
            current_date = date(day=1, month=1, year=1992)

        if not CurrencyInfo.objects.count():
            self.loop.run_until_complete(self._init_codes())

        # for currency in CurrencyInfo.objects.iterator():


        # if (date.today() -current_date).days > 40: # TODO: > {Amount of codes}
        #     coroutine = self._update_by_periods(current_date)
        # else:
        #     coroutine = self._update_by_days(current_date)

        try:
            # self.loop.run_until_complete(coroutine)
            pass
        finally:
            self.loop.run_until_complete(self.session.close())
            self.session = None
            self.loop.close()
            self.loop = None

    async def _get_page(self, url: str, allow_redirects: bool = True) -> str:
        assert isinstance(self.session, aiohttp.ClientSession)
        assert '{' not in url, "Got unformatted URL"
        async with self.session.get(url, allow_redirects=allow_redirects) as response:
            return await response.text(encoding='windows-1251')

    def _get_day_info(self, soup: bs4.BeautifulSoup) -> Generator[DayInfo, None, None]:
        tbody = soup.find(name='tbody')
        assert isinstance(tbody, bs4.Tag)
        for i in tbody:
            code, name, amount, course, change = (column.text for column in i)
            amount = int(amount.replace('\xa0', ''))
            course = float(course.replace(',', '.')) / amount
            change = float(change.replace(',', '.')) / amount
            yield self.DayInfo(
                code=code,
                name=name,
                amount=amount,
                course=course,
                change=change
            )

    def _get_period_info(self, soup: bs4.BeautifulSoup) -> Generator[PeriodInfo, None, None]:
        tbody = soup.find(name='tbody')
        for tr in in tbody:
            print()

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


    async def _update_by_periods(self, current_date: date) -> None:
        assert isinstance(current_date, date)
        today = date.today()


    async def _update_by_days(self, current_date: date) -> None:
        pass
