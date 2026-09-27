# downloader-bot

Telegram-бот: присылаете ссылку на видео (YouTube, TikTok, Instagram, VK, X/Twitter, публичные посты
Telegram) — бот скачивает его через yt-dlp и отправляет в чат. Архитектура — [architecture.md](architecture.md).

## Запуск

Нужны Python 3.11+, `ffmpeg` в PATH (для склейки видео и аудио) и `deno` в PATH —
yt-dlp решает им JS-челленджи YouTube; без него YouTube падает с ошибками вроде
«The page needs to be reloaded».

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN
.venv/bin/python -m downloader_bot
```

Все настройки — переменные окружения (или `.env`), список и значения по умолчанию в `.env.example`.

## Деплой на VPS

```bash
sudo useradd --system --home /opt/downloader-bot downloader-bot
# код в /opt/downloader-bot, venv в /opt/downloader-bot/.venv, .env рядом
# deno — в системный PATH, иначе systemd-сервис его не увидит
curl -fsSL https://deno.land/install.sh | sudo DENO_INSTALL=/usr/local sh
sudo cp deploy/downloader-bot.service /etc/systemd/system/
sudo systemctl enable --now downloader-bot
journalctl -u downloader-bot -f
```

yt-dlp нужно регулярно обновлять — площадки часто ломают экстракторы (`[default]` обновляет
и yt-dlp-ejs, его версия должна соответствовать yt-dlp):

```bash
.venv/bin/pip install -U "yt-dlp[default]" && sudo systemctl restart downloader-bot
```

## Тесты

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
