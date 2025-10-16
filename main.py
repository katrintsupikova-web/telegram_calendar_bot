import datetime
import gspread
from google.oauth2.service_account import Credentials
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Таблица для календаря")
GOOGLE_CREDS_FILE = "credentials.json"  # имя файла с ключом сервисного аккаунта

# Названия столбцов
DATE_COLUMN_NAME = 'Дата план'
STATUS_COLUMN_NAME = 'Статус'
CLIENT_COLUMN_NAME = 'Клиент'
BLOGGER_COLUMN_NAME = 'Ссылка на социальную сеть блогера'
MANAGER_COLUMN_NAME = 'Имя менеджера'

# === Подключение к Google Sheets ===
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open(SPREADSHEET_NAME).sheet1

excluded_statuses = ["Промаркировано", "Креатив согласован", "Интаграция вышла"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# --- Функция нормализации даты ---
def normalize_date(date_str):
    date_str = date_str.strip()
    if not date_str:
        return None
    parts = date_str.split(".")
    if len(parts) == 2:  # дд.мм
        d, m = parts
        d = d.zfill(2)
        m = m.zfill(2)
        return f"{d}.{m}.{datetime.datetime.now().year}"
    elif len(parts) == 3:
        d, m, y = parts
        d = d.zfill(2)
        m = m.zfill(2)
        if len(y) == 2:
            y = "20" + y
        return f"{d}.{m}.{y}"
    return date_str

# --- Получаем задачи по дате ---
def get_tasks_for_date(target_date):
    all_values = sheet.get_all_values()
    header = all_values[0]

    date_col = header.index(DATE_COLUMN_NAME)
    status_col = header.index(STATUS_COLUMN_NAME)
    client_col = header.index(CLIENT_COLUMN_NAME)
    blogger_col = header.index(BLOGGER_COLUMN_NAME)
    manager_col = header.index(MANAGER_COLUMN_NAME)

    tasks = []
    for row in all_values[1:]:
        if len(row) <= max(date_col, status_col, client_col, blogger_col, manager_col):
            continue

        date_cell = normalize_date(row[date_col])
        status_value = row[status_col].strip() if len(row) > status_col else ""

        if not date_cell or status_value in excluded_statuses:
            continue

        if date_cell == target_date:
            client = row[client_col].strip()
            blogger = row[blogger_col].strip()
            manager = row[manager_col].strip()
            tasks.append((client, blogger, manager, date_cell))
    return tasks

# --- Отправка интерактивного чеклиста ---
def send_checklist(chat_id, tasks, title="Запланированные интеграции"):
    if not tasks:
        bot.send_message(chat_id, f"{title}:\nНет запланированных интеграций.")
        return

    markup = InlineKeyboardMarkup()
    for i, (client, blogger, manager, date_str) in enumerate(tasks):
        button_text = f"☐ {client} {blogger} {manager}"
        if "выходные" in title.lower():
            button_text += f" {date_str}"
        markup.add(InlineKeyboardButton(text=button_text, callback_data=f"task_{i}"))

    bot.send_message(chat_id, f"{title}:", reply_markup=markup)

# --- Обработчик кликов ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("task_"))
def callback_task(call):
    idx = int(call.data.split("_")[1])
    keyboard = call.message.reply_markup.keyboard
    old_text = keyboard[idx][0].text
    new_text = old_text.replace("☐", "✅") if "☐" in old_text else old_text.replace("✅", "☐")
    keyboard[idx][0].text = new_text

    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Команды ---
@bot.message_handler(commands=['plantoday'])
def plantoday(message):
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    tasks = get_tasks_for_date(today)
    send_checklist(message.chat.id, tasks, title="Запланированные интеграции на сегодня")

@bot.message_handler(commands=['plantomorrow'])
def plantomorrow(message):
    now = datetime.datetime.now()
    weekday = now.weekday()
    tomorrow = now + datetime.timedelta(days=1)

    if weekday == 4:  # Пятница — план на сб и вс
        saturday = now + datetime.timedelta(days=1)
        sunday = now + datetime.timedelta(days=2)
        tasks_sat = get_tasks_for_date(saturday.strftime("%d.%m.%Y"))
        tasks_sun = get_tasks_for_date(sunday.strftime("%d.%m.%Y"))
        tasks = tasks_sat + tasks_sun
        send_checklist(message.chat.id, tasks, title="Запланированные интеграции на выходные")
    else:
        tasks = get_tasks_for_date(tomorrow.strftime("%d.%m.%Y"))
        send_checklist(message.chat.id, tasks, title="Запланированные интеграции на завтра")

# --- Запуск ---
if __name__ == "__main__":
    bot.infinity_polling()
