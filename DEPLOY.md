# Развёртывание PrediCup на сервере (Ubuntu 24.04 LTS)

Инструкция для запуска бота на чистом сервере через Docker. Все команды
выполняются в терминале сервера (по SSH) под пользователем с правами sudo.

## 0. Что понадобится

Значения, которые нужно подставить в настройки (нет в репозитории):
- `BOT_TOKEN` — токен Telegram-бота (от @BotFather);
- `FOOTBALL_API_KEY` — ключ football-data.org;
- список `tg_id` администраторов;
- `id` чата (группы), где работает бот (вид `-100…`).

## 1. Установить Docker и git

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
# Официальный репозиторий Docker
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Docker стартует автоматически при загрузке сервера
sudo systemctl enable --now docker

# (необязательно) запускать docker без sudo:
sudo usermod -aG docker $USER   # затем выйти и зайти по SSH заново
```

Проверка: `docker --version` и `docker compose version` должны что-то вывести.

## 2. Получить код

```bash
git clone https://github.com/tieschth/PrediCup.git
cd PrediCup
```

## 3. Создать файл секретов `.env`

Файла `.env` в репозитории нет (секреты не хранятся в git) — создаём вручную:

```bash
cp .env.example .env
nano .env
```
Заполнить:
```
BOT_TOKEN=сюда_токен_бота
FOOTBALL_API_KEY=сюда_ключ_football_data_org
ENV=prod
```
> `ENV=prod` обязательно для боевого режима — отключает тестовые команды
> (`/devmatch`, `/devopen`, `/devresult`, `/devreset`, `/id`).
> Пути `CONFIG_PATH`/`DB_PATH` менять не нужно — внутри контейнера они уже заданы.

Сохранить в nano: `Ctrl+O`, `Enter`, затем `Ctrl+X`.

## 4. Создать конфиг `config/config.yaml`

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```
Указать как минимум:
```yaml
bot:
  display_timezone: "Europe/Moscow"

provider:
  name: football_data_org
  competition: "WC"

scheduler:
  open_at_local: "10:05"     # время МСК ежедневного открытия голосований
  open_window_hours: 24      # на матчи ближайших 24 часов

roles:
  admins: [123456789]              # tg_id админов
  allowed_chats: [-1001234567890]  # id рабочего чата (группы)

scoring:
  correct_outcome: 1
```

## 5. Запустить бота в фоне

```bash
docker compose up -d --build
```
- `-d` — фоновый режим (бот работает после выхода из SSH);
- `--build` — собрать образ (нужно при первом запуске и после `git pull`).

Проверить логи:
```bash
docker compose logs -f
```
Ожидаемо: `Стартовая синхронизация: 104 матчей` и `Бот запущен. Провайдер:
football_data_org`. Выйти из логов — `Ctrl+C` (контейнер продолжит работать).

## 6. Управление

```bash
docker compose ps          # статус
docker compose logs -f     # логи в реальном времени
docker compose restart     # перезапуск
docker compose down        # остановить (данные сохранятся)
docker compose up -d        # запустить снова
```

## 7. Данные, бэкапы и обновление

- База SQLite лежит на сервере в `./data/predicup.sqlite3` (том примонтирован в
  контейнер) — прогнозы и очки **переживают перезапуск и пересборку**.
- **Автобэкапы:** бот сам делает копию БД каждый день в `scheduler.backup_at_local`
  (по умолчанию 04:30 МСК) в папку `./data/backups/`, хранит последние
  `scheduler.backup_keep` штук (по умолчанию 14). Настраивается в `config.yaml`.
- **Скопировать бэкапы с сервера** на свой ПК (запускать локально):
  ```bash
  scp -r user@SERVER_IP:~/PrediCup/data/backups ./predicup-backups
  ```
- **Восстановление из бэкапа:**
  ```bash
  docker compose down
  cp data/backups/predicup-2026XXXX-XXXXXX.sqlite3 data/predicup.sqlite3
  docker compose up -d
  ```
- Обновление кода:
  ```bash
  git pull
  docker compose up -d --build
  ```
  `.env`, `config/config.yaml` и `./data` при этом не затрагиваются.

## 7.1 Логи

- Смотреть: `docker compose logs -f` (живой поток) или
  `docker compose logs --since 1h` (за последний час).
- Логи пишутся в JSON-файлы Docker с **ротацией** (макс. 5 файлов по 10 МБ —
  задано в docker-compose.yml), диск не забьётся.
- В логах видно ключевые события: старт, синхронизацию расписания, открытие
  голосований по матчам, завершение матчей с исходом и числом угадавших, бэкапы,
  а также ошибки (с трассировкой) — этого достаточно, чтобы понять, что случилось.

## 8. Автозапуск и устойчивость

- Контейнер запускается с политикой `restart: unless-stopped` — после
  перезагрузки сервера или падения процесса он поднимется сам (Docker уже
  включён в автозагрузку шагом 1).
- ⚠️ **Один экземпляр бота на токен.** Не запускай вторую копию с тем же
  `BOT_TOKEN` (например, локально на ПК и на сервере одновременно) — Telegram
  отдаёт обновления только одному поллеру, будет конфликт. На время боевой работы
  локальная копия должна быть выключена.

## 9. Права бота в чате (делает владелец бота)

Чтобы всё работало корректно, бота в группе нужно:
- добавить в группу и **сделать администратором** (тогда он видит команды и может
  постить);
- дать право **«Удаление сообщений»** — чтобы команды `/matches` и `/leaderboard`
  убирались из чата и не засоряли ленту.

## 10. Минимальные ресурсы

Бот лёгкий (Python + SQLite, редкие HTTP-запросы). Конфигурации **1 ядро / 1 ГБ
RAM / 20 ГБ диска** более чем достаточно с большим запасом.
