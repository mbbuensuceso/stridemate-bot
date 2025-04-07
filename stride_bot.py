import os
import json
import threading
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# ====== CONFIGURATION ======
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DATA_FILE = "user_scores.json"
CHALLENGE_DURATION_DAYS = 0
CHALLENGE_END_DATE = None

# ====== DATA STRUCTURES ======
user_scores = {}  # Format: {"chat_id:user_id": {"name": str, "steps": int}}

def load_data():
    global user_scores
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            user_scores = json.load(f)
    else:
        user_scores = {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ====== BOT COMMANDS ======
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    update.message.reply_text(f"👋 Hey, {user.first_name}! Welcome to StrideMate 🐧\n\n"
                               "Use /logsteps <number> to log your steps.\n"
                               "Type /help to see available commands.")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📘 *StrideMate Commands:*\n\n"
        "📌 /start – Welcome message\n"
        "📌 /logsteps <number> – Log your steps\n"
        "📌 /leaderboard – View rankings \n"
        "📌 /newchallenge <days> – Propose a step challenge\n"
        "📌 /resetsteps – Reset your personal step count\n"
        "📌 /help – Show this message\n\n"
        "Stay active and keep moving! 🚀",
        parse_mode="Markdown"
    )

def log_steps(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)

    if update.effective_chat.type == "private":
        update.message.reply_text("⚠️ You can only log steps in a group or channel.")
        return

    user = update.effective_user
    user_key = f"{chat_id}:{user.id}"

    try:
        steps = int(context.args[0])
        if user_key not in user_scores:
            user_scores[user_key] = {"name": user.first_name, "steps": 0}

        user_scores[user_key]["steps"] += steps
        save_data(user_scores)

        update.message.reply_text(
            f"✅  {user.first_name} logged in {steps} steps! "
            f"They now have a total {user_scores[user_key]['steps']} steps."
        )
    except (IndexError, ValueError):
        update.message.reply_text("❗ Usage: /logsteps <number>")

def show_leaderboard(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    group_scores = {
        k: v for k, v in user_scores.items() if k.startswith(f"{chat_id}:")
    }

    if not group_scores:
        update.message.reply_text("🏁 No steps logged yet in this group!")
        return

    sorted_users = sorted(group_scores.items(), key=lambda x: x[1]["steps"], reverse=True)
    leaderboard = "\n".join([
        f"{i+1}. {data['name']}: {data['steps']} steps"
        for i, (uid, data) in enumerate(sorted_users)
    ])
    update.message.reply_text(f"📊 Leaderboard:\n{leaderboard}")

def new_challenge(update: Update, context: CallbackContext):
    global CHALLENGE_DURATION_DAYS
    try:
        CHALLENGE_DURATION_DAYS = int(context.args[0])
        update.message.reply_text(f"🔔 Proposed a new {CHALLENGE_DURATION_DAYS}-day challenge! Use /confirm to start.")
    except (IndexError, ValueError):
        update.message.reply_text("❗ Usage: /newchallenge <days>")

def confirm_challenge(update: Update, context: CallbackContext):
    global CHALLENGE_END_DATE

    if CHALLENGE_DURATION_DAYS <= 0:
        update.message.reply_text("⚠️ Set challenge duration first using /newchallenge <days>.")
        return

    CHALLENGE_END_DATE = datetime.now() + timedelta(days=CHALLENGE_DURATION_DAYS)
    update.message.reply_text(f"✅ Challenge started! Ends on {CHALLENGE_END_DATE.strftime('%Y-%m-%d %H:%M')}.")

def reset_steps(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    user_key = f"{chat_id}:{user.id}"

    if user_key in user_scores:
        user_scores[user_key]["steps"] = 0
        save_data(user_scores)
        update.message.reply_text("🔄 Your steps have been reset to 0 in this group.")
    else:
        update.message.reply_text("⚠️ No steps found to reset.")

# ====== DAILY SCHEDULING ======
def send_nightly_reminder(bot):
    for chat_id in set(k.split(":")[0] for k in user_scores):
        bot.send_message(chat_id=int(chat_id), text="🌙 Don’t forget to log your steps before the day ends!")

def send_leaderboard_update(bot):
    for chat_id in set(k.split(":")[0] for k in user_scores):
        group_scores = {
            k: v for k, v in user_scores.items() if k.startswith(f"{chat_id}:")
        }
        if group_scores:
            sorted_users = sorted(group_scores.items(), key=lambda x: x[1]["steps"], reverse=True)
            leaderboard = "\n".join([
                f"{i+1}. {data['name']}: {data['steps']} steps"
                for i, (uid, data) in enumerate(sorted_users)
            ])
            bot.send_message(chat_id=int(chat_id), text=f"⭐ Daily Leaderboard:\n{leaderboard}")

def daily_scheduler(bot):
    now = datetime.now()
    last_reminder_date = now.date() if now.hour >= 21 else None
    last_leaderboard_date = now.date() if now.hour >= 18 else None

    while True:
        now = datetime.now()

        if now.hour == 21 and (last_reminder_date != now.date()):
            send_nightly_reminder(bot)
            last_reminder_date = now.date()

        if now.hour == 18 and (last_leaderboard_date != now.date()):
            send_leaderboard_update(bot)
            last_leaderboard_date = now.date()

        time.sleep(30)


# ====== CHALLENGE WATCHER ======
def challenge_watcher(bot):
    global CHALLENGE_END_DATE
    while True:
        if CHALLENGE_END_DATE and datetime.now() >= CHALLENGE_END_DATE:
            for chat_id in set(k.split(":")[0] for k in user_scores):
                group_scores = {
                    k: v for k, v in user_scores.items() if k.startswith(f"{chat_id}:")
                }
                if group_scores:
                    winner = max(group_scores.items(), key=lambda x: x[1]["steps"], default=None)
                    if winner:
                        name = winner[1]["name"]
                        steps = winner[1]["steps"]
                        bot.send_message(
                            chat_id=int(chat_id),
                            text=f"🏁 *Challenge Over!*\n🥇 The winner is *{name}* with *{steps}* steps!",
                            parse_mode="Markdown"
                        )
                    else:
                        bot.send_message(chat_id=int(chat_id), text="The challenge has ended, but no steps were logged. 😭 You'll do better neext time!")
            CHALLENGE_END_DATE = None
            save_data(user_scores)
        time.sleep(3600)

# ====== MAIN FUNCTION ======
def main():
    load_data()
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("logsteps", log_steps))
    dispatcher.add_handler(CommandHandler("leaderboard", show_leaderboard))
    dispatcher.add_handler(CommandHandler("newchallenge", new_challenge))
    dispatcher.add_handler(CommandHandler("confirm", confirm_challenge))
    dispatcher.add_handler(CommandHandler("resetsteps", reset_steps))

    threading.Thread(target=daily_scheduler, args=(updater.bot,), daemon=True).start()
    threading.Thread(target=challenge_watcher, args=(updater.bot,), daemon=True).start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
