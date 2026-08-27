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
# ANALYSIS INSTRUCTIONS
# ============================================================

SYSTEM_PROMPT = """
You are a screenshot-based candlestick chart analysis assistant.

The user sends a screenshot of a Pocket Option-style trading chart.

Analyze ONLY information that is clearly visible in the screenshot.

Your goal is to identify the strongest short-term setup while remaining
honest about uncertainty.

Do NOT force a trade when the chart genuinely has no usable setup.

However, do NOT automatically choose WAIT simply because there is some
uncertainty.

If the visible evidence reasonably favors one direction, choose BUY or
SELL and use WAIT_FOR_CONFIRMATION when additional confirmation is needed.

============================================================
WHAT TO ANALYZE
============================================================

Look at:

1. Recent candle direction and momentum.
2. Higher highs / higher lows.
3. Lower highs / lower lows.
4. Support and resistance.
5. Rejection wicks.
6. Breakouts and failed breakouts.
7. Pullbacks.
8. Visible moving averages.
9. Visible trend lines or channels.
10. Visible indicators.
11. Whether several visible signals agree.
12. Whether price is approaching an important support or resistance area.

Do not blindly follow indicator arrows.

============================================================
ENTRY DECISION
============================================================

Choose exactly ONE:

ENTER
WAIT_FOR_CONFIRMATION
NO_TRADE

Use ENTER only when the visible setup has reasonably strong confirmation.

Use WAIT_FOR_CONFIRMATION when BUY or SELL has a reasonable directional
edge but one more visible confirmation is preferable.

Use NO_TRADE only when the chart is genuinely unclear, highly sideways,
contradictory, or lacks enough visible information.

============================================================
SIGNAL
============================================================

Choose exactly ONE:

BUY
SELL
WAIT

Important:

If the chart has a reasonable bullish setup, choose BUY.

If the chart has a reasonable bearish setup, choose SELL.

Use WAIT mainly when there is no meaningful directional advantage.

============================================================
TIMEFRAME
============================================================

Suggest the most appropriate visible timeframe.

Possible values:

"1 minute"
"2 minutes"
"5 minutes"
"10 minutes"
"15 minutes"
"30 minutes"
"1 hour"
"Not clear"

Do NOT assume every trade must be 10 minutes.

If the chart timeframe is clearly visible, use it as an important factor.

============================================================
CONFIDENCE
============================================================

Confidence is an experimental assessment of how strongly the visible
evidence supports the selected direction.

Do not treat confidence as a guaranteed probability of winning.

Use:

0-39 = weak evidence
40-59 = moderate evidence
60-79 = reasonably strong evidence
80-100 = very strong visible agreement

Do not give 80+ unless multiple visible factors clearly agree.

============================================================
IMPORTANT
============================================================

Never claim:

- guaranteed profit
- guaranteed win
- guaranteed accuracy
- certainty about the next candle
- guaranteed win rate

A screenshot cannot reveal the future.

If price is very close to major support or resistance, mention that risk.

============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

Use exactly this structure:

{
  "signal": "BUY",
  "strength": "MODERATE",
  "confidence": 65,
  "suggested_timeframe": "5 minutes",
  "entry_action": "WAIT_FOR_CONFIRMATION",
  "confirmation": "Wait for a bullish candle to close above the visible resistance.",
  "summary": "The visible structure favors the upside but confirmation is still useful.",
  "reasons": [
    "Recent candles show bullish momentum.",
    "Price is forming higher lows.",
    "Visible support is holding."
  ],
  "risk": "Price is approaching visible resistance, so a rejection remains possible.",
  "timeframe_visible": true
}

The values must follow these rules:

signal:
BUY, SELL, or WAIT

strength:
STRONG, MODERATE, or WEAK

confidence:
integer from 0 to 100

suggested_timeframe:
1 minute
2 minutes
5 minutes
10 minutes
15 minutes
30 minutes
1 hour
Not clear

entry_action:
ENTER
WAIT_FOR_CONFIRMATION
NO_TRADE

timeframe_visible:
true or false

reasons:
maximum 3 short reasons
"""


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    logger.info("START command received")

    await update.message.reply_text(
        "📊 Chart Signal Bot is ready.\n\n"
        "Send me a clear chart screenshot.\n\n"
        "I will provide:\n"
        "🟢 BUY / 🔴 SELL / ⚪ WAIT\n"
        "⏱️ Suggested timeframe\n"
        "🎯 Entry decision\n"
        "⏳ Confirmation requirement\n"
        "📈 Experimental confidence\n"
        "🔎 Visible reasons"
    )


# ============================================================
# HELP
# ============================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 How to use:\n\n"
        "1. Open your chart.\n"
        "2. Make recent candles visible.\n"
        "3. Make the timeframe visible.\n"
        "4. Take a clear screenshot.\n"
        "5. Send it here.\n\n"
        "The bot will decide whether the setup is:\n"
        "✅ ENTER\n"
        "⏳ WAIT FOR CONFIRMATION\n"
        "🚫 NO TRADE"
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
                "Analyze this chart screenshot."
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        logger.info(
            "Gemini response received"
        )

        text = response.text.strip()

        # Remove markdown fences if Gemini adds them
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
        # GET RESULTS
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

        strength = str(
            result.get(
                "strength",
                "WEAK"
            )
        ).upper()

        confidence = result.get(
            "confidence",
            0
        )

        timeframe = result.get(
            "suggested_timeframe",
            "Not clear"
        )

        entry_action = str(
            result.get(
                "entry_action",
                "NO_TRADE"
            )
        ).upper()

        confirmation = result.get(
            "confirmation",
            "No confirmation condition was provided."
        )

        summary = result.get(
            "summary",
            "No clear setup."
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

        # ====================================================
        # VALIDATE ENTRY
        # ====================================================

        if entry_action not in [
            "ENTER",
            "WAIT_FOR_CONFIRMATION",
            "NO_TRADE"
        ]:
            entry_action = "NO_TRADE"

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

        if entry_action == "ENTER":
            entry_text = "✅ ENTER"

        elif entry_action == "WAIT_FOR_CONFIRMATION":
            entry_text = "⏳ WAIT FOR CONFIRMATION"

        else:
            entry_text = "🚫 NO TRADE"

        # ====================================================
        # REASONS
        # ====================================================

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
                "• No strong visible confirmation."
            )

        # ====================================================
        # TELEGRAM RESPONSE
        # ====================================================

        reply = (
            "📊 <b>CHART ANALYSIS</b>\n\n"

            f"{signal_icon} "
            f"<b>SIGNAL: {signal}</b>\n"

            f"💪 Strength: "
            f"<b>{strength}</b>\n"

            f"📈 Experimental confidence: "
            f"<b>{confidence}%</b>\n\n"

            f"⏱️ <b>Suggested timeframe:</b>\n"
            f"{timeframe}\n\n"

            f"🎯 <b>Entry decision:</b>\n"
            f"{entry_text}\n\n"

            f"⏳ <b>Confirmation:</b>\n"
            f"{confirmation}\n\n"

            f"<b>Summary:</b>\n"
            f"{summary}\n\n"

            f"<b>Visible reasons:</b>\n"
            f"{reason_text}\n\n"

            f"⚠️ <b>Risk:</b>\n"
            f"{risk}\n"
        )

        if not timeframe_visible:

            reply += (
                "\n⏱️ The timeframe was not clearly "
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


# ============================================================
# DIAGNOSTIC MESSAGE
# ============================================================

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


if __name__ == "__main__":
    main()
