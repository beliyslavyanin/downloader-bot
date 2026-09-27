FROM python:3.12-slim

# ffmpeg — склейка отдельных видео- и аудиопотоков;
# deno — JS-рантайм, которым yt-dlp решает челленджи YouTube.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TEMP_DIR=/tmp/downloader-bot

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY downloader_bot ./downloader_bot

RUN useradd --system --create-home --uid 10001 bot
USER bot

CMD ["python", "-m", "downloader_bot"]
