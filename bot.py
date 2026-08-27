import os
import json
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


# ============================================================
# SETUP
# ============================================================

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


# ============================================================
# FAST ANALYSIS INSTRUCTIONS
# ============================================================

SYSTEM_PROMPT = """
You are a fast, conservative screenshot-based chart analysis assistant.

The user sends a screenshot of a Pocket Option-style candlestick chart.

Analyze ONLY what is clearly visible.

Give ONE short trading assessment.

Choose exactly one signal:

BUY
SELL
WAIT

Choose exactly one entry decision:

ENTER
WAIT
NO_TRADE

Suggest ONE trade expiration:

1 minute
2 minutes
5 minutes
10 minutes
15 minutes
30 minutes
1 hour
Not clear

The suggested expiration is the estimated duration for the trade based
on the visible chart structure and momentum. It is NOT guaranteed.

Analyze quickly using the most important visible factors:

- recent candle direction
- short-term momentum
- higher highs / higher lows
- lower highs / lower lows
- support and resistance
- rejection candles
- visible moving averages
- visible trend lines
- visible indicators
- whether price is moving strongly or sideways

Do NOT blindly follow indicator arrows.

Do NOT invent information.

If the chart is genuinely unclear or contradictory, use WAIT and NO_TRADE.

If there is a reasonable directional setup, use BUY or SELL.

Use ENTER only when the visible setup has reasonably strong confirmation.

Use WAIT when the direction looks possible but entering immediately is
not advisable.

Never claim guaranteed profit, guaranteed accuracy, or certainty.

Confidence is only an experimental measure of how strongly the visible
evidence supports the signal.

Return ONLY valid JSON in exactly this format:

{
  "signal": "BUY",
  "confidence": 65,
  "trade_expiration": "5 minutes",
  "entry_decision": "ENTER",
  "risk": "Price is near resistance, so a reversal is possible."
}

Rules:

signal = BUY, SELL, or WAIT

confidence = integer from 0 to 100

trade_expiration =
"1 minute"
"2 minutes"
"5 minutes"
"10 minutes"
"15 minutes"
"30 minutes"
"1 hour"
"Not clear"

entry_decision =
"ENTER"
"WAIT"
"NO_TRADE"

risk = one short sentence
"""


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info("START command received")

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear chart screenshot.\n\n"
        "I will return:\n"
        "🟢 BUY / 🔴 SELL / ⚪ WAIT\n"
        "📈 Confidence\n"
        "⏱️ Trade expiration\n"
        "🎯 Entry decision\n"
        "⚠️ Risk"
    )


# ============================================================
# HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Send me a clear chart screenshot.\n\n"
        "The bot will quickly analyze it and return "
        "the signal, trade expiration, entry decision, "
        "confidence and risk."
    )


# ============================================================
# PHOTO ANALYSIS
# ============================================================

async def analyze_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    try:

        logger.info("PHOTO HANDLER STARTED")

        await message.chat.send_action(
            ChatAction.TYPING
        )

        photo = message.photo[-1]

        logger.info("Downloading Telegram image...")

        tg_file = await context.bot.get_file(
            photo.file_id
        )

        image_bytes = await tg_file.download_as_bytearray()

        logger.info(
            "Image downloaded: %s bytes",
            len(image_bytes)
        )

        if not image_bytes:
            raise RuntimeError(
                "Downloaded image is empty"
            )

        logger.info(
            "Sending image to Gemini..."
        )

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                ),
                SYSTEM_PROMPT,
                "Analyze this chart quickly."
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
        )

        logger.info(
            "Gemini response received"
        )

        text = response.text.strip()

        # Remove markdown formatting if returned
        if text.startswith("```"):

            text = text.replace(
                "```json",
                ""
            )

            text = text.replace(
                "```",
                ""
            )

            text = text.strip()

        result = json.loads(text)

        # ====================================================
        # READ RESULT
        # ====================================================

        signal = str(
            result.get(
                "signal",
                "WAIT"
            )
        ).upper()

        if signal not in [
            "BUY",
            "SELL",
            "WAIT"
        ]:
            signal = "WAIT"

        confidence = result.get(
            "confidence",
            0
        )

        expiration = result.get(
            "trade_expiration",
            "Not clear"
        )

        entry = str(
            result.get(
                "entry_decision",
                "NO_TRADE"
            )
        ).upper()

        if entry not in [
            "ENTER",
            "WAIT",
            "NO_TRADE"
        ]:
            entry = "NO_TRADE"

        risk = result.get(
            "risk",
            "The next price movement is uncertain."
        )

        # ====================================================
        # ICONS
        # ====================================================

        signal_icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "⚪"
        }.get(
            signal,
            "⚪"
        )

        if entry == "ENTER":

            entry_text = "✅ ENTER"

        elif entry == "WAIT":

            entry_text = "⏳ WAIT"

        else:

            entry_text = "🚫 NO TRADE"

        # ====================================================
        # SHORT RESPONSE
        # ====================================================

        reply = (
            "📊 <b>CHART SIGNAL</b>\n\n"

            f"{signal_icon} "
            f"<b>{signal}</b>\n\n"

            f"📈 Confidence: "
            f"<b>{confidence}%</b>\n"

            f"⏱️ Trade expiration: "
            f"<b>{expiration}</b>\n"

            f"🎯 Entry: "
            f"<b>{entry_text}</b>\n\n"

            f"⚠️ Risk: {risk}\n\n"

            "<i>Experimental analysis only. "
            "No result is guaranteed.</i>"
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
            "⚠️ I received your screenshot, but an "
            "error occurred while analyzing it."
        )


# ============================================================
# DIAGNOSTIC TEXT HANDLER
# ============================================================

async def diagnostic_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info(
        "DIAGNOSTIC MESSAGE RECEIVED"
    )

    await update.message.reply_text(
        "✅ Bot is working.\n\n"
        "Send your chart screenshot."
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "TELEGRAM ERROR: %s",
        context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "Starting Chart Signal Bot..."
    )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
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

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "Bot handlers registered successfully."
    )

    logger.info(
        "Starting Telegram polling..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
