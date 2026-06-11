# 📊 Stock Dip Monitor

Automated stock monitoring that runs every hour via GitHub Actions, tracks 15 tickers, scores buy-the-dip opportunities, and emails you an HTML report.

---

## What It Does

| Feature | Details |
|---------|---------|
| **Tickers** | XXXX,YYY |
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
