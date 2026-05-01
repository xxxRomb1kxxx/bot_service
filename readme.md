# bot_service — Telegram-бот симулятора врача

Отдельный сервис Telegram-бота для [simulator_for_doctors_FASTAPI](https://github.com/your-org/simulator_for_doctors_FASTAPI).

Бот общается с пользователями через Telegram и проксирует запросы к FastAPI-сервису агента через HTTP.

## Архитектура

```
Telegram ↔ bot_service (aiogram) ↔ HTTP ↔ simulator_for_doctors_FASTAPI (FastAPI)
```

Бот **не содержит** бизнес-логики: диалоговый движок, LLM, база данных — всё на стороне API-сервиса.

## Структура проекта

```
bot_service/
├── telegram/
│   ├── bot.py              # Точка входа, запуск polling
│   ├── api_client.py       # HTTP-клиент к FastAPI-бэкенду
│   ├── handlers/
│   │   ├── menu.py         # /start, /help, главное меню
│   │   ├── dialog.py       # Диалог с пациентом, /finish, /diagnosis
│   │   ├── training.py     # Выбор болезни, контрольный кейс
│   │   └── admin.py        # Управление вайтлистом (/wl_*)
│   └── keyboards/
│       └── inline.py       # Inline и Reply клавиатуры
├── dialog_engine/
│   └── dialog_states.py    # FSM-состояния aiogram
├── config/
│   └── __init__.py         # Настройки через pydantic-settings
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Быстрый старт

### 1. Переменные окружения

```bash
cp .env.example .env
# Заполните BOT_TOKEN и BACKEND_URL
```

| Переменная               | Описание                                       | По умолчанию            |
|--------------------------|------------------------------------------------|-------------------------|
| `BOT_TOKEN`              | Токен Telegram-бота (**обязательно**)          | —                       |
| `BACKEND_URL`            | URL FastAPI-бэкенда                            | `http://localhost:8000` |
| `ADMIN_IDS`              | Telegram ID администраторов (через запятую)    | (пусто)                 |
| `LOG_LEVEL`              | Уровень логирования                            | `INFO`                  |
| `LOGIN_SHARED_SECRET`    | Shared secret для `/auth/login`                | (пусто)                 |
| `TOKEN_LIFETIME_MINUTES` | Сколько минут кэшировать `access_token`        | `50`                    |

### 2. Docker Compose

```bash
docker compose up -d
```

В `docker-compose.yml` настройте `BACKEND_URL` на адрес запущенного API-сервиса.

### 3. Локальный запуск

```bash
pip install -r requirements.txt
python -m telegram.bot
```

## Команды бота

| Команда     | Описание                        |
|-------------|---------------------------------|
| `/start`    | Главное меню                    |
| `/help`     | Инструкция                      |
| `/finish`   | Завершить диалог                |
| `/diagnosis`| Перейти к постановке диагноза   |

### Команды администратора

| Команда          | Описание                            |
|------------------|-------------------------------------|
| `/admin`         | Панель администратора               |
| `/wl_list`       | Список всех пользователей           |
| `/wl_add`        | Добавить пользователя в вайтлист    |
| `/wl_remove`     | Удалить пользователя из вайтлиста   |
| `/wl_check <id>` | Проверить статус пользователя       |
| `/health`        | Статус бэкенда                      |

Добавьте свой Telegram ID в `ADMIN_IDS` в `.env`, чтобы получить доступ к командам администратора.

## Связанные репозитории

- **[simulator_for_doctors_FASTAPI](https://github.com/your-org/simulator_for_doctors_FASTAPI)** — FastAPI-сервис агента (LLM, диалоговый движок, вайтлист)