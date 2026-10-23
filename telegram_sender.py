import html
import requests
from typing import List, Dict, Any, Optional

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

COLUMN_DISPLAY_NAMES = {
    "name": "IPO Name",
    "category": "Category",
    "status": "Status",
    "gmp": "GMP",
    "total": "Total Sub",
    "total_time": "Updated",
    "qib": "QIB",
    "shni": "sHNI",
    "bhni": "bHNI",
    "nii": "NII",
    "rii": "Retail (RII)",
    "anchor": "Anchor",
    "size": "Issue Size",
    "price": "Price (₹)",
    "pe": "P/E",
    "closing_date": "Closing Date",
    "rii_lot_size": "Retail Lot (₹)",
    "shni_lot_size": "sHNI Lot (₹)",
}



def build_card_message(
    records: List[Dict[str, Any]],
    columns: List[str],
    header_title: str = "📊 <b>IPO Live Subscription Report</b>"
) -> List[str]:
    """
    Format records as clean, beautiful Telegram cards (HTML mode).
    Returns a list of message chunks (each <= 4000 characters).
    """
    if not records:
        return [f"{header_title}\n\n<i>No IPOs matched your filter criteria.</i>"]

    messages = []
    current_chunk = f"{header_title}\n\n"

    for idx, r in enumerate(records, 1):
        name = html.escape(str(r.get("name", "Unknown")))
        link = r.get("link") or r.get("_link")
        name_html = f"<a href='{link}'><b>{name}</b></a>" if link else f"<b>{name}</b>"

        card_lines = [f"{idx}. {name_html}"]

        for col in columns:
            col_lower = col.strip().lower()
            if col_lower in ["name", "link", "_link"]:
                continue

            disp_name = COLUMN_DISPLAY_NAMES.get(col_lower, col_lower.capitalize())
            val = r.get(col_lower, "-")
            val_str = html.escape(str(val))

            # Nice emoji prefixes for key columns
            icon = "▫️"
            if col_lower == "total":
                icon = "🔥"
            elif col_lower in ["rii", "retail"]:
                icon = "👥"
            elif col_lower == "qib":
                icon = "🏛️"
            elif col_lower in ["nii", "hni"]:
                icon = "💼"
            elif col_lower == "gmp":
                icon = "📈"
            elif col_lower in ["closing_date", "date"]:
                icon = "📅"
            elif col_lower == "price":
                icon = "💰"
            elif col_lower in ["rii_lot_size", "rii_lot"]:
                icon = "🛒"
            elif col_lower in ["shni_lot_size", "shni_lot"]:
                icon = "🏢"
            elif col_lower == "size":
                icon = "📦"

            elif col_lower == "category":
                icon = "🏷️"

            card_lines.append(f"   {icon} <b>{disp_name}:</b> {val_str}")

        card_lines.append("")  # Blank line separator
        card_text = "\n".join(card_lines)

        if len(current_chunk) + len(card_text) > 3800:
            messages.append(current_chunk.strip())
            current_chunk = card_text
        else:
            current_chunk += card_text + "\n"

    if current_chunk.strip():
        messages.append(current_chunk.strip())

    return messages


def build_table_message(
    records: List[Dict[str, Any]],
    columns: List[str],
    header_title: str = "📊 <b>IPO Live Subscription Report</b>"
) -> List[str]:
    """
    Format records as a monospace preformatted table (<pre>...</pre>).
    Returns message chunks (each <= 4000 characters).
    """
    if not records:
        return [f"{header_title}\n\n<pre>No records found.</pre>"]

    headers = [COLUMN_DISPLAY_NAMES.get(c.lower(), c.capitalize()) for c in columns]
    rows = []
    for r in records:
        row = [str(r.get(c.lower(), "-")) for c in columns]
        rows.append(row)

    # Compute max column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    # Format header & separator
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * widths[i] for i in range(len(widths)))

    table_lines = [header_line, sep_line]
    for row in rows:
        line = " | ".join(val.ljust(widths[i]) for i, val in enumerate(row))
        table_lines.append(line)

    full_table = "\n".join(table_lines)

    # Split into chunks if too long
    messages = []
    lines = full_table.split("\n")
    cur_lines = []
    cur_len = len(header_title) + 20

    for line in lines:
        if cur_len + len(line) + 1 > 3800:
            msg = f"{header_title}\n\n<pre>{html.escape(chr(10).join(cur_lines))}</pre>"
            messages.append(msg)
            cur_lines = [header_line, sep_line, line]
            cur_len = len(header_title) + 20 + len(header_line) + len(sep_line) + len(line)
        else:
            cur_lines.append(line)
            cur_len += len(line) + 1

    if cur_lines:
        msg = f"{header_title}\n\n<pre>{html.escape(chr(10).join(cur_lines))}</pre>"
        messages.append(msg)

    return messages


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> Dict[str, Any]:
    """
    Send a single message via Telegram Bot API.
    """
    if not bot_token or not chat_id:
        raise ValueError(
            "Telegram BOT_TOKEN or CHAT_ID is missing. "
            "Please provide them via CLI arguments (--token, --chat-id) or .env file."
        )

    url = TELEGRAM_API_URL.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }

    resp = requests.post(url, json=payload, timeout=15)
    data = resp.json()
    if not resp.ok or not data.get("ok"):
        error_desc = data.get("description", "Unknown Telegram error")
        raise RuntimeError(f"Telegram API Error ({resp.status_code}): {error_desc}")

    return data


def send_ipo_report_to_telegram(
    records: List[Dict[str, Any]],
    columns: List[str],
    bot_token: str,
    chat_id: str,
    fmt: str = "card",
    title: str = "📊 <b>IPO Live Subscription Report</b>"
) -> int:
    """
    Format and send the report chunks to Telegram.
    Returns the count of successfully sent message chunks.
    """
    if fmt == "table":
        chunks = build_table_message(records, columns, header_title=title)
    else:
        chunks = build_card_message(records, columns, header_title=title)

    sent_count = 0
    for chunk in chunks:
        send_telegram_message(bot_token, chat_id, chunk)
        sent_count += 1

    return sent_count
