import os
import base64
import json
import logging
from io import BytesIO

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


# --------------------------------------------------
# OPENAI INSTRUCTIONS
# --------------------------------------------------

SYSTEM_PROMPT = """
You are a conservative screenshot-based chart analysis assistant.

The user sends a screenshot of a Pocket Option-style candlestick chart.

Analyze ONLY what is visibly supported by the screenshot.

You do NOT know future prices and must never claim certainty,
guaranteed wins, or guaranteed accuracy.

Choose exactly one:
BUY, SELL, or WAIT.

Consider visible factors such as:

- recent price structure and direction
- recent candles and momentum
- rejection wicks and candle confirmation
- visible support and resistance
- visible indicators
- agreement or conflict between indicators

Prefer WAIT when:

- the chart is unclear
- the screenshot is incomplete
- the market looks sideways
- indicators conflict
- there is insufficient confirmation

Do not blindly follow indicator arrows.

Do not invent information that is not visible.

A screenshot may not clearly show the exact candle timing.
If the timeframe is not clearly visible, say so.

This is experimental chart analysis and not financial advice.

Return ONLY valid JSON in exactly this structure:

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

The signal must be exactly BUY, SELL, or WAIT.

Strength must be exactly STRONG, MODERATE, or WEAK.

Confidence must be an integer from 0 to 100.

timeframe_visible must be true or false.
"""


# --------------------------------------------------
# JSON PARSER
# --------------------------------------------------

def parse_json(text: str):
    text = text.strip()

    if text.startswith("```"):
        parts = text.split("```")

        if len(parts) >= 3:
            text = parts[1]

            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:]

    return json.loads(text.strip())


# --------------------------------------------------
# /START
# --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    logger.info("START command received")

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear screenshot of your chart.\n\n"
        "I will analyze the visible chart and return:\n"
        "🟢 BUY\n"
        "🔴 SELL\n"
        "⚪ WAIT\n\n"
        "For best results, keep recent candles and the timeframe visible."
    )


# --------------------------------------------------
# /HELP
# --------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 How to use the bot:\n\n"
        "1. Open your chart.\n"
        "2. Make sure recent candles are visible.\n"
        "3. Make the timeframe visible if possible.\n"
        "4. Take a clear screenshot.\n"
        "5. Send the screenshot here.\n\n"
        "The bot is conservative and may return WAIT when the setup is unclear."
    )


# --------------------------------------------------
# PHOTO / SCREENSHOT HANDLER
# --------------------------------------------------

async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    try:

        logger.info("PHOTO HANDLER STARTED")

        if not message or not message.photo:
            logger.warning("Photo handler called but no photo was found")

            await message.reply_text(
                "⚠️ I could not detect the screenshot."
            )

            return

        photo = message.photo[-1]

        logger.info(
            "Photo received successfully. File ID: %s",
            photo.file_id
        )

        await message.chat.send_action(ChatAction.TYPING)

        logger.info("Downloading image from Telegram...")

        tg_file = await context.bot.get_file(photo.file_id)

        buffer = BytesIO()

        await tg_file.download_to_memory(out=buffer)

        image_bytes = buffer.getvalue()

        logger.info(
            "Image downloaded successfully: %s bytes",
            len(image_bytes)
        )

        if not image_bytes:
            raise RuntimeError("Downloaded image is empty")

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        image_url = f"data:image/jpeg;base64,{image_b64}"

        logger.info(
            "Sending image to OpenAI. Model: %s",
            OPENAI_MODEL
        )

        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this trading chart screenshot "
                                "conservatively."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
        )

        logger.info("OpenAI response received")

        response_text = response.output_text

        logger.info(
            "OpenAI response length: %s",
            len(response_text)
        )

        # ------------------------------------------
        # PARSE OPENAI RESPONSE
        # ------------------------------------------

        try:

            result = parse_json(response_text)

        except Exception as error:

            logger.exception(
                "JSON parsing failed: %s",
                error
            )

            await message.reply_text(
                "⚪ WAIT\n\n"
                "I received your screenshot, but the analysis "
                "could not be interpreted reliably.\n\n"
                "Please try sending the screenshot again."
            )

            return

        # ------------------------------------------
        # BUILD RESPONSE
        # ------------------------------------------

        signal = str(
            result.get("signal", "WAIT")
        ).upper()

        if signal not in ["BUY", "SELL", "WAIT"]:
            signal = "WAIT"

        icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "⚪",
        }.get(signal, "⚪")

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

        risk = result.get(
            "risk",
            "A screenshot cannot guarantee the next price movement."
        )

        timeframe_visible = result.get(
            "timeframe_visible",
            False
        )

        if not isinstance(reasons, list):
            reasons = [str(reasons)]

        reason_text = "\n".join(
            f"• {reason}"
            for reason in reasons[:3]
        )

        if not reason_text:
            reason_text = "• No strong confirmation."

        reply = (
            "📊 <b>CHART ANALYSIS</b>\n\n"
            f"{icon} <b>SIGNAL: {signal}</b>\n"
            f"💪 Strength: <b>{strength}</b>\n"
            f"📈 Experimental confidence: <b>{confidence}%</b>\n\n"
            "<b>Summary</b>\n"
            f"{summary}\n\n"
            "<b>Visible reasons</b>\n"
            f"{reason_text}\n\n"
            "⚠️ <b>Caution:</b> "
            f"{risk}\n"
        )

        if not timeframe_visible:

            reply += (
                "\n⏱️ The requested timeframe was not clearly "
                "confirmed from the screenshot.\n"
            )

        reply += (
            "\n<i>Experimental chart analysis only. "
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

        try:

            await message.reply_text(
                "⚠️ I received your screenshot, but an error "
                "occurred while analyzing it.\n\n"
                "The error has been recorded in the Railway logs."
            )

        except Exception:

            logger.exception(
                "Could not send error message to Telegram."
            )


# --------------------------------------------------
# DIAGNOSTIC TEXT HANDLER
# --------------------------------------------------

async def diagnostic_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    logger.info(
        "DIAGNOSTIC MESSAGE RECEIVED: %s",
        message.text if message else "NO TEXT"
    )

    await message.reply_text(
        "✅ I received your message.\n\n"
        "The Telegram connection is working.\n"
        "Now send me your chart screenshot."
    )


# --------------------------------------------------
# ERROR HANDLER
# --------------------------------------------------

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "TELEGRAM BOT ERROR: %s",
        context.error
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    logger.info("Starting Chart Signal Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Commands
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

    # IMPORTANT:
    # Photo handler comes before the general text handler.
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            analyze_photo
        )
    )

    # Diagnostic handler for ordinary messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            diagnostic_message
        )
    )

    # Error handler
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
