# Screenshot Chart Signal Bot

## What it does
Send a chart screenshot to the Telegram bot. The bot analyzes only the visible chart information and returns:

- BUY
- SELL
- WAIT

The bot is intentionally conservative and should use WAIT when the screenshot is unclear or confirmations conflict.

## Setup

### 1. Create a Telegram bot
Open Telegram and search for **BotFather**.

Use `/newbot`, follow the instructions, and copy the bot token.

### 2. Get an OpenAI API key
Create an API key in your OpenAI Platform account.

### 3. Create `.env`
Copy `.env.example` to `.env`, then paste your two keys.

### 4. Install Python packages
```bash
pip install -r requirements.txt
```

### 5. Start the bot
```bash
python bot.py
```

## How to use
1. Set your chart to the timeframe you want to analyze.
2. Take a clear screenshot with enough recent candles visible.
3. Send it to the Telegram bot.
4. Read the BUY / SELL / WAIT response.

## Important
A screenshot cannot reveal the future. The confidence value is an experimental score based on the visible setup, not a guarantee or proven win rate. Test the system extensively before risking money.
