FROM python:3.12-slim

WORKDIR /app

LABEL build=2026-06-24-v4-fix

RUN pip install --no-cache-dir "python-telegram-bot[job-queue]"

COPY bot.py .

CMD ["python", "bot.py"]

