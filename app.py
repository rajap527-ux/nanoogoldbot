import os
import json
import asyncio
from datetime import datetime, time

import pytz
import yfinance as yf
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN").strip()
USDAED = 3.6725
OZ_TO_GRAM = 31.1035
USERS_FILE = "users.json"
UAE_TZ = pytz.timezone("Asia/Dubai")


def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)


def get_price_data():
    gold = yf.Ticker("GC=F").history(period="35d")
    silver = yf.Ticker("SI=F").history(period="35d")
    usdinr = yf.Ticker("INR=X").history(period="5d")

    if gold.empty or silver.empty or usdinr.empty:
        return None

    usd_inr = float(usdinr["Close"].iloc[-1])

    gold_today = float(gold["Close"].iloc[-1])
    gold_yday = float(gold["Close"].iloc[-2])
    silver_today = float(silver["Close"].iloc[-1])
    silver_yday = float(silver["Close"].iloc[-2])

    gold_24k_aed_g = gold_today * USDAED / OZ_TO_GRAM
    gold_22k_aed_g = gold_24k_aed_g * 22 / 24
    gold_24k_inr_g = gold_today * usd_inr / OZ_TO_GRAM
    gold_22k_inr_g = gold_24k_inr_g * 22 / 24

    silver_aed_g = silver_today * USDAED / OZ_TO_GRAM
    silver_inr_g = silver_today * usd_inr / OZ_TO_GRAM

    gold_change = ((gold_today - gold_yday) / gold_yday) * 100
    silver_change = ((silver_today - silver_yday) / silver_yday) * 100

    gold_30_avg = float(gold["Close"].tail(30).mean())
    silver_30_avg = float(silver["Close"].tail(30).mean())

    return {
        "usd_inr": usd_inr,
        "gold_usd_oz": gold_today,
        "silver_usd_oz": silver_today,
        "gold_22k_aed_g": gold_22k_aed_g,
        "gold_24k_aed_g": gold_24k_aed_g,
        "gold_22k_inr_g": gold_22k_inr_g,
        "gold_24k_inr_g": gold_24k_inr_g,
        "silver_aed_g": silver_aed_g,
        "silver_inr_g": silver_inr_g,
        "gold_change": gold_change,
        "silver_change": silver_change,
        "gold_30_avg": gold_30_avg,
        "silver_30_avg": silver_30_avg,
    }


def market_view(asset, price, change, avg30):
    if change < -0.8 and price <= avg30:
        signal = "BUY in small quantity"
        status = "Price is weak compared with recent trend"
    elif change > 1.0 and price > avg30:
        signal = "WAIT"
        status = "Price is strong and near higher level"
    else:
        signal = "HOLD / Buy slowly"
        status = "Market is neutral"

    reason = (
        f"{asset} changed {change:.2f}% from previous close. "
        f"When USD weakens, Fed rate-cut expectation rises, inflation fear increases, "
        f"or geopolitical tension increases, precious metals usually move up. "
        f"When USD strengthens or bond yields rise, gold/silver may fall."
    )

    return signal, status, reason


def build_report():
    d = get_price_data()
    if not d:
        return "Sorry, price data is not available now. Try again later."

    gold_signal, gold_status, gold_reason = market_view(
        "Gold", d["gold_usd_oz"], d["gold_change"], d["gold_30_avg"]
    )
    silver_signal, silver_status, silver_reason = market_view(
        "Silver", d["silver_usd_oz"], d["silver_change"], d["silver_30_avg"]
    )

    now = datetime.now(UAE_TZ).strftime("%d-%b-%Y %I:%M %p UAE")

    return f"""
🌅 Gold & Silver Market Update
🕘 {now}

🥇 GOLD
24K UAE: AED {d['gold_24k_aed_g']:.2f}/gram
22K UAE: AED {d['gold_22k_aed_g']:.2f}/gram
24K India: ₹{d['gold_24k_inr_g']:.0f}/gram
22K India: ₹{d['gold_22k_inr_g']:.0f}/gram
Change: {d['gold_change']:.2f}%

📊 Gold Status: {gold_status}
✅ Gold View: {gold_signal}
Why: {gold_reason}

🥈 SILVER
UAE: AED {d['silver_aed_g']:.2f}/gram
India: ₹{d['silver_inr_g']:.0f}/gram
Change: {d['silver_change']:.2f}%

📊 Silver Status: {silver_status}
✅ Silver View: {silver_signal}
Why: {silver_reason}

💱 USD/INR: {d['usd_inr']:.2f}

Note: Educational market view only, not guaranteed investment advice.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_chat.id)
    save_users(users)

    await update.message.reply_text(
        "Welcome! I will give gold & silver price, market status, buy/wait view, and daily 9 AM UAE alert.\n\n"
        "Commands:\n"
        "/price - Today price\n"
        "/gold - Gold view\n"
        "/silver - Silver view\n"
        "/why - Why market is changing\n"
        "/alert_on - Enable daily alert\n"
        "/alert_off - Disable alert\n\n"
        "You can also ask: Should I buy gold today?"
    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_report())


async def gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = build_report()
    await update.message.reply_text(report.split("🥈 SILVER")[0])


async def silver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = build_report()
    await update.message.reply_text("🥈 SILVER" + report.split("🥈 SILVER")[1])


async def why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Gold & silver usually change because of:\n\n"
        "1. US dollar strength or weakness\n"
        "2. US Fed interest rate expectation\n"
        "3. Inflation data\n"
        "4. War or geopolitical tension\n"
        "5. Central bank gold buying\n"
        "6. INR movement against USD\n"
        "7. Jewellery demand in India/UAE\n\n"
        "Weak USD or rate-cut expectation usually supports gold/silver. Strong USD or high yields usually pressures them."
    )


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

    if "buy" in text or "invest" in text or "should" in text:
        await update.message.reply_text(build_report())
    elif "why" in text or "increase" in text or "decrease" in text or "market" in text:
        await why(update, context)
    elif "gold" in text or "silver" in text or "price" in text:
        await update.message.reply_text(build_report())
    else:
        await update.message.reply_text(
            "Ask me like:\n"
            "Should I buy gold today?\n"
            "Why gold price increased?\n"
            "Silver price today?\n"
            "Gold market status?"
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