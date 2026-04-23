import os
import json
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

# --- Настройки ---
BOT_TOKEN = "8686463901:AAHMjVL6lo_Z71sf1OnLsKWgXaT4UOtAgsQ"
OPENAI_API_KEY = "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"
SPREADSHEET_ID = "1D7yDn5NB-W-1SQgVN4EIQX4a2MEyHycLoZOoPuWy3QQ"
CREDENTIALS_FILE = "credentials.json"  # положи рядом с bot.py

# --- Клиенты ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)

scopes = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

# Заголовки таблицы (добавляются один раз)
HEADERS = ["Дата", "Магазин", "Сумма", "Валюта", "Категория", "Товары", "Кто добавил", "Время записи"]

def ensure_headers():
    first_row = sheet.row_values(1)
    if first_row != HEADERS:
        sheet.insert_row(HEADERS, 1)

# --- Промт для GPT-4o ---
SYSTEM_PROMPT = """Ты бухгалтерский помощник. Анализируй изображение чека и извлекай данные.
Верни ТОЛЬКО JSON без markdown и без дополнительного текста, строго в формате:
{
  "date": "ДД.ММ.ГГГГ",
  "store": "название магазина или заведения",
  "total": 0.00,
  "category": "одно из: Продукты / Кафе и рестораны / Транспорт / Офис / Медицина / Другое",
  "items": "краткий список товаров через запятую, максимум 100 символов",
  "currency": "RUB"
}
Если какое-то поле невозможно прочитать — используй null."""

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await msg.reply_text("⏳ Анализирую чек, подожди немного...")

    try:
        # Скачиваем фото в лучшем качестве
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        # Запрос к GPT-4o Vision
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": msg.caption or "Распознай данные с чека"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}"
                    }}
                ]}
            ],
            max_tokens=500
        )

        raw = response.choices[0].message.content.strip()

        # Убираем markdown если модель всё же добавила
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        # Запись в Google Sheets
        row = [
            data.get("date") or datetime.now().strftime("%d.%m.%Y"),
            data.get("store") or "—",
            data.get("total") or 0,
            data.get("currency") or "RUB",
            data.get("category") or "Другое",
            data.get("items") or "—",
            msg.from_user.full_name,
            datetime.now().strftime("%d.%m.%Y %H:%M")
        ]
        sheet.append_row(row)

        # Красивый ответ пользователю
        total = row[2]
        reply = (
            f"✅ *Чек успешно добавлен в таблицу!*\n\n"
            f"📅 Дата: {row[0]}\n"
            f"🏪 Магазин: {row[1]}\n"
            f"💰 Сумма: {total} {row[3]}\n"
            f"🏷 Категория: {row[4]}\n"
            f"📝 Товары: {row[5]}"
        )
        await msg.reply_text(reply, parse_mode="Markdown")

    except json.JSONDecodeError:
        await msg.reply_text(
            "⚠️ Не удалось распознать данные с чека. "
            "Попробуй сфотографировать чётче или при лучшем освещении."
        )
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка: {str(e)}")
        print(f"Ошибка: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "/start":
        await update.message.reply_text(
            "👋 *Привет! Я бухгалтерский бот.*\n\n"
            "Отправь мне фото чека — я распознаю его и автоматически добавлю данные в Google Таблицу.\n\n"
            "📌 *Советы для лучшего распознавания:*\n"
            "• Фотографируй чек на ровной поверхности\n"
            "• Следи чтобы весь чек был в кадре\n"
            "• Хорошее освещение — лучший результат\n\n"
            "Можешь добавить подпись к фото чтобы уточнить категорию.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("📸 Отправь мне фото чека!")

# --- Запуск ---
def main():
    ensure_headers()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    print("✅ Бот запущен! Ожидаю чеки...")
    app.run_polling()

if __name__ == "__main__":
    main()
