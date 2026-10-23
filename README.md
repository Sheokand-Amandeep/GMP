# IPO Live Subscription & GMP Telegram Bot (Full Hosting Service)

A production-ready Telegram Bot that tracks real-time IPO Live Subscription Bidding details and Grey Market Premium (GMP) for Indian Mainboard and SME IPOs from [InvestorGain](https://www.investorgain.com/report/ipo-subscription-live/333/open/).

Subscribers can configure their own personalized filters directly in Telegram chats, and receive automated updates on schedule.

---

## 🌟 Key Features

1. **User Welcome (`/start`)**:
   - Clean, friendly introduction explaining what the bot does without overwhelming the user.
2. **Subscribers Management (`/add` and `/remove`)**:
   - `/add`: Subscribes the user, registers their chat ID into an SQLite database (`subscribers.db`), and presents a comprehensive configuration guide.
   - `/remove`: Unsubscribes the user from automated alerts.
3. **Per-User Persistent Filters**:
   - **Delivery Frequency**:
     - `/daily` — Receive data every day (Default).
     - `/alternate` — Receive data every alternate day (1 day interval between sends).
     - `/thirdday` — Receive data every 3rd day (skipping 2 days in between).
   - **Delivery Timing**:
     - `/morning` — Receive alerts at 6:00 AM in the morning (Default).
     - `/evening` — Receive alerts at 6:00 PM in the evening.
   - **Filter Preferences**:
     - `/open` — Subscribe to Open IPOs only.
     - `/all` — Subscribe to All IPOs (Open, Listed & Recent).
     - `/closing` — Subscribe to IPOs Closing Today only.
     - `/mainboard` — Filter for Mainboard IPOs only.
     - `/sme` — Filter for SME IPOs only.
     - `/both` — Receive both Mainboard and SME IPOs.
     - `/mingmp <number>` — e.g. `/mingmp 20` to only receive IPOs with >=20% GMP (use `/mingmp 0` to reset).
     - `/mintotal <number>` — e.g. `/mintotal 2.0` to receive IPOs subscribed >=2x (use `/mintotal 0` to reset).
     - `/minretail <number>` — e.g. `/minretail 1.5` to filter by Retail (RII) subscription.
     - `/format <card|table>` — Choose between visual mobile cards or monospace table format.
     - `/columns <list>` — Customize columns (e.g. `/columns name,price,rii_lot_size,shni_lot_size,total,gmp`).
       - `rii_lot_size`: Calculated as `(15000 // price) * price` (multiple of price just below ₹15,000).
       - `shni_lot_size`: Multiple of `rii_lot_size` just above ₹2,00,000.
4. **Instant Testing (`/check`)**:
   - Users can send `/check` anytime to immediately fetch their personalized live report without waiting for the automatic schedule.
5. **Settings Review (`/myfilters`)**:
   - Displays a clean profile summary of the user's active filter configuration.
6. **Automated Time-Based Scheduler**:
   - Checks the local clock continuously and automatically triggers at **6:00 AM** and **6:00 PM**.
   - Evaluates each user's chosen frequency (`daily`, `alternate`, `thirdday`) and preferred time (`morning` vs `evening`).
   - Tab request batching: Scrapes each tab at most once per broadcast cycle to protect InvestorGain from excessive requests.


---

## 📋 Telegram App Setup (What you should do in Telegram)

Follow these simple steps inside your Telegram app:

### 1. Create Bot & Get Token via `@BotFather`
1. In Telegram, search for `@BotFather` and click **Start**.
2. Send `/newbot`.
3. Choose a name (e.g. `IPO Live Tracker`) and a unique username ending in `bot` (e.g. `MyIpoSubscriptionBot`).
4. Copy the **HTTP API Token** provided by BotFather.
5. Paste it into your [.env](file:///a:/08_Projects/PlayWright/GMP/.env) file:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   ```

### 2. Configure Bot Command Menu in Telegram
To make Telegram show the nice autocomplete menu whenever users type `/`, do this in `@BotFather`:
1. Send `/setcommands` to `@BotFather`.
2. Select your bot.
3. Copy and paste the entire block below into the chat:
```text
start - Welcome & Bot Introduction
add - Subscribe & view filter settings
remove - Unsubscribe from automatic updates
check - Get your custom IPO report right now
myfilters - View your active filter settings
daily - Receive data every day
alternate - Receive data every alternate day
thirdday - Receive data skipping 2 days in between
morning - Receive alerts at 6:00 AM Morning
evening - Receive alerts at 6:00 PM Evening
open - Filter for Open IPOs only
all - Filter for All IPOs
closing - Filter for IPOs closing today
sme - Filter for SME IPOs only
mainboard - Filter for Mainboard IPOs only
both - Both Mainboard & SME IPOs
mingmp - Set minimum GMP % (e.g. /mingmp 20)
mintotal - Set minimum Total subscription (e.g. /mintotal 2)
minretail - Set minimum Retail subscription
format - Change layout (/format card or /format table)
columns - Customize columns (/columns name,total,rii,gmp)
help - Show all available commands
```


### 3. (Optional) Enhance Bot Profile
In `@BotFather`:
- `/setdescription` — What people see when they open the chat before clicking Start.
- `/setabouttext` — Text in the bot's profile bio.
- `/setuserpic` — Upload an avatar / logo for the bot.

---

## 💻 Installation & Running

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Continuous Telegram Bot
```bash
python bot.py
```
*The bot will start long polling, handle incoming user commands in real time, and run the background broadcasting loop.*

---

## 🗄️ Project Architecture

```
.
├── bot.py                # Main Telegram Bot service (python-telegram-bot application)
├── database.py           # SQLite database for subscribers and user filter preferences
├── scraper.py            # InvestorGain live table scraper with Cloudflare deobfuscation
├── filters.py            # Row filtering and column projection engine
├── telegram_sender.py    # Formatter for Card and Monospace Table layouts
├── config.py             # Global configuration and environment settings
├── main.py               # Standalone CLI tool for manual/dry-run execution
├── requirements.txt      # Project dependencies
├── .env.example          # Environment variables template
└── subscribers.db        # Auto-created SQLite database file
```
