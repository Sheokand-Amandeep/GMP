import sys
# Ensure UTF-8 output in Windows command prompts
sys.stdout.reconfigure(encoding="utf-8")

import argparse
from typing import List

import config
from scraper import scrape_ipo_subscriptions
from filters import filter_ipo_data, project_columns
from telegram_sender import (
    send_ipo_report_to_telegram,
    build_card_message,
    build_table_message,
    COLUMN_DISPLAY_NAMES,
)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape IPO Live Subscription data from InvestorGain, filter columns/rows, and send to Telegram."
    )
    # Scraping target
    parser.add_argument(
        "--tab",
        default=config.DEFAULT_TAB,
        help="Subscription tab or URL (e.g. 'open', 'all', 'closing-today', 'sme', 'ipo' or full URL). Default: open",
    )

    # Filtering options
    parser.add_argument(
        "--category",
        choices=["all", "mainboard", "sme", "ipo"],
        default="all",
        help="Filter by IPO category: all, mainboard (or ipo), sme. Default: all",
    )
    parser.add_argument(
        "--min-total",
        type=float,
        default=None,
        help="Filter minimum Total subscription (e.g. 1.0 for oversubscribed issues).",
    )
    parser.add_argument(
        "--min-rii",
        type=float,
        default=None,
        help="Filter minimum Retail (RII) subscription times.",
    )
    parser.add_argument(
        "--min-qib",
        type=float,
        default=None,
        help="Filter minimum QIB subscription times.",
    )
    parser.add_argument(
        "--min-gmp",
        type=float,
        default=None,
        help="Filter minimum GMP percentage (e.g. 10.0 for >=10%%).",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by badge status (e.g. 'CT' for Closing Today, 'O' for Open).",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search query for IPO name or category.",
    )

    # Output columns selection
    parser.add_argument(
        "--columns",
        default=",".join(config.DEFAULT_COLUMNS),
        help=f"Comma-separated column names to include. Available: {', '.join(COLUMN_DISPLAY_NAMES.keys())}",
    )

    # Output format
    parser.add_argument(
        "--format",
        choices=["card", "table"],
        default="card",
        help="Telegram message format: 'card' (modern cards) or 'table' (monospace preformatted table). Default: card",
    )

    # Telegram Credentials
    parser.add_argument(
        "--token",
        default=config.TELEGRAM_BOT_TOKEN,
        help="Telegram Bot Token (or set TELEGRAM_BOT_TOKEN in .env).",
    )
    parser.add_argument(
        "--chat-id",
        default=config.TELEGRAM_CHAT_ID,
        help="Telegram Chat ID (or set TELEGRAM_CHAT_ID in .env).",
    )

    # Dry-run flag
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape, filter and display in console without sending to Telegram.",
    )

    parser.add_argument(
        "--title",
        default="📊 <b>IPO Live Subscription Report</b>",
        help="Custom header title for the message.",
    )

    return parser.parse_args()


def print_console_preview(records: List[dict], columns: List[str], fmt: str, title: str):
    print("=" * 60)
    print("PREVIEW OF TELEGRAM MESSAGE CONTENT:")
    print("=" * 60)
    if fmt == "table":
        chunks = build_table_message(records, columns, header_title=title)
    else:
        chunks = build_card_message(records, columns, header_title=title)

    for i, chunk in enumerate(chunks, 1):
        print(f"--- [Message Chunk {i}] ---")
        print(chunk)
        print()
    print("=" * 60)


def main():
    args = parse_args()
    selected_cols = [c.strip() for c in args.columns.split(",") if c.strip()]

    print(f"[*] Scraping subscription data from InvestorGain (tab/url: '{args.tab}')...")
    try:
        raw_data = scrape_ipo_subscriptions(args.tab)
    except Exception as e:
        print(f"[!] Scraping failed: {e}")
        sys.exit(1)

    print(f"[+] Total IPOs fetched: {len(raw_data)}")

    # Apply row filters
    filtered_data = filter_ipo_data(
        raw_data,
        category=args.category,
        min_total=args.min_total,
        min_rii=args.min_rii,
        min_qib=args.min_qib,
        min_gmp_pct=args.min_gmp,
        status=args.status,
        search=args.search,
    )
    print(f"[+] Records matching filters: {len(filtered_data)}")

    # Project to selected columns
    projected_data = project_columns(filtered_data, selected_cols)

    # Always show preview in terminal
    print_console_preview(projected_data, selected_cols, args.format, args.title)

    # Check dry run or send
    if args.dry_run:
        print("[i] Dry-run enabled. Message was NOT sent to Telegram.")
        return

    # Telegram credentials check
    bot_token = args.token
    chat_id = args.chat_id

    if not bot_token or not chat_id:
        print("\n[!] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not provided!")
        print("    You can either:")
        print("    1. Create a '.env' file with:")
        print("       TELEGRAM_BOT_TOKEN=your_bot_token_here")
        print("       TELEGRAM_CHAT_ID=your_chat_id_here")
        print("    2. Or pass them via CLI:")
        print("       python main.py --token <TOKEN> --chat-id <CHAT_ID>")
        print("\n    To test without sending, use: python main.py --dry-run")
        sys.exit(1)

    print(f"[*] Dispatching message to Telegram Chat ID: {chat_id}...")
    try:
        sent_chunks = send_ipo_report_to_telegram(
            projected_data,
            columns=selected_cols,
            bot_token=bot_token,
            chat_id=chat_id,
            fmt=args.format,
            title=args.title,
        )
        print(f"[SUCCESS] Successfully sent {sent_chunks} message chunk(s) to Telegram!")
    except Exception as e:
        print(f"[!] Failed to send message to Telegram: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
