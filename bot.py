import os
import base64
import json
import logging
from io import BytesIO

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
logging.basicConfig(level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are a conservative screenshot-based chart analysis assistant.

The user sends a screenshot of a Pocket Option-style candlestick chart. Analyze only what is visibly supported by the screenshot. You do NOT know future prices and must never claim certainty, guaranteed wins, or a guaranteed win rate.

Your task is to choose exactly one:
BUY, SELL, or WAIT.

Use these visible factors when possible:
- recent price structure and direction
- the last several candles and momentum
- rejection wicks / candle confirmation
- support/resistance areas visible on the chart
- whether visible indicators agree or conflict

Important:
- Prefer WAIT when the screenshot is cluttered, incomplete, sideways, contradictory, or not readable.
- Do not blindly follow an indicator arrow.
- Do not invent unseen data.
- A screenshot alone may not show the exact 10-minute candle timing. If the timeframe or timing is not clearly visible, say so.
- This is an experimental analysis, not financial advice.

Return ONLY valid JSON in this exact format:
{
  "signal": "BUY" | "SELL" | "WAIT",
  "strength": "STRONG" | "MODERATE" | "WEAK",
  "confidence": integer from 0 to 100,
  "summary": "one short sentence",
  "reasons": ["reason 1", "reason 2", "reason 3"],
  "risk": "one short caution",
  "timeframe_visible": true | false
}
"""

def parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    return json.loads(text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear screenshot of your chart. I will return:\n"
        "🟢 BUY / 🔴 SELL / ⚪ WAIT\n"
        "plus the visible reasons and a caution.\n\n"
        "For best results, keep the chart and recent candles clearly visible."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How to use:\n"
        "1. Open your chart.\n"
        "2. Use the 10-minute view if that is your strategy.\n"
        "3. Take a clear screenshot with recent candles visible.\n"
        "4. Send the screenshot here.\n\n"
        "The bot is conservative: unclear setups should return WAIT."
    )

async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    photo = message.photo[-1]
    await message.chat.send_action(ChatAction.TYPING)

    tg_file = await context.bot.get_file(photo.file_id)
    buffer = BytesIO()
    await tg_file.download_to_memory(out=buffer)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    image_url = f"data:image/jpeg;base64,{image_b64}"

    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this chart screenshot conservatively."},
                {"type": "input_image", "image_url": image_url, "detail": "high"}
            ]
        }]
    )

    try:
        result = parse_json(response.output_text)
    except Exception:
        await message.reply_text(
            "⚪ WAIT\n\nI could not read the chart reliably from this screenshot. "
            "Please send a clearer screenshot with the recent candles visible."
        )
        return

    signal = result.get("signal", "WAIT")
    icon = {"BUY": "🟢", "SELL": "🔴", "WAIT": "⚪"}.get(signal, "⚪")

    reasons = result.get("reasons", [])
    reason_text = "\n".join(f"• {r}" for r in reasons[:3]) or "• No strong confirmation"

    reply = (
        f"📊 <b>CHART ANALYSIS</b>\n\n"
        f"{icon} <b>SIGNAL: {signal}</b>\n"
        f"💪 Strength: <b>{result.get('strength', 'WEAK')}</b>\n"
        f"📈 Experimental confidence: <b>{result.get('confidence', 0)}%</b>\n\n"
        f"<b>Summary</b>\n{result.get('summary', 'No clear setup.')}\n\n"
        f"<b>Visible reasons</b>\n{reason_text}\n\n"
        f"⚠️ <b>Caution:</b> {result.get('risk', 'A screenshot cannot guarantee the next candle.')}\n"
    )

    if not result.get("timeframe_visible", False):
        reply += "\n⏱️ The requested timeframe was not clearly confirmed from the screenshot."

    reply += "\n\n<i>Experimental chart analysis only. No prediction is guaranteed.</i>"
    await message.reply_text(reply, parse_mode="HTML")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_photo))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
