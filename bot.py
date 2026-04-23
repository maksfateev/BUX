import os
import json
import base64
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

# --- Настройки ---
BOT_TOKEN = "8686463901:AAHMjVL6lo_Z71sf1OnLsKWgXaT4UOtAgsQ"
OPENAI_API_KEY = "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"
SPREADSHEET_ID = "1D7yDn5NB-W-1SQgVN4EIQX4a2MEyHycLoZOoPuWy3QQ"

# --- Google Sheets через переменную окружения ---
scopes = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

google_creds_json = os.environ.get("GOOGLE_CREDENTIALS")
if google_creds_json:
    creds_dict = json.loads(google_creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
else:
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

HEADERS = ["Дата", "Магазин", "Сумма", "Валюта", "Категория", "Товары", "Кто добавил", "Время записи"]

def ensure_headers():
    first_row = sheet.row_values(1)
    if first_row != HEADERS:
        sheet.insert_row(HEADERS, 1)

# --- OpenAI ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)

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
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

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
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

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

        reply = (
            f"✅ *Чек успешно добавлен в таблицу!*\n\n"
            f"📅 Дата: {row[0]}\n"
            f"🏪 Магазин: {row[1]}\n"
            f"💰 Сумма: {row[2]} {row[3]}\n"
            f"🏷 Категория: {row[4]}\n"
            f"📝 Товары: {row[5]}"
        )
        await msg.reply_text(reply, parse_mode="Markdown")

    except json.JSONDecodeError:
        await msg.reply_text("⚠️ Не удалось распознать данные с чека. Попробуй сфотографировать чётче.")
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка: {str(e)}")
        print(f"Ошибка: {e}")

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привет! Я бухгалтерский бот.*\n\n"
        "Отправь мне фото чека — я распознаю его и автоматически добавлю данные в Google Таблицу.\n\n"
        "📌 *Советы для лучшего распознавания:*\n"
        "• Фотографируй чек на ровной поверхности\n"
        "• Следи чтобы весь чек был в кадре\n"
        "• Хорошее освещение — лучший результат",
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Отправь мне фото чека!")

def main():
    ensure_headers()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ Бот запущен! Ожидаю чеки...")
    app.run_polling()

if __name__ == "__main__":
    main()
