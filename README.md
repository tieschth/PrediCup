# PrediCup — Telegram-бот предсказаний на ЧМ-2026

Бот для группового чата: перед матчами публикует голосовалку с флагами, **скрытно**
записывает прогноз каждого участника (другие чужой выбор не видят), после матча
подтягивает результат, начисляет очки и ведёт таблицу лидеров.

Первая версия: групповой этап, исход **П1 / Ничья / П2**.

## Возможности

- 🗳 Голосование на inline-кнопках с флагами — выбор виден только боту (анонимно
  для остальных), запись приватная через `callback_query`.
- 🔁 Переголосование до начала матча, автозакрытие приёма ровно на старте.
- 🏁 Авто-резолв результата из внешнего источника и начисление очков.
- 🏆 Таблица лидеров (`/leaderboard`) — пока только для админов (роли в конфиге).
- 📬 `/matches` — список открытых голосований в личку со ссылками на сообщения.
- ⚠️ Уведомление участнику об успехе/ошибке записи голоса; при ошибке — алерт
  админам в ЛС с причиной.
- 🧪 Дев-режим с командами `/devmatch` и `/devresult` для ручного прогона сценария.

## Стек

Python 3.12 · [aiogram 3.x](https://docs.aiogram.dev) · SQLAlchemy 2 (async) +
SQLite · APScheduler · pydantic-settings · pytest.

## Быстрый старт (локально)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

copy .env.example .env                       # впиши BOT_TOKEN (и FOOTBALL_API_KEY)
copy config\config.example.yaml config\config.yaml   # впиши admins и allowed_chats

.\.venv\Scripts\python.exe -m bot.main
```

Токен бота берётся у [@BotFather](https://t.me/BotFather). Чтобы бот видел
команды в группе, в BotFather отключи Privacy Mode (или дай боту права админа).

## Конфигурация

- **`.env`** — только секреты и пути: `BOT_TOKEN`, `FOOTBALL_API_KEY`,
  `ENV` (`dev`/`prod`), `CONFIG_PATH`, `DB_PATH`.
- **`config/config.yaml`** — настройки (см. `config/config.example.yaml`):
  - `scheduler.open_at_local` — время (по `display_timezone`) ежедневного открытия
    голосований; `scheduler.open_window_hours` — на матчи ближайших N часов;
  - `provider.name` — `mock` | `football_data_org` | `openfootball`;
  - `roles.admins` — `tg_id` админов; `roles.allowed_chats` — id чатов (супергруппа,
    отрицательный id вида `-100…`);
  - `scoring.correct_outcome` — очки за угаданный исход;
  - `scheduler.*` — частота фоновых задач.

> Узнать `tg_id` и id чата можно, например, через [@userinfobot] / переслав
> сообщение из группы боту вроде [@getidsbot].

## Источник данных о матчах

За абстракцией `MatchProvider` (`bot/services/football/base.py`):

- **`football_data_org`** — [football-data.org](https://www.football-data.org)
  (бесплатный тариф, ключ в `FOOTBALL_API_KEY`, турнир `provider.competition: WC`);
- **`openfootball`** — статичный публичный JSON, без ключа, но результаты с
  задержкой;
- **`mock`** — управляемый источник для тестов и дев-режима.

Сменить источник — один параметр `provider.name`, код не трогается.

## Ручной прогон сценария (dev)

При `ENV=dev` админам доступны команды (нужен `provider.name: mock`):

```
/devmatch Бразилия Аргентина 10 BRA ARG   # вброс матча, старт через 10 минут
                                          # → в чате появляется голосовалка с флагами
/devresult HOME 2:1                        # «результат прочитан» → резолв и очки
/leaderboard                               # таблица лидеров (только админ)
```

Так можно проверить весь путь: голосование → переголосование → закрытие →
начисление очков → таблица.

## Docker

```bash
cp .env.example .env                         # заполнить
cp config/config.example.yaml config/config.yaml
docker compose up -d --build
```

SQLite хранится в `./data` (том), поэтому данные переживают рестарт контейнера.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Покрывают начисление очков, контракт mock-провайдера и e2e-флоу
(матч → голоса → результат → очки → таблица).

## Структура

```
bot/
  main.py            точка входа
  config.py          .env + config.yaml
  access.py          проверки ролей
  flags.py           код сборной -> эмодзи-флаг
  scheduler.py       фоновые задачи (APScheduler)
  db/                модели, сессии, репозиторий
  services/          scoring, matches, leaderboard, notifications, presentation
    football/        провайдеры данных (base/mock/factory/football_data_org/openfootball)
  handlers/          common, admin, predictions, dev
  keyboards/         клавиатура голосования
tests/               pytest
```

## На будущее

Угадывание точного счёта и доп. время/пенальти на плей-офф (поля в моделях
заложены), расширение ролей доступа, анимации, миграция на Postgres.
