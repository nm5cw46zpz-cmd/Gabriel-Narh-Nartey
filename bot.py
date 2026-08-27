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

# Load environment variables
load_dotenv()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


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

Return ONLY valid JSON using exactly this structure:

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


def parse_json(text: str):
    """Convert the model's JSON response into a Python dictionary."""

    text = text.strip()

    # Remove markdown code fences if the model adds them
    if text.startswith("```"):
        parts = text.split("```")

        if len(parts) >= 3:
            text = parts[1]

            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:]

    return json.loads(text.strip())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start."""

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear screenshot of your chart.\n\n"
        "I will analyze the visible chart and return:\n"
        "🟢 BUY\n"
        "🔴 SELL\n"
        "⚪ WAIT\n\n"
        "For best results, keep recent candles and the timeframe visible."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""

    await update.message.reply_text(
        "📖 How to use the bot:\n\n"
        "1. Open your chart.\n"
        "2. Make sure recent candles are visible.\n"
        "3. Make the timeframe visible if possible.\n"
        "4. Take a clear screenshot.\n"
        "5. Send the screenshot here.\n\n"
        "The bot is conservative and may return WAIT when the setup is unclear."
    )


async def analyze_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a chart screenshot and analyze it."""

    message = update.message

    try:
        logger.info("📸 Photo received from Telegram")

        if not message.photo:
            await message.reply_text(
                "⚪ WAIT\n\n"
                "I could not detect the image. Please send the chart "
                "as a normal Telegram photo."
            )
            return

        # Get highest-resolution Telegram photo
        photo = message.photo[-1]

        logger.info("Downloading Telegram image...")

        await message.chat.send_action(ChatAction.TYPING)

        tg_file = await context.bot.get_file(photo.file_id)

        buffer = BytesIO()

        await tg_file.download_to_memory(out=buffer)

        image_bytes = buffer.getvalue()

        if not image_bytes:
            raise RuntimeError("Downloaded image is empty")

        logger.info(
            "Image downloaded successfully: %s bytes",
            len(image_bytes),
        )

        # Convert image to base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        image_url = f"data:image/jpeg;base64,{image_b64}"

        logger.info(
            "Sending image to OpenAI using model: %s",
            OPENAI_MODEL,
        )

        # Send image to OpenAI
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
            len(response_text),
        )

        # Convert JSON response
        try:
            result = parse_json(response_text)

        except Exception as json_error:

            logger.error(
                "Could not parse OpenAI JSON response: %s",
                json_error,
            )

            await message.reply_text(
                "⚪ WAIT\n\n"
                "I received the chart, but I could not reliably "
                "interpret the analysis response.\n\n"
                "Please send the screenshot again."
            )

            return

        # Get signal
        signal = str(result.get("signal", "WAIT")).upper()

        if signal not in ["BUY", "SELL", "WAIT"]:
            signal = "WAIT"

        icon = {
            "BUY": "🟢",
            "SELL": "🔴",
            "WAIT": "⚪",
        }.get(signal, "⚪")

        strength = result.get("strength", "WEAK")

        confidence = result.get("confidence", 0)

        summary = result.get(
            "summary",
            "No clear setup was identified.",
        )

        reasons = result.get("reasons", [])

        risk = result.get(
            "risk",
            "A screenshot cannot guarantee the next price movement.",
        )

        timeframe_visible = result.get(
            "timeframe_visible",
            False,
        )

        # Make sure reasons is a list
        if not isinstance(reasons, list):
            reasons = [str(reasons)]

        reason_text = "\n".join(
            f"• {reason}"
            for reason in reasons[:3]
        )

        if not reason_text:
            reason_text = "• No strong confirmation."

        # Create Telegram response
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
            parse_mode="HTML",
        )

        logger.info(
            "Analysis successfully sent to Telegram: %s",
            signal,
        )

    except Exception as error:

        # Log the complete error in Railway
        logger.exception(
            "❌ ERROR WHILE PROCESSING PHOTO: %s",
            error,
        )

        # Tell the user something went wrong
        try:
            await message.reply_text(
                "⚠️ I received your screenshot, but an error "
                "occurred while analyzing it.\n\n"
                "Please try sending the screenshot again."
            )

        except Exception:
            logger.exception(
                "Could not send error message to Telegram."
            )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Handle unexpected Telegram errors."""

    logger.exception(
        "Telegram bot error: %s",
        context.error,
    )


def main():
    """Start the Telegram bot."""

    logger.info("🚀 Starting Chart Signal Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    # Photo messages
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            analyze_photo,
        )
    )

    # Global error handler
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is starting Telegram polling...")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
