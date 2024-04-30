# Установка
## Требования
Python3.12
## Шаги
см. [install](install)
# Информация
## Общая информация
- Весь код, комментарии, описание функций/методов/классов на английском. Только readme.md на русском.
- При первом запуске сервера, или любой другой команды после migrate параллельно с потоком django будет запускаться поток updater, который обновляет данные на лету
- Статус обновления можно посмотреть в файле *[логов](currencys/logging/log.log)*
- Валюта, которая не имеет ссылки
- С задержкой в 1 секунду между запросами к [finmarket](https://www.finmarket.ru) (анти-спам) и скоростью интернета 100мбит/с обновление базы данных длилось 3 часа, 39 минут и 24 секунд. В таблицу всего вставлено 1_008_642 строчек данных на каждый день и для каждой валюты.
## Баги
- При выходе из Django досрочно (во время работы updater), валюты, которые не успели обновиться, обновляться не будут
