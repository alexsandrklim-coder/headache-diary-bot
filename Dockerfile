FROM python:3.12-slim

WORKDIR /app

LABEL build=2026-06-25-v6-report

RUN pip install --no-cache-dir "python-telegram-bot[job-queue]" python-docx

COPY bot.py .

CMD ["python", "bot.py"]

