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

Your job is to provide a cautious trading setup assessment.

Choose exactly one signal:
BUY, SELL, or WAIT.

Also determine:

1. suggested_timeframe
2. entry_action

The entry_action must be exactly one of:
ENTER
WAIT_FOR_CONFIRMATION
NO_TRADE

IMPORTANT:

- Never claim certainty.
- Never claim guaranteed profit.
- Never claim a guaranteed win rate.
- Do not invent unseen market information.
- Do not blindly follow indicator arrows.
- Prefer WAIT when the chart is unclear.
- Prefer WAIT_FOR_CONFIRMATION when the direction looks possible
  but a confirming candle or price reaction is still needed.
- Use NO_TRADE when the screenshot is too unclear or contradictory.
- Consider visible price structure, recent candles, momentum,
  rejection wicks, support/resistance, and visible indicators.
- Consider whether price is close to a support or resistance area.
- If the screenshot does not clearly show a timeframe, say so.
- The suggested timeframe should be based ONLY on what can reasonably
  be inferred from the visible chart.
- Do not assume that every trade should be 10 minutes.

Possible suggested timeframes include:
1 minute
2 minutes
5 minutes
10 minutes
15 minutes
30 minutes
1 hour
Not clear

Return ONLY valid JSON in exactly this format:

{
  "signal": "BUY",
  "strength": "MODERATE",
  "confidence": 65,
  "suggested_timeframe": "5 minutes",
  "entry_action": "WAIT_FOR_CONFIRMATION",
  "confirmation": "Wait for a bullish candle to close above the visible resistance.",
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

suggested_timeframe must be one of:
"1 minute",
"2 minutes",
"5 minutes",
"10 minutes",
"15 minutes",
"30 minutes",
"1 hour",
"Not clear".

entry_action must be one of:
"ENTER",
"WAIT_FOR_CONFIRMATION",
"NO_TRADE".

timeframe_visible must be true or false.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    logger.info("START command received")

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear chart screenshot.\n\n"
        "I will provide:\n"
        "🟢 BUY / 🔴 SELL / ⚪ WAIT\n"
        "⏱️ Suggested timeframe\n"
        "⏳ Whether to wait for confirmation\n"
        "📈 Experimental confidence\n"
        "🔎 Visible reasons"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Open your trading chart.\n"
        "2. Make recent candles visible.\n"
        "3. Make the timeframe visible if possible.\n"
        "4. Take a clear screenshot.\n"
        "5. Send it here.\n\n"
        "The bot will assess whether confirmation is needed."
    )


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

        logger.info("Sending image to Gemini...")

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                ),
                SYSTEM_PROMPT,
                "Analyze this chart screenshot conservatively."
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        logger.info("Gemini response received")

        text = response.text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "")
            text = text.replace("```", "")
            text = text.strip()

        result = json.loads(text)

        signal = str(
            result.get("signal", "WAIT")
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

        timeframe = result.get(
            "suggested_timeframe",
            "Not clear"
        )

        entry_action = result.get(
            "entry_action",
            "NO_TRADE"
        )

        confirmation = result.get(
            "confirmation",
            "No confirmation condition provided."
        )

        summary = result.get(
            "summary",
            "No clear setup."
        )

        reasons = result.get(
            "reasons",
            []
        )

        if not isinstance(reasons, list):
            reasons = [str(reasons)]

        reason_text = "\n".join(
            f"• {reason}"
            for reason in reasons[:3]
        )

        if not reason_text:
            reason_text = "• No strong confirmation."

        risk = result.get(
            "risk",
            "A screenshot cannot guarantee the next price movement."
        )

        if entry_action == "ENTER":
            entry_text = "✅ ENTER"
        elif entry_action == "WAIT_FOR_CONFIRMATION":
            entry_text = "⏳ WAIT FOR CONFIRMATION"
        else:
            entry_text = "🚫 NO TRADE"

        reply = (
            "📊 <b>CHART ANALYSIS</b>\n\n"

            f"{icon} <b>SIGNAL: {signal}</b>\n"
            f"💪 Strength: <b>{strength}</b>\n"
            f"📈 Experimental confidence: "
            f"<b>{confidence}%</b>\n\n"

            f"⏱️ <b>Suggested timeframe:</b>\n"
            f"{timeframe}\n\n"

            f"<b>Entry decision:</b>\n"
            f"{entry_text}\n\n"

            f"<b>Confirmation:</b>\n"
            f"{confirmation}\n\n"

            f"<b>Summary:</b>\n"
            f"{summary}\n\n"

            f"<b>Visible reasons:</b>\n"
            f"{reason_text}\n\n"

            f"⚠️ <b>Risk:</b> {risk}\n"
        )

        if not result.get(
            "timeframe_visible",
            False
        ):
            reply += (
                "\n⏱️ The chart timeframe was not clearly "
                "visible in the screenshot."
            )

        reply += (
            "\n\n<i>Experimental chart analysis only. "
            "No prediction or profit is guaranteed.</i>"
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


async def diagnostic_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.info("DIAGNOSTIC MESSAGE RECEIVED")

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

    logger.info(
        "Bot handlers registered successfully."
    )

    logger.info(
        "Starting Telegram polling..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
