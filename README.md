# 📊 Stock Dip Monitor

Automated stock monitoring that runs every hour via GitHub Actions, tracks 15 tickers, scores buy-the-dip opportunities, and emails you an HTML report.

---

## What It Does

| Feature | Details |
|---------|---------|
| **Tickers** | AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, JNJ, WMT, PG, UNH, HD, MA |
| **Schedule** | Every hour Mon–Fri, 12:00–22:00 UTC (covers US market hours) |
| **Data** | yfinance (free, no API key needed) |
| **Alerts** | Email with full HTML table |

### Alert Conditions

An alert fires for a ticker when **any** of these are true (and the stock is *not* bouncing back):

1. **Monthly drop ≥ 10 %** — unless the month is up ≥ 10 % or the week is up ≥ 5 %
2. **Daily drop ≥ 5 %** — same recovery filter
3. **Within 2 % of 52-week low**
4. **Below 50-day moving average**
5. **Below 200-day moving average**

### Email Contents

- Summary table: Ticker, Price, 6M / 3M / 1M / 1D % change
- **Buy-the-Dip Score** (0–100, higher = deeper dip)
- Monthly decline column
- Distance from 52-week low
- Distance below MA50
- Distance below MA200
- Alert detail section listing every triggered reason

---

## Setup (5 minutes)

### 1. Create the repo

```bash
git init stock-monitor && cd stock-monitor
# copy the project files in, then:
git add -A && git commit -m "initial commit"
git remote add origin git@github.com:YOUR_USER/stock-monitor.git
git push -u origin main
```

### 2. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|--------|-------|
| `EMAIL_SENDER` | your-email@gmail.com |
| `EMAIL_PASSWORD` | Gmail **App Password** (not your login password) |
| `EMAIL_RECEIVER` | recipient@example.com (comma-separated for multiple) |
| `SMTP_SERVER` | `smtp.gmail.com` *(optional, this is the default)* |
| `SMTP_PORT` | `587` *(optional, this is the default)* |

#### Getting a Gmail App Password

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already on
3. Search "App passwords" → generate one for "Mail"
4. Copy the 16-character password into the `EMAIL_PASSWORD` secret

### 3. Run it

- **Automatic:** It will run on the cron schedule once pushed.
- **Manual:** Go to **Actions → Stock Dip Monitor → Run workflow**.

---

## Customization

### Change tickers

Edit the `TICKERS` list at the top of `main.py`:

```python
TICKERS = [
    "AAPL", "MSFT", "GOOGL",  # ... your picks
]
```

### Only email when alerts fire

Uncomment this line in `main()`:

```python
# if not alert_map: return
```

### Change the schedule

Edit the cron in `.github/workflows/stock_monitor.yml`:

```yaml
- cron: "0 12-22 * * 1-5"   # current: hourly Mon-Fri 12-22 UTC
- cron: "0 */2 * * *"        # example: every 2 hours, all days
```

---

## Local Testing

```bash
pip install -r requirements.txt

# without email (just prints to console):
python main.py

# with email:
export EMAIL_SENDER="you@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"
export EMAIL_RECEIVER="you@gmail.com"
python main.py
```

---

## Buy-the-Dip Score Breakdown

| Component | Max Points | Logic |
|-----------|-----------|-------|
| Monthly decline | 25 | 1.25 × abs(monthly %) |
| Daily decline | 15 | 3 × abs(daily %) |
| Weekly decline | 15 | 1.5 × abs(weekly %) |
| Near 52-week low | 20 | < 5 % above → 20 pts, < 10 % → 15, < 20 % → 8 |
| Below MA50 | 15 | 1.5 × abs(distance %) |
| Below MA200 | 10 | 1 × abs(distance %) |
| **Total** | **100** | |
