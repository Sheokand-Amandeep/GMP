import sys
sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import html
import logging
from datetime import datetime
from typing import List, Dict, Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    BaseHandler,
    ContextTypes,
)


import config
import database
from scraper import scrape_ipo_subscriptions
from filters import filter_ipo_data, project_columns
from telegram_sender import (
    build_card_message,
    build_table_message,
    COLUMN_DISPLAY_NAMES,
)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("IPOBot")


class FlexibleCommandHandler(BaseHandler):
    """
    Custom handler allowing commands to:
    1. Be case-insensitive (e.g., /start, /START, start, START).
    2. Run with or without slashes (forward slash '/' or backward slash '\\').
    3. Support optional bot username mentions (@BotUsername).
    4. Populate context.args properly for parameterized commands.
    """

    def __init__(self, command: Any, callback: Any):
        super().__init__(callback)
        if isinstance(command, str):
            self.commands = {command.lower()}
        else:
            self.commands = {c.lower() for c in command}

    def check_update(self, update: object):
        if not isinstance(update, Update) or not update.effective_message:
            return None
        text = update.effective_message.text or update.effective_message.caption
        if not text:
            return None
        parts = text.strip().split()
        if not parts:
            return None
        raw_cmd = parts[0]
        # Strip any leading slashes (forward slash '/' or backward slash '\\')
        clean_cmd = raw_cmd.lstrip("/\\")
        if not clean_cmd:
            return None
        cmd_name, _, mention = clean_cmd.partition("@")
        cmd_name = cmd_name.lower()

        if mention and update.get_bot():
            try:
                bot_user = update.get_bot().username
                if bot_user and mention.lower() != bot_user.lower():
                    return None
            except Exception:
                pass

        if cmd_name in self.commands:
            args = parts[1:]
            return (args, True)
        return None

    def collect_additional_context(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        update: Update,
        application: Application,
        check_result: Any,
    ) -> None:
        if isinstance(check_result, tuple):
            context.args = check_result[0]


def get_or_register_user(update: Update) -> Dict[str, Any]:
    """Ensure user exists in DB; returns user dict."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    sub = database.get_subscriber(chat_id)
    if not sub:
        sub = database.add_subscriber(
            chat_id=chat_id,
            username=user.username or "",
            first_name=user.first_name or "",
        )
    return sub


# =====================================================================
# Command: /start
# =====================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Warm greeting explaining the bot concept without overwhelming with all filters."""
    user = update.effective_user
    first_name = user.first_name or "Investor"

    text = (
        f"👋 <b>Welcome, {first_name}!</b>\n\n"
        "📈 <b>About this Bot:</b>\n"
        "I track real-time <b>IPO Live Subscription Bidding</b> (QIB, Retail, NII, Total) "
        "and <b>Grey Market Premium (GMP)</b> for Mainboard & SME IPOs directly from InvestorGain.\n\n"
        "🔔 <b>How to Subscribe & Get Updates:</b>\n"
        "• Send <b>/add</b> — Subscribe to automatic IPO alerts & view filter customization options.\n"
        "• Send <b>/check</b> — Fetch the latest live IPO status immediately.\n"
        "• Send <b>/remove</b> — Unsubscribe from automatic updates anytime.\n"
        "• Send <b>/help</b> — Show list of basic commands."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# =====================================================================
# Command: /add
# =====================================================================
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe user to automatic IPO alerts and present all available configuration options."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    sub = database.add_subscriber(
        chat_id=chat_id,
        username=user.username or "",
        first_name=user.first_name or "",
    )

    text = (
        "✅ <b>You are now SUBSCRIBED to automatic IPO alerts!</b>\n\n"
        "📋 <b>Your Current Filter Settings:</b>\n"
        f"• <b>Scope:</b> <code>{sub.get('tab', 'open')}</code> (e.g. open IPOs only)\n"
        f"• <b>Category:</b> <code>{sub.get('category', 'all')}</code> (Mainboard + SME)\n"
        f"• <b>Frequency:</b> <code>{sub.get('frequency', 'daily').capitalize()}</code>\n"
        f"• <b>Delivery Time:</b> <code>{sub.get('preferred_time', 'morning').capitalize()} ({'06:00 AM' if sub.get('preferred_time') != 'evening' else '06:00 PM'})</code>\n"
        f"• <b>Min GMP:</b> <code>{sub.get('min_gmp', 0.0)}%</code>\n"
        f"• <b>Min Total Sub:</b> <code>{sub.get('min_total', 0.0)}x</code>\n"
        f"• <b>Min Retail Sub:</b> <code>{sub.get('min_rii', 0.0)}x</code>\n"
        f"• <b>Display Format:</b> <code>{sub.get('format', 'card')}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ <b>HOW TO CONFIGURE YOUR FILTERS:</b>\n"
        "Send any of these commands to customize your alerts:\n\n"
        "⏰ <b>1. Frequency & Delivery Time:</b>\n"
        "• /daily — Receive IPO data every day (Default)\n"
        "• /alternate — Receive data every alternate day (every 2 days)\n"
        "• /thirdday — Receive data every 3rd day (skipping 2 days in between)\n"
        "• /morning — Receive in the morning at 6:00 AM (Default)\n"
        "• /evening — Receive in the evening at 6:00 PM\n\n"
        "🏷️ <b>2. Scope & Category:</b>\n"
        "• /open — Receive only currently Open IPOs\n"
        "• /all — Receive All IPOs (Open, Listed & Recent)\n"
        "• /closing — Receive only IPOs closing today\n"
        "• /mainboard — Mainboard IPOs only\n"
        "• /sme — SME IPOs only\n"
        "• /both — Both Mainboard & SME\n\n"
        "🎯 <b>3. Demand & Profit Thresholds:</b>\n"
        "• <code>/mingmp 20</code> — Only IPOs with >=20% GMP (use <code>/mingmp 0</code> to reset)\n"
        "• <code>/mintotal 2</code> — Only IPOs subscribed >=2x (use <code>/mintotal 0</code> to reset)\n"
        "• <code>/minretail 1.5</code> — Only IPOs with Retail >=1.5x\n\n"
        "📊 <b>4. Display Style & Columns:</b>\n"
        "• <code>/format card</code> — Visual cards with badges & clickable links\n"
        "• <code>/format table</code> — Compact monospace preformatted table\n"
        "• <code>/columns name,price,rii_lot_size,shni_lot_size,total,gmp</code> — Select custom columns\n"
        "• <code>/columns reset</code> — Reset to default columns\n\n"
        "🔍 <b>5. Inspect & Test:</b>\n"
        "• /check — Fetch your live custom report right now!\n"
        "• /myfilters — Review your current active preferences\n"
        "• /remove — Unsubscribe anytime\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)



# =====================================================================
# Command: /remove
# =====================================================================
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe user from automatic updates."""
    chat_id = update.effective_chat.id
    database.remove_subscriber(chat_id)

    text = (
        "🛑 <b>You have been UNSUBSCRIBED from automatic IPO alerts.</b>\n\n"
        "You will no longer receive periodic updates.\n"
        "💡 <i>You can re-subscribe anytime by sending</i> <b>/add</b>."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# =====================================================================
# Scope & Category filter commands: /open, /all, /closing, /sme, /mainboard, /both
# =====================================================================
async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, tab="open")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> You will now receive <b>Open IPOs only</b>.\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, tab="all")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> You will now receive <b>All IPOs</b> (Open, Recent, Listed).\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def closing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, tab="closing-today")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> You will now receive <b>IPOs Closing Today only</b>.\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def sme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, category="sme")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> You will now receive <b>SME IPOs only</b>.\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def mainboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, category="mainboard")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> You will now receive <b>Mainboard IPOs only</b>.\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def both_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, category="all")
    await update.message.reply_text(
        "✅ <b>Filter updated:</b> Category set to <b>Both Mainboard & SME</b>.\n"
        "💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# Subscription Frequency Commands: /daily, /alternate, /thirdday
# =====================================================================
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, frequency="daily")
    await update.message.reply_text(
        "✅ <b>Subscription Frequency set to DAILY!</b>\n"
        "You will receive IPO subscription alerts <b>every day</b> at your chosen time.\n"
        "💡 Review settings with /myfilters or test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def alternate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, frequency="alternate")
    await update.message.reply_text(
        "✅ <b>Subscription Frequency set to ALTERNATE DAYS!</b>\n"
        "You will receive IPO updates <b>every alternate day</b> (1 day gap between alerts).\n"
        "💡 Review settings with /myfilters or test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def thirdday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, frequency="thirdday")
    await update.message.reply_text(
        "✅ <b>Subscription Frequency set to EVERY THIRD DAY!</b>\n"
        "You will receive IPO updates by <b>skipping two days in between</b>.\n"
        "💡 Review settings with /myfilters or test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# Delivery Time Commands: /morning, /evening
# =====================================================================
async def morning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, preferred_time="morning")
    await update.message.reply_text(
        "🌅 <b>Delivery time set to MORNING (06:00 AM)!</b>\n"
        "You will receive your IPO reports at 6:00 AM according to your frequency.\n"
        "💡 Review settings with /myfilters or test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )

async def evening_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    database.update_subscriber(chat_id, preferred_time="evening")
    await update.message.reply_text(
        "🌆 <b>Delivery time set to EVENING (06:00 PM)!</b>\n"
        "You will receive your IPO reports at 6:00 PM according to your frequency.\n"
        "💡 Review settings with /myfilters or test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# Threshold filter commands: /mingmp, /mintotal, /minretail
# =====================================================================

async def mingmp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    args = context.args

    if not args:
        sub = database.get_subscriber(chat_id)
        current = sub.get("min_gmp", 0.0)
        await update.message.reply_text(
            f"ℹ️ Current minimum GMP filter: <b>{current}%</b>\n\n"
            "To change, specify a percentage, e.g.:\n"
            "• <code>/mingmp 20</code> (only >=20% GMP)\n"
            "• <code>/mingmp 0</code> (reset/remove filter)",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        val = float(args[0].replace("%", "").strip())
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid number! Example usage: <code>/mingmp 20</code> or <code>/mingmp 0</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    database.update_subscriber(chat_id, min_gmp=max(0.0, val))
    if val <= 0:
        msg = "✅ Minimum GMP filter has been <b>reset</b> (all GMP values included)."
    else:
        msg = f"✅ Minimum GMP filter set to <b>>= {val}%</b>."

    await update.message.reply_text(f"{msg}\n💡 Test anytime with /check.", parse_mode=ParseMode.HTML)


async def mintotal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    args = context.args

    if not args:
        sub = database.get_subscriber(chat_id)
        current = sub.get("min_total", 0.0)
        await update.message.reply_text(
            f"ℹ️ Current minimum Total Subscription: <b>{current}x</b>\n\n"
            "To change, specify a number of times, e.g.:\n"
            "• <code>/mintotal 2</code> (only >=2x subscribed)\n"
            "• <code>/mintotal 0</code> (reset/remove filter)",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        val = float(args[0].lower().replace("x", "").strip())
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid number! Example usage: <code>/mintotal 2.5</code> or <code>/mintotal 0</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    database.update_subscriber(chat_id, min_total=max(0.0, val))
    if val <= 0:
        msg = "✅ Minimum Total Subscription filter has been <b>reset</b>."
    else:
        msg = f"✅ Minimum Total Subscription set to <b>>= {val}x</b>."

    await update.message.reply_text(f"{msg}\n💡 Test anytime with /check.", parse_mode=ParseMode.HTML)


async def minretail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    args = context.args

    if not args:
        sub = database.get_subscriber(chat_id)
        current = sub.get("min_rii", 0.0)
        await update.message.reply_text(
            f"ℹ️ Current minimum Retail (RII) Subscription: <b>{current}x</b>\n\n"
            "To change, specify a number of times, e.g.:\n"
            "• <code>/minretail 1.5</code> (only >=1.5x)\n"
            "• <code>/minretail 0</code> (reset/remove filter)",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        val = float(args[0].lower().replace("x", "").strip())
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid number! Example usage: <code>/minretail 1.5</code> or <code>/minretail 0</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    database.update_subscriber(chat_id, min_rii=max(0.0, val))
    if val <= 0:
        msg = "✅ Minimum Retail (RII) Subscription filter has been <b>reset</b>."
    else:
        msg = f"✅ Minimum Retail (RII) Subscription set to <b>>= {val}x</b>."

    await update.message.reply_text(f"{msg}\n💡 Test anytime with /check.", parse_mode=ParseMode.HTML)


# =====================================================================
# Display & Column Selection: /format, /columns
# =====================================================================
async def format_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    args = context.args

    if not args or args[0].lower() not in ["card", "table"]:
        await update.message.reply_text(
            "ℹ️ Choose display format:\n"
            "• <code>/format card</code> — Visual cards with badges & clickable links\n"
            "• <code>/format table</code> — Compact monospace preformatted table",
            parse_mode=ParseMode.HTML,
        )
        return

    fmt = args[0].lower()
    database.update_subscriber(chat_id, format=fmt)
    await update.message.reply_text(
        f"✅ Display format updated to <b>{fmt}</b>.\n💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )


async def columns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_or_register_user(update)
    args = context.args

    if not args:
        sub = database.get_subscriber(chat_id)
        current = sub.get("columns", database.DEFAULT_USER_COLUMNS)
        valid_cols = ", ".join(f"<code>{k}</code>" for k in COLUMN_DISPLAY_NAMES.keys())
        await update.message.reply_text(
            f"📋 <b>Your Current Columns:</b>\n<code>{current}</code>\n\n"
            f"<b>Available Columns:</b>\n{valid_cols}\n\n"
            "<b>Usage:</b>\n"
            "• <code>/columns name,total,rii,qib,gmp,closing_date</code>\n"
            "• <code>/columns reset</code> (restores default columns)",
            parse_mode=ParseMode.HTML,
        )
        return

    joined_arg = " ".join(args).strip().lower()
    if joined_arg == "reset":
        database.update_subscriber(chat_id, columns=database.DEFAULT_USER_COLUMNS)
        await update.message.reply_text(
            f"✅ Columns reset to default:\n<code>{database.DEFAULT_USER_COLUMNS}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_cols = [c.strip() for c in joined_arg.split(",") if c.strip()]
    if not raw_cols:
        await update.message.reply_text("⚠️ No valid column names provided.")
        return

    # Filter to recognized columns
    clean_cols = [c for c in raw_cols if c in COLUMN_DISPLAY_NAMES]
    if not clean_cols:
        await update.message.reply_text(
            f"⚠️ None of the provided columns were recognized. Available:\n{', '.join(COLUMN_DISPLAY_NAMES.keys())}"
        )
        return

    # Ensure 'name' is included
    if "name" not in clean_cols:
        clean_cols.insert(0, "name")

    col_str = ",".join(clean_cols)
    database.update_subscriber(chat_id, columns=col_str)
    await update.message.reply_text(
        f"✅ Selected columns updated:\n<code>{col_str}</code>\n💡 Test anytime with /check.",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# Status & Inspection: /myfilters, /help, /check
# =====================================================================
async def myfilters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sub = get_or_register_user(update)

    active_status = "🟢 Active (Subscribed)" if sub.get("is_active") else "🔴 Inactive (Unsubscribed)"
    
    freq_label = {
        "daily": "Daily (Every day)",
        "alternate": "Alternate Days (Every 2 days)",
        "thirdday": "Every Third Day (Skip 2 days in between)"
    }.get(sub.get("frequency", "daily"), sub.get("frequency", "daily"))

    time_label = {
        "morning": "Morning at 06:00 AM",
        "evening": "Evening at 06:00 PM"
    }.get(sub.get("preferred_time", "morning"), sub.get("preferred_time", "morning"))

    last_sent = sub.get("last_sent_date") or "Not yet dispatched"

    text = (
        f"⚙️ <b>Your Active Filter & Schedule Profile:</b>\n\n"
        f"• <b>Status:</b> {active_status}\n"
        f"• <b>Frequency (/daily | /alternate | /thirdday):</b>\n  <code>{freq_label}</code>\n"
        f"• <b>Delivery Time (/morning | /evening):</b>\n  <code>{time_label}</code>\n"
        f"• <b>Last Dispatched Date:</b> <code>{last_sent}</code>\n"
        f"• <b>Scope (/open | /all | /closing):</b> <code>{sub.get('tab', 'open')}</code>\n"
        f"• <b>Category (/mainboard | /sme | /both):</b> <code>{sub.get('category', 'all')}</code>\n"
        f"• <b>Min GMP (/mingmp):</b> <code>{sub.get('min_gmp', 0.0)}%</code>\n"
        f"• <b>Min Total Sub (/mintotal):</b> <code>{sub.get('min_total', 0.0)}x</code>\n"
        f"• <b>Min Retail Sub (/minretail):</b> <code>{sub.get('min_rii', 0.0)}x</code>\n"
        f"• <b>Display Format (/format):</b> <code>{sub.get('format', 'card')}</code>\n"
        f"• <b>Selected Columns (/columns):</b>\n  <code>{sub.get('columns', database.DEFAULT_USER_COLUMNS)}</code>\n\n"
        "💡 <i>Send /check to generate your live report right now!</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>IPO Bot Command Directory:</b>\n\n"
        "💡 <i>All commands are case-insensitive and can be run with <code>/</code>, <code>\\</code>, or directly without any slash (e.g. <code>check</code>, <code>CHECK</code>, <code>/check</code>, or <code>\\check</code>).</i>\n\n"
        "<b>Core Actions:</b>\n"
        "• /start — Welcome & Bot introduction\n"
        "• /add — Subscribe & view all filter settings\n"
        "• /remove — Unsubscribe from automatic updates\n"
        "• /check — Fetch live report immediately\n"
        "• /myfilters — Check your current active settings\n\n"
        "<b>Schedule & Timing:</b>\n"
        "• /daily — Receive alerts everyday (Default)\n"
        "• /alternate — Receive alerts every alternate day\n"
        "• /thirdday — Receive alerts skipping 2 days in between\n"
        "• /morning — Receive alerts at 6:00 AM (Default)\n"
        "• /evening — Receive alerts at 6:00 PM\n\n"
        "<b>Filter Scope & Category:</b>\n"
        "• /open — Open IPOs only\n"
        "• /all — All IPOs\n"
        "• /closing — Closing today only\n"
        "• /mainboard — Mainboard only\n"
        "• /sme — SME only\n"
        "• /both — Both Mainboard and SME\n\n"
        "<b>Numeric Filters:</b>\n"
        "• /mingmp &lt;pct&gt; — Minimum GMP % (e.g. <code>/mingmp 20</code> or <code>mingmp 20</code>)\n"
        "• /mintotal &lt;x&gt; — Minimum Total Subscription (e.g. <code>/mintotal 2</code> or <code>mintotal 2</code>)\n"
        "• /minretail &lt;x&gt; — Minimum Retail Subscription (e.g. <code>/minretail 1.5</code> or <code>minretail 1.5</code>)\n\n"
        "<b>Display:</b>\n"
        "• /format &lt;card|table&gt; — Card or table layout\n"
        "• /columns &lt;cols&gt; — Select custom columns\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)



async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch live data from InvestorGain, apply user's saved filters, and send immediately."""
    chat_id = update.effective_chat.id
    sub = get_or_register_user(update)

    tab = sub.get("tab", "open")
    cat = sub.get("category", "all")
    min_gmp = sub.get("min_gmp") if sub.get("min_gmp", 0.0) > 0 else None
    min_tot = sub.get("min_total") if sub.get("min_total", 0.0) > 0 else None
    min_rii = sub.get("min_rii") if sub.get("min_rii", 0.0) > 0 else None
    fmt = sub.get("format", "card")
    cols = [c.strip() for c in sub.get("columns", database.DEFAULT_USER_COLUMNS).split(",") if c.strip()]

    status_msg = await update.message.reply_text(
        f"⏳ <i>Scraping live IPO data ({tab})...</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        raw_records = await asyncio.to_thread(scrape_ipo_subscriptions, tab)
    except Exception as e:
        logger.error(f"Error scraping for user {chat_id}: {e}")
        await status_msg.edit_text("❌ Failed to fetch data from InvestorGain. Please try again later.")
        return

    # Apply user-specific filters
    filtered = filter_ipo_data(
        raw_records,
        category=cat,
        min_total=min_tot,
        min_rii=min_rii,
        min_gmp_pct=min_gmp,
    )

    projected = project_columns(filtered, cols)

    title = (
        f"📊 <b>IPO Live Subscription Report</b>\n"
        f"<i>Scope: {tab.upper()} | Cat: {cat.upper()} | Total Found: {len(projected)}</i>"
    )

    if fmt == "table":
        chunks = build_table_message(projected, cols, header_title=title)
    else:
        chunks = build_card_message(projected, cols, header_title=title)

    await status_msg.delete()

    for chunk in chunks:
        await update.message.reply_text(
            chunk,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


# =====================================================================
# Automated Background Broadcaster (Scheduled at 6:00 AM & 6:00 PM)
# =====================================================================
async def dispatch_scheduled_batch(application: Application, slot_name: str, today: Any):
    """
    Dispatch scheduled IPO reports to all eligible subscribers for current slot ('morning' or 'evening').
    Respects:
      - preferred_time (morning at 6 AM or evening at 6 PM)
      - frequency (daily, alternate, thirdday)
    """
    subscribers = database.get_active_subscribers()
    if not subscribers:
        return

    eligible = [s for s in subscribers if database.should_send_to_user(s, slot_name, today)]
    if not eligible:
        logger.info(f"No subscribers eligible for {slot_name} slot on {today.isoformat()}.")
        return

    logger.info(f"Dispatching {slot_name} scheduled alert to {len(eligible)} subscriber(s) on {today.isoformat()}...")

    # Group by tab so each tab is scraped at most once per batch
    needed_tabs = set(s.get("tab", "open") for s in eligible)
    tab_data: Dict[str, List[dict]] = {}

    for tab in needed_tabs:
        try:
            tab_data[tab] = await asyncio.to_thread(scrape_ipo_subscriptions, tab)
        except Exception as e:
            logger.error(f"Error scraping tab '{tab}' during {slot_name} schedule: {e}")
            tab_data[tab] = []

    for sub in eligible:
        chat_id = sub["chat_id"]
        tab = sub.get("tab", "open")
        records = tab_data.get(tab, [])
        if not records:
            continue

        cat = sub.get("category", "all")
        min_gmp = sub.get("min_gmp") if sub.get("min_gmp", 0.0) > 0 else None
        min_tot = sub.get("min_total") if sub.get("min_total", 0.0) > 0 else None
        min_rii = sub.get("min_rii") if sub.get("min_rii", 0.0) > 0 else None
        fmt = sub.get("format", "card")
        cols = [c.strip() for c in sub.get("columns", database.DEFAULT_USER_COLUMNS).split(",") if c.strip()]

        filtered = filter_ipo_data(
            records,
            category=cat,
            min_total=min_tot,
            min_rii=min_rii,
            min_gmp_pct=min_gmp,
        )

        if not filtered:
            continue

        projected = project_columns(filtered, cols)
        slot_label = "Morning (06:00 AM)" if slot_name == "morning" else "Evening (06:00 PM)"
        title = (
            f"🔔 <b>{slot_label} Scheduled IPO Alert</b>\n"
            f"<i>Scope: {tab.upper()} | Cat: {cat.upper()} | Frequency: {sub.get('frequency', 'daily').capitalize()}</i>"
        )

        if fmt == "table":
            chunks = build_table_message(projected, cols, header_title=title)
        else:
            chunks = build_card_message(projected, cols, header_title=title)

        sent_success = False
        for chunk in chunks:
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                sent_success = True
                await asyncio.sleep(0.5)  # Telegram rate limit compliance
            except Exception as err:
                logger.warning(f"Failed to send scheduled message to {chat_id}: {err}")
                break

        if sent_success:
            database.record_sent(chat_id, today.isoformat())


async def broadcast_loop(application: Application):
    """
    Background worker that runs continuously.
    Checks the local clock every 20 seconds.
    Triggers automatically at:
      - 06:00 AM for subscribers with /morning
      - 06:00 PM (18:00) for subscribers with /evening
    Respects /daily, /alternate, /thirdday frequencies.
    """
    logger.info(
        f"Automated time-based scheduler started. "
        f"Morning: {config.MORNING_HOUR:02d}:{config.MORNING_MINUTE:02d}, "
        f"Evening: {config.EVENING_HOUR:02d}:{config.EVENING_MINUTE:02d}."
    )
    last_triggered_slot = None  # Tuple: (slot_name, date_str)

    while True:
        try:
            await asyncio.sleep(20)
            now = datetime.now()
            today = now.date()
            today_str = today.isoformat()

            # Morning check (06:00 AM)
            if now.hour == config.MORNING_HOUR and now.minute == config.MORNING_MINUTE:
                slot_key = ("morning", today_str)
                if last_triggered_slot != slot_key:
                    last_triggered_slot = slot_key
                    logger.info("Clock matched Morning schedule (06:00 AM). Starting batch dispatch...")
                    await dispatch_scheduled_batch(application, "morning", today)

            # Evening check (06:00 PM)
            elif now.hour == config.EVENING_HOUR and now.minute == config.EVENING_MINUTE:
                slot_key = ("evening", today_str)
                if last_triggered_slot != slot_key:
                    last_triggered_slot = slot_key
                    logger.info("Clock matched Evening schedule (06:00 PM). Starting batch dispatch...")
                    await dispatch_scheduled_batch(application, "evening", today)

        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)


async def triggersend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Test command to instantly test the scheduled dispatch without waiting for 6 AM / 6 PM."""
    chat_id = update.effective_chat.id
    owner_id = str(config.TELEGRAM_CHAT_ID).strip()
    if owner_id and str(chat_id) != owner_id:
        await update.message.reply_text("⛔ This command is restricted to the bot owner.")
        return

    sub = database.get_subscriber(chat_id)
    slot = "morning"
    if context.args and context.args[0].lower() in ["morning", "evening"]:
        slot = context.args[0].lower()
    elif sub and sub.get("preferred_time") == "evening":
        slot = "evening"

    now = datetime.now()
    await update.message.reply_text(
        f"⚡ <i>Triggering manual test of {slot.upper()} scheduled broadcast right now...</i>",
        parse_mode=ParseMode.HTML
    )
    # Temporarily bypass frequency restriction for test trigger
    await dispatch_scheduled_batch(context.application, slot, now.date())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner command to view user counts and subscription statistics."""
    try:
        chat_id = update.effective_chat.id if update.effective_chat else None
        user_id = update.effective_user.id if update.effective_user else None
        owner_id = str(config.TELEGRAM_CHAT_ID).strip() if config.TELEGRAM_CHAT_ID else ""

        logger.info(f"Stats command received from chat_id={chat_id}, user_id={user_id} (Configured owner_id={owner_id})")

        # Restrict to owner if TELEGRAM_CHAT_ID is set
        if owner_id and str(chat_id) != owner_id and str(user_id) != owner_id:
            logger.warning(f"Unauthorized /stats attempt by user_id: {user_id}, chat_id: {chat_id}")
            await update.message.reply_text("⛔ This command is restricted to the bot owner.")
            return

        stats = database.get_stats()
        text = (
            "📊 <b>IPO Bot Subscriber Statistics:</b>\n\n"
            f"👥 <b>Total Tracked Users:</b> <code>{stats['total']}</code>\n"
            f"🟢 <b>Active Subscribers (via /add):</b> <code>{stats['active']}</code>\n"
            f"🔴 <b>Unsubscribed Users (via /remove):</b> <code>{stats['inactive']}</code>\n\n"
            "⏰ <b>Active Delivery Preferences:</b>\n"
            f"• Morning (06:00 AM): <code>{stats['by_time'].get('morning', 0)}</code>\n"
            f"• Evening (06:00 PM): <code>{stats['by_time'].get('evening', 0)}</code>\n\n"
            "📅 <b>Active Frequency Preferences:</b>\n"
            f"• Daily: <code>{stats['by_frequency'].get('daily', 0)}</code>\n"
            f"• Alternate: <code>{stats['by_frequency'].get('alternate', 0)}</code>\n"
            f"• Every 3rd Day: <code>{stats['by_frequency'].get('thirdday', 0)}</code>\n"
        )

        if stats["recent"]:
            text += "\n👤 <b>Recent Users:</b>\n"
            for u in stats["recent"][:15]:
                name = html.escape(str(u.get("first_name") or "User"))
                uname = f" (@{html.escape(str(u['username']))})" if u.get("username") else ""
                status = "🟢 Active" if u.get("is_active") else "🔴 Inactive"
                text += f"• {status} — <b>{name}</b>{uname} [<code>{u['chat_id']}</code>]\n"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error handling stats_command: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Error fetching stats: {e}")


async def on_startup(application: Application):
    """Hook called when the application starts up; spawns the broadcast background task."""
    database.init_db()
    asyncio.create_task(broadcast_loop(application))
    logger.info("IPO Bot startup completed. Ready for updates.")


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "your_bot_token_here":
        print("\n" + "=" * 60)
        print(" [!] ERROR: TELEGRAM_BOT_TOKEN is missing or not configured!")
        print("     Please set your bot token in .env or environment variable.")
        print("     Example: TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("=" * 60 + "\n")
        sys.exit(1)

    print(f"[*] Starting IPO Telegram Bot (Python-Telegram-Bot)...")
    app = ApplicationBuilder().token(token).post_init(on_startup).build()

    # Core commands
    app.add_handler(FlexibleCommandHandler("start", start_command))
    app.add_handler(FlexibleCommandHandler("add", add_command))
    app.add_handler(FlexibleCommandHandler(["remove", "stop"], remove_command))

    # Frequency & Delivery Time
    app.add_handler(FlexibleCommandHandler("daily", daily_command))
    app.add_handler(FlexibleCommandHandler("alternate", alternate_command))
    app.add_handler(FlexibleCommandHandler("thirdday", thirdday_command))
    app.add_handler(FlexibleCommandHandler("morning", morning_command))
    app.add_handler(FlexibleCommandHandler("evening", evening_command))

    # Scope & Category
    app.add_handler(FlexibleCommandHandler("open", open_command))
    app.add_handler(FlexibleCommandHandler("all", all_command))
    app.add_handler(FlexibleCommandHandler("closing", closing_command))
    app.add_handler(FlexibleCommandHandler("sme", sme_command))
    app.add_handler(FlexibleCommandHandler("mainboard", mainboard_command))
    app.add_handler(FlexibleCommandHandler("both", both_command))

    # Numeric thresholds
    app.add_handler(FlexibleCommandHandler("mingmp", mingmp_command))
    app.add_handler(FlexibleCommandHandler("mintotal", mintotal_command))
    app.add_handler(FlexibleCommandHandler("minretail", minretail_command))

    # Display & Column Selection
    app.add_handler(FlexibleCommandHandler("format", format_command))
    app.add_handler(FlexibleCommandHandler("columns", columns_command))

    # Inspection & Testing
    app.add_handler(FlexibleCommandHandler(["myfilters", "settings"], myfilters_command))
    app.add_handler(FlexibleCommandHandler(["check", "now"], check_command))
    app.add_handler(FlexibleCommandHandler("triggersend", triggersend_command))
    app.add_handler(FlexibleCommandHandler(["stats", "users", "subscribers"], stats_command))
    app.add_handler(FlexibleCommandHandler("help", help_command))

    print("[+] Handlers registered. Starting continuous long polling...")
    app.run_polling()


if __name__ == "__main__":
    main()

