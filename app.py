import os
import json
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, time

import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

USERS_FILE = "users.json"
UAE_TZ = pytz.timezone("Asia/Dubai")
USDAED = 3.6725
OZ_TO_GRAM = 31.1035


def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)


def get_stooq_price(symbol):
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = requests.get(url, timeout=15)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text))
    if df.empty or "Close" not in df.columns:
        raise Exception("No price data")

    latest = float(df["Close"].iloc[-1])
    previous = float(df["Close"].iloc[-2])
    avg30 = float(df["Close"].tail(30).mean())

    change = ((latest - previous) / previous) * 100
    return latest, previous, avg30, change


def get_usdinr():
    try:
        latest, _, _, _ = get_stooq_price("usdinr")
        return latest
    except Exception:
        return 83.50


def get_price_data():
    try:
        gold_usd, _, gold_avg30, gold_change = get_stooq_price("xauusd")
    except Exception:
        gold_usd = 2335.50
        gold_avg30 = 2320.00
        gold_change = 0.0

    try:
        silver_usd, _, silver_avg30, silver_change = get_stooq_price("xagusd")
    except Exception:
        silver_usd = 27.85
        silver_avg30 = 27.50
        silver_change = 0.0

    usd_inr = get_usdinr()

    gold_24k_aed_g = gold_usd * USDAED / OZ_TO_GRAM
    gold_22k_aed_g = gold_24k_aed_g * 22 / 24

    gold_24k_inr_g = gold_usd * usd_inr / OZ_TO_GRAM
    gold_22k_inr_g = gold_24k_inr_g * 22 / 24

    silver_aed_g = silver_usd * USDAED / OZ_TO_GRAM
    silver_inr_g = silver_usd * usd_inr / OZ_TO_GRAM

    return {
        "gold_usd": gold_usd,
        "silver_usd": silver_usd,
        "gold_avg30": gold_avg30,
        "silver_avg30": silver_avg30,
        "gold_change": gold_change,
        "silver_change": silver_change,
        "usd_inr": usd_inr,
        "gold_24k_aed_g": gold_24k_aed_g,
        "gold_22k_aed_g": gold_22k_aed_g,
        "gold_24k_inr_g": gold_24k_inr_g,
        "gold_22k_inr_g": gold_22k_inr_g,
        "silver_aed_g": silver_aed_g,
        "silver_inr_g": silver_inr_g,
    }


def market_view(asset, price, change, avg30):
    if change < -0.7 and price <= avg30:
        return "BUY in small quantity", "Price is weak compared with recent average"

    if change > 1.0 and price > avg30:
        return "WAIT", "Price is strong and may be expensive today"

    return "HOLD / Buy slowly", "Market is neutral"


def why_market_text():
    return (
        "Gold & silver usually change because of:\n\n"
        "1. US dollar strength or weakness\n"
        "2. US Fed interest rate expectation\n"
        "3. Inflation data\n"
        "4. War or geopolitical tension\n"
        "5. Central bank gold buying\n"
        "6. INR movement against USD\n"
        "7. Jewellery demand in India/UAE\n\n"
        "Weak USD or rate-cut expectation usually supports gold/silver.\n"
        "Strong USD or high bond yields usually pressures them."
    )


def build_report():
    d = get_price_data()

    gold_signal, gold_status = market_view(
        "Gold", d["gold_usd"], d["gold_change"], d["gold_avg30"]
    )
    silver_signal, silver_status = market_view(
        "Silver", d["silver_usd"], d["silver_change"], d["silver_avg30"]
    )

    now = datetime.now(UAE_TZ).strftime("%d-%b-%Y %I:%M %p UAE")

    return f"""
🌅 Gold & Silver Market Update
🕘 {now}

🥇 GOLD
Spot: ${d['gold_usd']:.2f}/oz
24K UAE: AED {d['gold_24k_aed_g']:.2f}/gram
22K UAE: AED {d['gold_22k_aed_g']:.2f}/gram
24K India: ₹{d['gold_24k_inr_g']:.0f}/gram
22K India: ₹{d['gold_22k_inr_g']:.0f}/gram
Change: {d['gold_change']:.2f}%

📊 Gold Status: {gold_status}
✅ Gold View: {gold_signal}

🥈 SILVER
Spot: ${d['silver_usd']:.2f}/oz
UAE: AED {d['silver_aed_g']:.2f}/gram
India: ₹{d['silver_inr_g']:.0f}/gram
Change: {d['silver_change']:.2f}%

📊 Silver Status: {silver_status}
✅ Silver View: {silver_signal}

💱 USD/INR: {d['usd_inr']:.2f}

📌 Why market changes:
Weak USD, Fed rate-cut expectation, inflation fear, war tension and central bank buying usually support gold/silver. Strong USD and high bond yields usually reduce demand.

Note: Educational market view only. Not guaranteed investment advice.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_chat.id)
    save_users(users)

    await update.message.reply_text(
        "Welcome! I provide gold & silver price, AED/INR value, market status, buy/wait view and daily 9 AM UAE alert.\n\n"
        "Commands:\n"
        "/price - Today gold & silver price\n"
        "/gold - Gold view\n"
        "/silver - Silver view\n"
        "/why - Why market is changing\n"
        "/alert_on - Enable daily alert\n"
        "/alert_off - Disable alert\n\n"
        "You can also ask: Should I buy gold today?"
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest gold & silver price...")
    try:
        report = build_report()
        await update.message.reply_text(report)
    except Exception as e:
        await update.message.reply_text(f"Price fetch error: {e}")


async def gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching gold price...")
    try:
        report = build_report()
        await update.message.reply_text(report.split("🥈 SILVER")[0])
    except Exception as e:
        await update.message.reply_text(f"Gold price error: {e}")


async def silver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching silver price...")
    try:
        report = build_report()
        await update.message.reply_text("🥈 SILVER" + report.split("🥈 SILVER")[1])
    except Exception as e:
        await update.message.reply_text(f"Silver price error: {e}")


async def why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(why_market_text())


async def alert_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_chat.id)
    save_users(users)
    await update.message.reply_text("Daily 9 AM UAE alert enabled.")


async def alert_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.discard(update.effective_chat.id)
    save_users(users)
    await update.message.reply_text("Daily alert disabled.")


async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if any(word in text for word in ["buy", "invest", "should", "price", "gold", "silver"]):
        await price(update, context)
    elif any(word in text for word in ["why", "increase", "decrease", "market"]):
        await why(update, context)
    else:
        await update.message.reply_text(
            "Ask me like:\n"
            "Should I buy gold today?\n"
            "Gold price today?\n"
            "Silver price today?\n"
            "Why gold price increased?"
        )


async def daily_alert(context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    report = build_report()

    for chat_id in users:
        try:
            await context.bot.send_message(chat_id=chat_id, text=report)
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing. Add BOT_TOKEN in Railway Variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("gold", gold))
    app.add_handler(CommandHandler("silver", silver))
    app.add_handler(CommandHandler("why", why))
    app.add_handler(CommandHandler("alert_on", alert_on))
    app.add_handler(CommandHandler("alert_off", alert_off))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query))

    app.job_queue.run_daily(
        daily_alert,
        time=time(hour=9, minute=0, tzinfo=UAE_TZ),
        name="daily_gold_silver_alert",
    )

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()