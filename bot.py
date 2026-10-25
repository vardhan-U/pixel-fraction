import io
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    ADMIN_USER_ID,
    PORT,
    WEBHOOK_URL,
    SECRET_TOKEN,
    PASS_THRESHOLD,
    BONUS_THRESHOLD,
    SIMILARITY_THRESHOLD,
)
from color_engine import analyze_pixel_fraction, compute_dhash, compute_similarity
from quest_manager import QuestManager
from database import Database

# Patch Tornado WebhookAppClass so Render health checks at GET / return 200 OK
try:
    import tornado.web
    import tornado.routing
    from telegram.ext._updater import WebhookAppClass

    class HealthCheckHandler(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "application/json")
            self.write({"status": "healthy", "service": "Pixel Fraction Telegram Bot"})

    _orig_webhook_init = WebhookAppClass.__init__

    def _patched_webhook_init(self, webhook_path, bot, update_queue, secret_token=None):
        _orig_webhook_init(self, webhook_path, bot, update_queue, secret_token)
        self.wildcard_router.rules.append(
            tornado.web.Rule(tornado.routing.PathMatches(r"/$"), HealthCheckHandler)
        )

    WebhookAppClass.__init__ = _patched_webhook_init
except Exception as e:
    pass

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

quest_mgr = QuestManager()
db = Database()


def is_admin(user_id: int) -> bool:
    # Check environment variable or runtime registered admin
    effective_admin = db.state.get("admin_id") or ADMIN_USER_ID
    if not effective_admin:
        return True  # If no admin configured, allow demo control
    return str(user_id) == str(effective_admin)


async def setadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows the presenter to claim admin controls for the session."""
    user = update.effective_user
    db.state["admin_id"] = str(user.id)
    db._save()
    await update.message.reply_text(
        f"👑 **Admin privileges granted to {user.first_name}** (`{user.id}`)!\n"
        "You can now use `/forcequest` to override quests during the live presentation.",
        parse_mode="Markdown"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and explains the rules."""
    user = update.effective_user
    welcome_text = (
        f"👋 Welcome {user.first_name} to **Pixel Fraction**!\n\n"
        "🎯 **Daily Color Quest Bot**\n"
        "Every day brings a brand new color quest with an inspiring Unsplash photo.\n\n"
        "📸 **How to Play:**\n"
        "1. Check today's quest with /quest\n"
        "2. Find and photograph matching objects around you\n"
        "3. Send your photo here or in your group!\n\n"
        "✨ **Scoring:**\n"
        f"• Pass: ≥ {PASS_THRESHOLD}% color fraction (+10 pts)\n"
        f"• Bonus: ≥ {BONUS_THRESHOLD}% color fraction (+25 pts)\n"
        "• Group members can vote on submissions!\n"
        "• Keep up daily streaks for the leaderboard 🏆"
    )
    keyboard = [
        [
            InlineKeyboardButton("🎯 Today's Quest", callback_data="cmd_quest"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="cmd_leaderboard"),
        ],
        [
            InlineKeyboardButton("🆔 My ID", callback_data="cmd_myid"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Pixel Fraction Commands:**\n\n"
        "• /quest — View today's color quest & Unsplash inspiration\n"
        "• /leaderboard — View current group leaderboard & streaks\n"
        "• /myid — View your Telegram numeric ID\n"
        "• /forcequest — (Admin) Force trigger a new quest for demo\n"
        "• /help — Show this help message\n\n"
        "💡 *Tip:* In group chats, simply post a photo and the bot will score it automatically!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_status = "👑 (Admin)" if is_admin(user_id) else ""
    await update.message.reply_text(
        f"🆔 Your Telegram User ID is: `{user_id}` {admin_status}",
        parse_mode="Markdown"
    )


async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays today's active color quest with photo and credits."""
    quest = quest_mgr.get_todays_quest()
    caption = (
        f"🎯 **TODAY'S COLOR QUEST**\n\n"
        f"Target Color: **{quest['color_name']}** {quest['emoji']}\n"
        f"Requirement: At least **{PASS_THRESHOLD}%** of your photo must match!\n\n"
        f"💬 *{quest['description']}*\n\n"
        f"📷 Reference photo by [{quest['photographer']}]({quest['photographer_url']}) on [Unsplash](https://unsplash.com/?utm_source=pixel_fraction&utm_medium=referral)\n"
        f"📅 Date: {quest['date']}"
    )

    if update.callback_query:
        msg = update.callback_query.message
        await msg.reply_photo(
            photo=quest["photo_url"],
            caption=caption,
            parse_mode="Markdown"
        )
        await update.callback_query.answer()
    else:
        await update.message.reply_photo(
            photo=quest["photo_url"],
            caption=caption,
            parse_mode="Markdown"
        )


async def forcequest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to force a new quest for demo purposes."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Only the demo admin can force a new quest.")
        return

    # Check if a specific color was requested: /forcequest red
    args = context.args
    color_pref = args[0].lower() if args else None

    quest = quest_mgr.fetch_new_quest(preferred_color=color_pref)
    caption = (
        f"⚡ **DEMO QUEST OVERRIDE ACTIVATED!**\n\n"
        f"Target Color: **{quest['color_name']}** {quest['emoji']}\n"
        f"Requirement: At least **{PASS_THRESHOLD}%** of your photo must match!\n\n"
        f"💬 *{quest['description']}*\n\n"
        f"📷 Reference photo by [{quest['photographer']}]({quest['photographer_url']}) on [Unsplash](https://unsplash.com/?utm_source=pixel_fraction&utm_medium=referral)"
    )
    await update.message.reply_photo(
        photo=quest["photo_url"],
        caption=caption,
        parse_mode="Markdown"
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows top scores and streaks in this chat."""
    chat_id = update.effective_chat.id
    leaders = db.get_leaderboard(chat_id)

    if not leaders:
        text = "🏆 **Leaderboard is empty!**\nBe the first to submit a photo for today's quest!"
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        text = "🏆 **PIXEL FRACTION LEADERBOARD** 🏆\n\n"
        for idx, entry in enumerate(leaders):
            medal = medals[idx] if idx < len(medals) else "🔹"
            text += f"{medal} **{entry['name']}** — {entry['score']} pts (🔥 {entry['streak']} day streak)\n"

    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown")
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Evaluates uploaded photos against the active quest."""
    message = update.message
    if not message or not message.photo:
        return

    user = update.effective_user
    chat = update.effective_chat
    quest = quest_mgr.get_todays_quest()

    # Get largest available photo
    photo_file = message.photo[-1]
    file_obj = await photo_file.get_file()
    image_bytes = await file_obj.download_as_bytearray()

    # 1. Anti-Cheat Check
    if quest.get("dhash"):
        user_dhash = compute_dhash(bytes(image_bytes))
        similarity = compute_similarity(user_dhash, quest["dhash"])
        if similarity >= SIMILARITY_THRESHOLD:
            await message.reply_text(
                f"🚨 **Anti-Cheat Warning!**\n"
                f"Your photo is **{int(similarity * 100)}% identical** to the Unsplash reference photo!\n"
                f"Please take and submit an original photo from your surroundings.",
                parse_mode="Markdown"
            )
            return

    # 2. Color Pixel Fraction Analysis
    try:
        analysis = analyze_pixel_fraction(bytes(image_bytes), quest["color_key"])
    except Exception as e:
        logger.error(f"Error analyzing image: {e}")
        await message.reply_text("⚠️ Could not process image. Please try another photo.")
        return

    percentage = analysis["percentage"]
    color_name = analysis["target_color"]
    emoji = analysis["emoji"]

    submission_id = f"{chat.id}_{message.message_id}"
    db.register_photo_submission(submission_id, user.id)

    # 3. Determine Outcome and Points
    if percentage >= BONUS_THRESHOLD:
        points = 25
        badge = "🌟 **CRITICAL HIT! BONUS POINTS!** 🌟"
        status_msg = f"Incredible find! Your photo is **{percentage}%** {color_name} {emoji}!"
    elif percentage >= PASS_THRESHOLD:
        points = 10
        badge = "✅ **QUEST CLEARED!**"
        status_msg = f"Solid match! Your photo is **{percentage}%** {color_name} {emoji}."
    else:
        points = 0
        badge = "❌ **QUEST INCOMPLETE**"
        status_msg = f"Detected **{percentage}%** {color_name} {emoji}. Need at least **{PASS_THRESHOLD}%** to pass."

    if points > 0:
        user_data = db.record_submission(chat.id, user.id, user.first_name, points)
        streak_text = f"\n🔥 **Streak:** {user_data['streak']} days | 💎 **Total Score:** {user_data['score']} pts"
    else:
        streak_text = "\n💡 *Tip: Try getting closer or finding better lighting!*"

    # 4. Result Card with Community Vote Buttons
    card_text = (
        f"{badge}\n\n"
        f"👤 **Player:** {user.first_name}\n"
        f"🎯 **Target:** {color_name} {emoji}\n"
        f"📊 **Fraction Detected:** {percentage}%\n"
        f"{status_msg}"
        f"{streak_text}"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔥 Creative (0)", callback_data=f"vote:{submission_id}:creative"),
            InlineKeyboardButton("🎨 Nice Find (0)", callback_data=f"vote:{submission_id}:nice_find"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        card_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles voting and navigation inline buttons."""
    query = update.callback_query
    data = query.data

    if data == "cmd_quest":
        await quest_command(update, context)
        return
    elif data == "cmd_leaderboard":
        await leaderboard_command(update, context)
        return
    elif data == "cmd_myid":
        user_id = query.from_user.id
        await query.answer(f"Your User ID: {user_id}", show_alert=True)
        return

    # Voting: vote:{submission_id}:{vote_type}
    if data.startswith("vote:"):
        parts = data.split(":")
        if len(parts) == 3:
            _, sub_id, vote_type = parts
            voter_id = query.from_user.id
            success, alert_msg, counts = db.add_vote(sub_id, voter_id, vote_type)

            await query.answer(alert_msg)

            if success:
                # Update button text with counts
                c_creative = counts.get("creative", 0)
                c_nice = counts.get("nice_find", 0)
                new_keyboard = [
                    [
                        InlineKeyboardButton(f"🔥 Creative ({c_creative})", callback_data=f"vote:{sub_id}:creative"),
                        InlineKeyboardButton(f"🎨 Nice Find ({c_nice})", callback_data=f"vote:{sub_id}:nice_find"),
                    ]
                ]
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is missing! Set it in .env")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("quest", quest_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("setadmin", setadmin_command))
    app.add_handler(CommandHandler("forcequest", forcequest_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    if WEBHOOK_URL:
        # Render Webhook Mode
        webhook_path = f"/webhook/{TELEGRAM_BOT_TOKEN}"
        full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
        logger.info(f"Starting in WEBHOOK mode on port {PORT}")
        logger.info(f"Webhook URL: {full_webhook_url}")

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=full_webhook_url,
            secret_token=SECRET_TOKEN,
        )
    else:
        # Local Polling Mode
        logger.info("Starting in POLLING mode (Local development)...")
        app.run_polling()


if __name__ == "__main__":
    main()
