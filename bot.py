import os
import sys
import json
import calendar
import datetime
import logging
import tempfile
import threading
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError

_log_dir = os.path.dirname(os.path.abspath(__file__))
_log_file = os.path.join(_log_dir, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(_log_file, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
    sys.exit(1)

DATA_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(DATA_DIR, "headache_data.json")
_file_lock = threading.Lock()

QUESTION_HOUR = int(os.environ.get("QUESTION_HOUR", "20"))
QUESTION_MINUTE = int(os.environ.get("QUESTION_MINUTE", "0"))

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def _atomic_save(filepath, data):
    with _file_lock:
        dir_name = os.path.dirname(filepath) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, filepath)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise


def load_data():
    with _file_lock:
        if not os.path.exists(DATA_FILE):
            return {}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}


def save_data(data):
    _atomic_save(DATA_FILE, data)


def get_user_data(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"answers": {}}
    return data[uid]


def save_user_data(user_id, user_data):
    data = load_data()
    data[str(user_id)] = user_data
    save_data(data)


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 Календарь")],
            [KeyboardButton("📊 Статистика"), KeyboardButton("ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


async def _safe_reply(message, text, **kwargs):
    for attempt in range(3):
        try:
            return await message.reply_text(text, **kwargs)
        except TimedOut:
            logger.warning("TimedOut on attempt %d, retrying...", attempt + 1)
            if attempt == 2:
                raise
        except NetworkError as e:
            logger.warning("NetworkError on attempt %d: %s", attempt + 1, e)
            if attempt == 2:
                raise


async def _safe_edit(query, text, **kwargs):
    try:
        return await query.edit_message_text(text, **kwargs)
    except Exception as e:
        logger.warning("edit_message_text failed: %s", e)
        return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я дневник головной боли.\n"
        "Каждый день в {hour}:{minute:02d} я буду спрашивать, болела ли голова.\n\n"
        "Отвечай кнопками, и я сохраню статистику.".format(
            hour=QUESTION_HOUR, minute=QUESTION_MINUTE
        ),
        reply_markup=get_main_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n\n"
        "Каждый день в {hour}:{minute:02d} я пришлю вопрос: болела ли голова.\n"
        "Нажми «Да, болела» или «Нет, не болела».\n\n"
        "Команды:\n"
        "📋 Календарь — посмотреть дни за текущий месяц\n"
        "📊 Статистика — общая статистика\n"
        "ℹ️ Помощь — эта справка".format(
            hour=QUESTION_HOUR, minute=QUESTION_MINUTE
        ),
        reply_markup=get_main_keyboard(),
    )


async def send_daily_question(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    today = datetime.date.today().isoformat()
    user_data = get_user_data(chat_id)

    if today in user_data.get("answers", {}):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("😣 Да, болела", callback_data=f"pain_yes_{today}"),
            InlineKeyboardButton("😊 Нет, не болела", callback_data=f"pain_no_{today}"),
        ],
    ])

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Голова болела сегодня? ({date})".format(
                date=datetime.date.today().strftime("%d.%m.%Y")
            ),
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error("Failed to send daily question to %s: %s", chat_id, e)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("pain_"):
        parts = data.split("_")
        has_pain = parts[1] == "yes"
        date_str = parts[2]

        user_data = get_user_data(user_id)
        if "answers" not in user_data:
            user_data["answers"] = {}
        user_data["answers"][date_str] = has_pain
        save_user_data(user_id, user_data)

        emoji = "😣" if has_pain else "😊"
        text = "{emoji} Записал: {date} — {status}".format(
            emoji=emoji,
            date=datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y"),
            status="голова болела" if has_pain else "голова не болела",
        )
        await _safe_edit(query, text)
        return

    if data.startswith("cal_prev_") or data.startswith("cal_next_"):
        parts = data.split("_")
        year = int(parts[2])
        month = int(parts[3])
        if data.startswith("cal_prev_"):
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        else:
            month += 1
            if month > 12:
                month = 1
                year += 1
        keyboard, header = get_calendar_keyboard(user_id, year, month)
        await _safe_edit(query, header, reply_markup=keyboard)
        return

    if data == "cal_back":
        await _safe_edit(query, "Выбери действие:")
        await _safe_reply(query.message, "Выбери действие:", reply_markup=get_main_keyboard())
        return

    if data == "cal_ignore":
        await query.answer()


def get_calendar_keyboard(user_id, year, month):
    user_data = get_user_data(user_id)
    answers = user_data.get("answers", {})

    buttons = []
    buttons.append([
        InlineKeyboardButton("◀️", callback_data=f"cal_prev_{year}_{month}"),
        InlineKeyboardButton(f"{MONTHS_RU[month-1]} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"cal_next_{year}_{month}"),
    ])
    buttons.append([
        InlineKeyboardButton("Пн", callback_data="cal_ignore"),
        InlineKeyboardButton("Вт", callback_data="cal_ignore"),
        InlineKeyboardButton("Ср", callback_data="cal_ignore"),
        InlineKeyboardButton("Чт", callback_data="cal_ignore"),
        InlineKeyboardButton("Пт", callback_data="cal_ignore"),
        InlineKeyboardButton("Сб", callback_data="cal_ignore"),
        InlineKeyboardButton("Вс", callback_data="cal_ignore"),
    ])

    cal = calendar.monthcalendar(year, month)
    today = datetime.date.today()
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                if date_str in answers:
                    marker = "😣" if answers[date_str] else "✅"
                    row.append(InlineKeyboardButton(f"{day}{marker}", callback_data="cal_ignore"))
                else:
                    row.append(InlineKeyboardButton(str(day), callback_data="cal_ignore"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton("⬅️ В меню", callback_data="cal_back")])
    header = f"{MONTHS_RU[month-1]} {year}\n😣 — болела  ✅ — не болела"
    return InlineKeyboardMarkup(buttons), header


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "📋 Календарь":
        now = datetime.date.today()
        keyboard, header = get_calendar_keyboard(user_id, now.year, now.month)
        await update.message.reply_text(header, reply_markup=keyboard)
        return

    if text == "📊 Статистика":
        user_data = get_user_data(user_id)
        answers = user_data.get("answers", {})
        total = len(answers)
        pain_days = sum(1 for v in answers.values() if v)
        no_pain_days = total - pain_days

        if total == 0:
            await update.message.reply_text("Пока нет записей.", reply_markup=get_main_keyboard())
            return

        pain_pct = round(pain_days / total * 100)
        msg = (
            "📊 Статистика:\n\n"
            "Всего дней: {total}\n"
            "😣 Болела голова: {pain} ({pct}%)\n"
            "😊 Не болела: {no_pain}".format(
                total=total, pain=pain_days, pct=pain_pct, no_pain=no_pain_days
            )
        )
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())
        return

    if text == "ℹ️ Помощь":
        await cmd_help(update, context)
        return

    await update.message.reply_text("Выбери действие:", reply_markup=get_main_keyboard())


async def error_handler(update, context):
    logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)


async def post_init(application):
    job_queue = application.job_queue
    job_queue.run_daily(
        send_daily_question,
        time=datetime.time(hour=QUESTION_HOUR, minute=QUESTION_MINUTE, second=0),
        name="daily_headache_question",
    )
    logger.info("Scheduled daily question at %02d:%02d", QUESTION_HOUR, QUESTION_MINUTE)

    if update := application.update_queue:
        pass


def main():
    logger.info("Bot starting...")
    try:
        app = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(30)
            .post_init(post_init)
            .build()
        )
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)
        logger.info("Bot is running!")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
        raise


if __name__ == "__main__":
    main()
