import os
import base64
import logging

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are a conservative screenshot-based chart analysis assistant.

The user sends a screenshot of a Pocket Option-style candlestick chart.

Analyze ONLY what is visibly supported by the screenshot.

Choose exactly one:
BUY, SELL, or WAIT.

Consider:
- recent price structure
- candle direction and momentum
- rejection wicks
- visible support and resistance
- visible indicators
- agreement or conflict between indicators

Prefer WAIT when the chart is unclear, sideways, incomplete,
or contradictory.

Never claim certainty or guaranteed profit.

Return ONLY valid JSON in exactly this format:

{
  "signal": "BUY",
  "strength": "STRONG",
  "confidence": 75,
  "summary": "Short explanation.",
  "reasons": [
    "Reason 1",
    "Reason 2",
    "Reason 3"
  ],
  "risk": "Short caution.",
  "timeframe_visible": true
}

signal must be BUY, SELL, or WAIT.

strength must be STRONG, MODERATE, or WEAK.

confidence must be an integer from 0 to 100.

timeframe_visible must be true or false.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear chart screenshot and I will analyze it."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Send a clear screenshot of your trading chart.\n\n"
        "Keep recent candles and the timeframe visible if possible."
    )


async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    try:
        logger.info("PHOTO HANDLER STARTED")

        await message.chat.send_action(ChatAction.TYPING)

        photo = message.photo[-1]

        logger.info("Downloading Telegram image...")

        tg_file = await context.bot.get_file(photo.file_id)

        image_bytes = await tg_file.download_as_bytearray()

        logger.info(
            "Image downloaded: %s bytes",
            len(image_bytes)
        )

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        logger.info("Sending image to Gemini...")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                ),
                SYSTEM_PROMPT,
                "Analyze this trading chart screenshot conservatively."
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        logger.info("Gemini response received")

        text = response.text.strip()

        # Remove markdown code fences if Gemini adds them
        if text.startswith("```"):
            text = text.replace("```json", "")
            text = text.replace("```", "")
            text = text.strip()

        import json

        result = json.loads(text)

        signal = str(
            result.get("signal", "WAIT")
        ).upper()

        if signal not in ["BUY", "SELL", "WAIT"]:
            signal = "WAIT"

        icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "⚪",
        }[signal]

        strength = result.get("strength", "WEAK")
        confidence = result.get("confidence", 0)
        summary = result.get(
            "summary",
            "No clear setup."
        )

        reasons = result.get("reasons", [])

        if not isinstance(reasons, list):
            reasons = [str(reasons)]

        reason_text = "\n".join(
            f"• {r}" for r in reasons[:3]
        )

        risk = result.get(
            "risk",
            "A screenshot cannot guarantee the next price movement."
        )

        reply = (
            "📊 <b>CHART ANALYSIS</b>\n\n"
            f"{icon} <b>SIGNAL: {signal}</b>\n"
            f"💪 Strength: <b>{strength}</b>\n"
            f"📈 Experimental confidence: <b>{confidence}%</b>\n\n"
            "<b>Summary</b>\n"
            f"{summary}\n\n"
            "<b>Visible reasons</b>\n"
            f"{reason_text}\n\n"
            f"⚠️ <b>Caution:</b> {risk}\n"
        )

        if not result.get("timeframe_visible", False):
            reply += (
                "\n⏱️ Timeframe was not clearly visible."
            )

        reply += (
            "\n\n<i>Experimental chart analysis only. "
            "No prediction is guaranteed.</i>"
        )

        await message.reply_text(
            reply,
            parse_mode="HTML"
        )

        logger.info(
            "ANALYSIS SUCCESSFULLY SENT: %s",
            signal
        )

    except Exception as error:

        logger.exception(
            "ERROR WHILE PROCESSING PHOTO: %s",
            error
        )

        await message.reply_text(
            "⚠️ I received your screenshot, but an error "
            "occurred while analyzing it.\n\n"
            "Please check the Railway logs."
        )


async def diagnostic_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "✅ I received your message.\n\n"
        "Send me your chart screenshot."
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "TELEGRAM ERROR: %s",
        context.error
    )


def main():

    logger.info("Starting Chart Signal Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            analyze_photo
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            diagnostic_message
        )
    )

    app.add_error_handler(error_handler)

    logger.info("Bot is starting polling...")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
