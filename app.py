import os
import json
import re
import requests
from datetime import datetime, time

import pytz
from bs4 import BeautifulSoup
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


def get_chennai_gold_silver_rate():
    url = "https://www.livechennai.com/gold_silverrate.asp"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.find_all("tr")

    gold_24k_1g = None
    gold_22k_1g = None
    silver_1g = None

    for row in rows:
        cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        clean = [re.sub(r"[₹,\s]", "", c) for c in cols]

        # Gold table row usually has: Date, 24K 1gm, 24K 8gm, 22K 1gm, 22K 8gm
        if len(clean) >= 5 and re.search(r"\d{1,2}/[A-Za-z]{3}/\d{4}", cols[0]):
            nums = []
            for c in clean[1:]:
                if c.isdigit():
                    nums.append(int(c))

            if len(nums) >= 4:
                gold_24k_1g = nums[0]
                gold_22k_1g = nums[2]
                break

    # Silver rate: find first row with date and silver-like smaller value
    for row in rows:
        cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        clean = [re.sub(r"[₹,\s]", "", c) for c in cols]

        if len(clean) >= 2 and re.search(r"\d{1,2}/[A-Za-z]{3}/\d{4}", cols[0]):
            nums = []
            for c in clean[1:]:
                if c.isdigit():
                    nums.append(int(c))

            # Silver 1gm is usually below 1000, gold is above 10000
            for n in nums:
                if 50 <= n <= 1000:
                    silver_1g = n
                    break

        if silver_1g:
            break

    if not gold_24k_1g or not gold_22k_1g:
        raise Exception("Could not read today's live gold rate from LiveChennai")

    if not silver_1g:
        silver_1g = 270

    return gold_24k_1g, gold_22k_1g, silver_1g


def get_uae_gold_rate_from_india(gold_24k_inr):
    """
    Approx AED/gm conversion from India retail rate.
    For exact UAE jewellery shop rate, separate UAE retail source is needed.
    """
    return gold_24k_inr / 22.7


def get_price_data():
    try:
        gold_24k_inr_g, gold_22k_inr_g, silver_inr_g = get_chennai_gold_silver_rate()
    except Exception:
        gold_24k_inr_g = 15524
        gold_22k_inr_g = 14230
        silver_inr_g = 270

    gold_24k_aed_g = get_uae_gold_rate_from_india(gold_24k_inr_g)
    gold_22k_aed_g = get_uae_gold_rate_from_india(gold_22k_inr_g)
    silver_aed_g = silver_inr_g / 22.7

    return {
        "gold_24k_inr_g": gold_24k_inr_g,
        "gold_22k_inr_g": gold_22k_inr_g,
        "silver_inr_g": silver_inr_g,
        "gold_24k_aed_g": gold_24k_aed_g,
        "gold_22k_aed_g": gold_22k_aed_g,
        "silver_aed_g": silver_aed_g,
        "gold_change": 0.0,
        "silver_change": 0.0,
    }


def market_view(asset, change):
    if change < -0.7:
        return "BUY in small quantity", "Price is lower today"
    elif change > 1.0:
        return "WAIT", "Price is higher today"
    else:
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

    gold_signal, gold_status = market_view("Gold", d["gold_change"])
    silver_signal, silver_status = market_view("Silver", d["silver_change"])

    now = datetime.now(UAE_TZ).strftime("%d-%b-%Y %I:%M %p UAE")

    return f"""
🌅 Gold & Silver Market Update
🕘 {now}

🥇 GOLD - Chennai Retail Rate
24K India: ₹{d['gold_24k_inr_g']:,}/gram
22K India: ₹{d['gold_22k_inr_g']:,}/gram

Approx UAE Conversion:
24K UAE: AED {d['gold_24k_aed_g']:.2f}/gram
22K UAE: AED {d['gold_22k_aed_g']:.2f}/gram

📊 Gold Status: {gold_status}
✅ Gold View: {gold_signal}

🥈 SILVER - Chennai Retail Rate
India: ₹{d['silver_inr_g']:,}/gram
Approx UAE: AED {d['silver_aed_g']:.2f}/gram

📊 Silver Status: {silver_status}
✅ Silver View: {silver_signal}

📌 Why market changes:
{why_market_text()}

Note: India rates are Chennai retail rates. UAE values are approximate conversion only.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    users.add(update.effective_chat.id)
    save_users(users)

    await update.message.reply_text(
        "Welcome! I provide gold & silver price, Chennai India rate, approximate AED value, market status and daily 9 AM UAE alert.\n\n"
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
        await update.message.reply_text(build_report())
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