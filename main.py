"""
Stock Monitor – runs every hour via GitHub Actions.
Pulls prices with yfinance, scores buy-the-dip opportunities,
and emails an HTML report when alert conditions are met.
"""

import os
import datetime as dt

import yfinance as yf
import pandas as pd
import numpy as np

# ──────────────────────────────────────────────
# 1.  TICKERS
# ──────────────────────────────────────────────
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "V", "JNJ",
    "WMT", "PG", "UNH", "HD", "MA",
]

# ──────────────────────────────────────────────
# 2.  CONFIG  (all from GitHub Secrets / env)
# ──────────────────────────────────────────────
EMAIL_SENDER   = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")      # Gmail App Password
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER", "")
SMTP_SERVER    = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT") or "587")

# ──────────────────────────────────────────────
# 3.  DATA HELPERS
# ──────────────────────────────────────────────
def fetch_data(ticker: str) -> dict | None:
    """Return a dict of metrics for one ticker, or None on failure."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")          # 1-year history
        if hist.empty or len(hist) < 5:
            print(f"  ⚠  {ticker}: not enough history")
            return None

        close = hist["Close"]
        current = close.iloc[-1]

        # --- period returns ---------------------------------------------------
        def pct_change_ago(days):
            subset = close[close.index <= close.index[-1]]
            if len(subset) >= days:
                old = subset.iloc[-days]
                return (current - old) / old * 100
            return np.nan

        day_1   = pct_change_ago(1)
        week_1  = pct_change_ago(5)
        month_1 = pct_change_ago(21)
        month_3 = pct_change_ago(63)
        month_6 = pct_change_ago(126)

        # --- 52-week low & high -----------------------------------------------
        low_52  = close.min()
        high_52 = close.max()
        dist_52_low = (current - low_52) / low_52 * 100   # how far above low

        # --- moving averages ---------------------------------------------------
        ma50  = close.rolling(50).mean().iloc[-1]  if len(close) >= 50  else np.nan
        ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan

        dist_below_ma50  = (current - ma50)  / ma50  * 100 if not np.isnan(ma50)  else np.nan
        dist_below_ma200 = (current - ma200) / ma200 * 100 if not np.isnan(ma200) else np.nan

        # --- buy-the-dip score  (0-100, higher = stronger dip signal) ----------
        score = _dip_score(
            day_1, week_1, month_1, dist_52_low,
            dist_below_ma50, dist_below_ma200,
        )

        return {
            "ticker":            ticker,
            "price":             round(current, 2),
            "1D %":              round(day_1,   2) if not np.isnan(day_1)   else None,
            "1W %":              round(week_1,  2) if not np.isnan(week_1)  else None,
            "1M %":              round(month_1, 2) if not np.isnan(month_1) else None,
            "3M %":              round(month_3, 2) if not np.isnan(month_3) else None,
            "6M %":              round(month_6, 2) if not np.isnan(month_6) else None,
            "52W Low":           round(low_52,  2),
            "52W High":          round(high_52, 2),
            "MA50":              round(ma50,  2)  if not np.isnan(ma50)  else None,
            "MA200":             round(ma200, 2)  if not np.isnan(ma200) else None,
            "Dist 52W Low %":    round(dist_52_low, 2),
            "Dist Below MA50 %": round(dist_below_ma50,  2) if not np.isnan(dist_below_ma50)  else None,
            "Dist Below MA200 %":round(dist_below_ma200, 2) if not np.isnan(dist_below_ma200) else None,
            "Dip Score":         score,
        }
    except Exception as exc:
        print(f"  ✗  {ticker}: {exc}")
        return None


def _dip_score(day_1, week_1, month_1, dist_52_low, dist_ma50, dist_ma200) -> int:
    """
    Composite 0-100 score.  Higher = deeper dip = better potential buy.
    Weights:  monthly drop 25, daily drop 15, weekly drop 15,
              proximity to 52w low 20, below MA50 15, below MA200 10.
    """
    s = 0

    # Monthly decline component (max 25 pts)
    if not np.isnan(month_1) and month_1 < 0:
        s += min(abs(month_1) * 1.25, 25)

    # Daily decline (max 15 pts)
    if not np.isnan(day_1) and day_1 < 0:
        s += min(abs(day_1) * 3, 15)

    # Weekly decline (max 15 pts)
    if not np.isnan(week_1) and week_1 < 0:
        s += min(abs(week_1) * 1.5, 15)

    # Near 52-week low (max 20 pts) – the closer, the higher the score
    if not np.isnan(dist_52_low):
        if dist_52_low < 5:
            s += 20
        elif dist_52_low < 10:
            s += 15
        elif dist_52_low < 20:
            s += 8

    # Below MA50 (max 15 pts)
    if not np.isnan(dist_ma50) and dist_ma50 < 0:
        s += min(abs(dist_ma50) * 1.5, 15)

    # Below MA200 (max 10 pts)
    if not np.isnan(dist_ma200) and dist_ma200 < 0:
        s += min(abs(dist_ma200), 10)

    return min(int(round(s)), 100)


# ──────────────────────────────────────────────
# 4.  ALERT LOGIC
# ──────────────────────────────────────────────
def should_alert(row: dict) -> tuple[bool, list[str]]:
    """
    Returns (True/False, [list of reasons]).

    Conditions:
      A) Monthly drop ≥ 10 % AND it did NOT rise ≥ 10 % in the past month
         AND it did NOT rise ≥ 5 % in the past week.
      B) Daily drop ≥ 5 % AND same recovery filters as A.
      C) Price within 2 % of 52-week low.
      D) Price below MA50.
      E) Price below MA200.
    """
    reasons = []
    m1  = row.get("1M %")
    d1  = row.get("1D %")
    w1  = row.get("1W %")

    # recovery filters – if either is True the dip may be a bounce, skip A/B
    monthly_recovery = (m1 is not None and m1 >= 10)
    weekly_recovery  = (w1 is not None and w1 >= 5)
    recovering = monthly_recovery or weekly_recovery

    if not recovering:
        if m1 is not None and m1 <= -10:
            reasons.append(f"Monthly decline {m1:+.1f}%")
        if d1 is not None and d1 <= -5:
            reasons.append(f"Daily drop {d1:+.1f}%")

    dist_low = row.get("Dist 52W Low %")
    if dist_low is not None and dist_low <= 2:
        reasons.append(f"Near 52-week low ({dist_low:+.1f}% above)")

    ma50 = row.get("Dist Below MA50 %")
    if ma50 is not None and ma50 < 0:
        reasons.append(f"Below MA50 ({ma50:+.1f}%)")

    ma200 = row.get("Dist Below MA200 %")
    if ma200 is not None and ma200 < 0:
        reasons.append(f"Below MA200 ({ma200:+.1f}%)")

    return (len(reasons) > 0, reasons)


# ──────────────────────────────────────────────
# 5.  EMAIL
# ──────────────────────────────────────────────
def _fmt(val, suffix="%"):
    """Format a value for the HTML table."""
    if val is None:
        return '<td style="text-align:center;color:#999">—</td>'
    color = "#e74c3c" if val < 0 else "#27ae60" if val > 0 else "#333"
    return f'<td style="text-align:right;color:{color}">{val:+.2f}{suffix}</td>'


def build_email_html(rows: list[dict], alert_map: dict[str, list[str]]) -> str:
    """Build a full HTML email body."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- summary table (all 15 tickers) ----
    table_rows = ""
    for r in rows:
        tk = r["ticker"]
        alert_flag = ""  # no icon
        dip = r["Dip Score"]
        dip_color = (
            "#e74c3c" if dip >= 60 else
            "#e67e22" if dip >= 35 else
            "#27ae60"
        )
        table_rows += f"""<tr>
            <td style="font-weight:600">{tk}</td>
            <td style="text-align:right">${r['price']:.2f}</td>
            {_fmt(r['6M %'])}
            {_fmt(r['3M %'])}
            {_fmt(r['1M %'])}
            {_fmt(r['1D %'])}
            <td style="text-align:center;font-weight:700;color:{dip_color}">{dip}</td>
            {_fmt(r['Dist Below MA50 %'])}
            {_fmt(r['Dist Below MA200 %'])}
        </tr>"""

    # ---- alert details ----
    alert_section = ""
    if alert_map:
        items = "".join(
            f"<li><strong>{tk}</strong>: {', '.join(reasons)}</li>"
            for tk, reasons in alert_map.items()
        )
        alert_section = f"""
        <h3 style="color:#e74c3c;margin-top:28px">⚠️ Alert Details</h3>
        <ul>{items}</ul>
        """

    html = f"""\
    <html><body style="font-family:Arial,Helvetica,sans-serif;color:#222;max-width:960px;margin:auto">
    <h2 style="margin-bottom:4px">📊 Stock Dip Monitor</h2>
    <p style="color:#888;margin-top:0">{now}</p>

    <div style="overflow-x:auto">
    <table style="border-collapse:collapse;font-size:13px;width:100%">
      <thead>
        <tr style="background:#f5f6fa">
          <th style="padding:8px;text-align:left">Ticker</th>
          <th style="padding:8px;text-align:right">Price</th>
          <th style="padding:8px;text-align:right">6M %</th>
          <th style="padding:8px;text-align:right">3M %</th>
          <th style="padding:8px;text-align:right">1M %</th>
          <th style="padding:8px;text-align:right">1D %</th>
          <th style="padding:8px;text-align:center">Dip Score</th>
          <th style="padding:8px;text-align:right">Dist &lt; MA50</th>
          <th style="padding:8px;text-align:right">Dist &lt; MA200</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
    </div>

    {alert_section}

    <hr style="margin-top:32px;border:none;border-top:1px solid #ddd">
    <p style="font-size:11px;color:#aaa">
      Dip Score 0-100 (higher = deeper dip). Alerts fire when monthly
      drop ≥10 %, daily drop ≥5 % (excluding recovery bounces), near
      52-week low, or below MA50/MA200.
    </p>
    </body></html>
    """
    return html

def send_email(subject: str, html_body: str):
    """Send an HTML email via SMTP SSL (Gmail by default)."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("  ⚠  Email credentials not configured – skipping send.")
        print("     Set EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER env vars.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER.split(","), msg.as_string())
        print("  ✓  Email sent successfully.")
    except Exception as e:
        print(f"  ✗  Email failed: {e}")


# ──────────────────────────────────────────────
# 6.  MAIN
# ──────────────────────────────────────────────
def main():
    print(f"{'='*60}")
    print(f"  Stock Dip Monitor  –  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}")
    print(f"{'='*60}\n")

    rows: list[dict] = []
    for tk in TICKERS:
        print(f"  Fetching {tk} …")
        data = fetch_data(tk)
        if data:
            rows.append(data)

    if not rows:
        print("\n  ✗  No data fetched – exiting.")
        return

    # Evaluate alerts
    alert_map: dict[str, list[str]] = {}
    for r in rows:
        triggered, reasons = should_alert(r)
        if triggered:
            alert_map[r["ticker"]] = reasons
            print(f"  🔔 ALERT  {r['ticker']}: {', '.join(reasons)}")

    # Build & send email
    n_alerts = len(alert_map)
    subject = (
        f"🔔 {n_alerts} Stock Alert{'s' if n_alerts != 1 else ''} – Dip Monitor"
        if n_alerts
        else "📊 Stock Dip Monitor – No Alerts"
    )
    html = build_email_html(rows, alert_map)

    # Always send the summary email so you see the table.
    # To only email on alerts, uncomment the next line:
    # if not alert_map: return
    with open("email_subject.txt", "w") as f:
        f.write(subject)
    with open("email_body.html", "w") as f:
        f.write(html)
    print("  ✓  Email files written.")
    # Print summary table to Actions log
    print(f"\n{'─'*60}")
    df = pd.DataFrame(rows)[["ticker", "price", "6M %", "3M %", "1M %", "1D %", "Dip Score"]]
    print(df.to_string(index=False))
    print(f"{'─'*60}")
    print(f"\n  Done.  {n_alerts} alert(s) fired.\n")


if __name__ == "__main__":
    main()
