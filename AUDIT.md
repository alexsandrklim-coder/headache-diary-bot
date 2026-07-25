## Аудит бота @sheybolitbot — v16

### КРИТИЧЕСКИЕ БАГИ:

1. **save_user_data() ИГНОРИРУЕТ Gist** (строки 155-177) — пишет ТОЛЬКО в локальный файл. Когда пользователь меняет время, пишет заметку, или делает /setpain — данные теряются на Render. Нужно: делегировать в save_data().

2. **_safe_reply ловит только TimedOut/NetworkError** (строки 195-206) — если Telegram вернёт另一种 ошибку (403 Forbidden, 400 Bad Request) — бот крашнется. Нужно: ловить все Exception.

3. **reschedule_user_job() требует context.job_queue** (строка 234) — в webhook mode с custom aiohttp job_queue может не работать. В set_save (строка 736) вызывается reschedule — при webhook крашнет.

### БАГИ СРЕДНЕЙ КРИТИЧНОСТИ:

4. **`prev_year` и `next_year` считаются но НЕ ИСПОЛЬЗУЮТСЯ** (строки 259, 261, 335, 337) — мёртвый код.

5. **Дублирование `import tempfile`** (строки 7 и 9) — `import tempfile` и `import tempfile as _tf`.

6. **`import hashlib, hmac`** (строки 10-11) — не используются.

7. **`cmd_start` создаёт user дважды** — вызывает `get_user_time()` → `get_user_data()` (создаёт+сохраняет), потом снова проверяет и создаёт (строки 472-476).

8. **`generate_report` tempfile не удаляется при ошибке** (строки 462-465) — NamedTemporaryFile created but if doc.save() fails, file leaks.

9. **`trigger_handler` НЕ фильтрует uid** — перебирает ВСЕ ключи data, включая тех кто не является user_id (строки 925-941).

10. **Календарь: `prev_year`/`next_year` пересчитаны неправильно** — prev_month=12 → prev_year=year (должен быть year-1), строка 259.

### АРХИТЕКТУРНЫЕ ПРОБЛЕМЫ:

11. **deploy_vps.sh, start_bot.bat, railway.toml** — мёртвые файлы, не используются.
12. **HARD_DATA хардкожен в коде** — нельзя обновить без деплоя.
13. **Бот token в webhook URL** — виден в логах.
14. **Нет rate limiting** на webhook endpoint.
15. **`urllib.request` импортируется внутри функций** — должен быть на верхнем уровне.

### ВЫПОЛНЕННЫЕ ПРОВЕРКИ:

- Gist read/write: OK
- Health endpoint: OK  
- Trigger endpoint: OK (Sent to 1 user)
- Webhook handler: OK (200 responses)
- Cold start: ~50 секунд (Render free tier)
