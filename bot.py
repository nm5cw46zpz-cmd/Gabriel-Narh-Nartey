import os
import base64
import logging
import json

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

# --------------------------------------------------
# SETUP
# --------------------------------------------------

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


# --------------------------------------------------
# GEMINI INSTRUCTIONS
# --------------------------------------------------

SYSTEM_PROMPT = """
You are a conservative screenshot-based chart analysis assistant.

The user sends a screenshot of a Pocket Option-style candlestick chart.

Analyze ONLY what is visibly supported by the screenshot.

Choose exactly one:
BUY, SELL, or WAIT.

Consider:

- recent price structure
- recent candle direction
- candle momentum
- rejection wicks
- visible support and resistance
- visible indicators
- agreement or conflict between indicators

Prefer WAIT when the chart is:

- unclear
- incomplete
- sideways
- contradictory
- missing important information

Do not blindly follow indicator arrows.

Do not invent information that is not visible.

Never claim certainty, guaranteed profit, or guaranteed accuracy.

This is experimental chart analysis only.

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

Rules:

signal must be BUY, SELL, or WAIT.

strength must be STRONG, MODERATE, or WEAK.

confidence must be an integer from 0 to 100.

timeframe_visible must be true or false.
"""


# --------------------------------------------------
# START COMMAND
# --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    logger.info("START command received")

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear screenshot of your trading chart.\n\n"
        "I will analyze the visible chart and return:\n"
        "🟢 BUY\n"
        "🔴 SELL\n"
        "⚪ WAIT\n\n"
        "For best results, keep recent candles and the "
        "timeframe visible."
    )


# --------------------------------------------------
# HELP COMMAND
# --------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Open your trading chart.\n"
        "2. Make recent candles visible.\n"
        "3. Make the timeframe visible if possible.\n"
        "4. Take a clear screenshot.\n"
        "5. Send the screenshot here."
    )


# --------------------------------------------------
# PHOTO ANALYSIS
# --------------------------------------------------

async def analyze_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    try:

        logger.info("PHOTO HANDLER STARTED")

        if not message or not message.photo:
            logger.warning("No photo found")

            await message.reply_text(
                "⚠️ I could not detect the screenshot."
            )

            return

        await message.chat.send_action(
            ChatAction.TYPING
        )

        photo = message.photo[-1]

        logger.info(
            "Photo received. File ID: %s",
            photo.file_id
        )

        logger.info(
            "Downloading Telegram image..."
        )

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
                "Analyze this trading chart screenshot conservatively."
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        logger.info(
            "Gemini response received"
        )

        text = response.text.strip()

        logger.info(
            "Gemini response length: %s",
            len(text)
        )

        # Remove markdown code fences
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

        # Parse JSON
        result = json.loads(text)

        # --------------------------------------------------
        # SIGNAL
        # --------------------------------------------------

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

        icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "⚪"
        }[signal]

        strength = result.get(
            "strength",
            "WEAK"
        )

        confidence = result.get(
            "confidence",
            0
        )

        summary = result.get(
            "summary",
            "No clear setup was identified."
        )

        reasons = result.get(
            "reasons",
            []
        )

        if not isinstance(
            reasons,
            list
        ):
            reasons = [
                str(reasons)
            ]

        reason_text = "\n".join(
            f"• {reason}"
            for reason in reasons[:3]
        )

        if not reason_text:
            reason_text = (
                "• No strong confirmation."
            )

        risk = result.get(
            "risk",
            "A screenshot cannot guarantee the next price movement."
        )

        timeframe_visible = result.get(
            "timeframe_visible",
            False
        )

        # --------------------------------------------------
        # TELEGRAM RESPONSE
        # --------------------------------------------------

        reply = (
            "📊 <b>CHART ANALYSIS</b>\n\n"
            f"{icon} <b>SIGNAL: {signal}</b>\n"
            f"💪 Strength: <b>{strength}</b>\n"
            f"📈 Experimental confidence: "
            f"<b>{confidence}%</b>\n\n"
            "<b>Summary</b>\n"
            f"{summary}\n\n"
            "<b>Visible reasons</b>\n"
            f"{reason_text}\n\n"
            f"⚠️ <b>Caution:</b> {risk}\n"
        )

        if not timeframe_visible:

            reply += (
                "\n⏱️ The timeframe was not clearly "
                "visible in the screenshot.\n"
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
            "⚠️ I received your screenshot, but an "
            "error occurred while analyzing it.\n\n"
            "Please check the Railway logs."
        )


# --------------------------------------------------
# DIAGNOSTIC TEXT HANDLER
# --------------------------------------------------

async def diagnostic_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info(
        "DIAGNOSTIC MESSAGE RECEIVED"
    )

    await update.message.reply_text(
        "✅ I received your message.\n\n"
        "Send me your chart screenshot."
    )


# --------------------------------------------------
# ERROR HANDLER
# --------------------------------------------------

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "TELEGRAM ERROR: %s",
        context.error
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    logger.info(
        "Starting Chart Signal Bot..."
    )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # /help
    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    # Screenshots
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            analyze_photo
        )
    )

    # Normal text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            diagnostic_message
        )
    )

    # Errors
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


# --------------------------------------------------
# RUN
# --------------------------------------------------

if __name__ == "__main__":
    main()
