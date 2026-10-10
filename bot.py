import os
import re
import sqlite3
from pathlib import Path
from statistics import median
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

DB_PATH = Path(__file__).with_name("aviator.db")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        multiplier REAL NOT NULL CHECK(multiplier >= 1),
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        threshold REAL NOT NULL,
        estimated_probability REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        evaluated INTEGER NOT NULL DEFAULT 0,
        outcome INTEGER
    )""")
    con.commit()
    return con

def values(limit=10000):
    with db() as con:
        return [float(r[0]) for r in con.execute(
            "SELECT multiplier FROM rounds ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Aviator Risk Analyzer (1xBet history)\n\n"
        "I analyze observed history; I cannot know the exact next multiplier.\n\n"
        "/add 1.24 2.10 1.03 4.50 — add past results\n"
        "/stats — overall historical stats\n"
        "/risk — empirical frequencies for 2x/5x/10x\n"
        "/estimate 2 — log an estimate for whether a round reaches 2x\n"
        "/recent — latest 10 results\n"
        "/help — help"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = [p for p in re.split(r"[,;\s]+", " ".join(context.args).strip()) if p]
    if not parts:
        await update.message.reply_text("Example: /add 1.24 2.10 1.03 4.50")
        return
    try:
        nums = [float(p.lower().replace("x", "")) for p in parts]
    except ValueError:
        await update.message.reply_text("Numbers only, e.g. /add 1.24 2.10 4.50")
        return
    if any(n < 1 or n >= 100000 for n in nums):
        await update.message.reply_text("Each multiplier must be at least 1.00x.")
        return
    with db() as con:
        con.executemany("INSERT INTO rounds(multiplier,source) VALUES (?, 'telegram')",
                        [(n,) for n in nums])
    await update.message.reply_text(f"Saved {len(nums)} result(s). Use /stats or /risk.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = values()
    if not v:
        await update.message.reply_text("No data yet. Add results with /add 1.24 2.10 1.03")
        return
    lines = [
        f"Results recorded: {len(v)}",
        f"Median observed multiplier: {median(v):.2f}x",
        f"Below 1.50x: {sum(x < 1.5 for x in v)/len(v)*100:.1f}%",
        f"Below 2.00x: {sum(x < 2 for x in v)/len(v)*100:.1f}%",
        f"Reached 5.00x or more: {sum(x >= 5 for x in v)/len(v)*100:.1f}%",
        f"Reached 10.00x or more: {sum(x >= 10 for x in v)/len(v)*100:.1f}%",
    ]
    await update.message.reply_text("📈 Historical statistics\n\n" + "\n".join(lines) +
        "\n\nThese are past frequencies, not the probability of the next round.")

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = values()
    if not v:
        await update.message.reply_text("No data yet. Use /add to enter observed multipliers.")
        return
    lines = [f"Sample size: {len(v)} observed rounds"]
    for t in (2, 5, 10):
        p = sum(x >= t for x in v) / len(v) * 100
        lines.append(f"Observed rounds reaching {t}x+: {p:.1f}% ({sum(x >= t for x in v)}/{len(v)})")
    lines.append("\nHistorical sample frequencies do not predict the next result.")
    await update.message.reply_text("🧮 Empirical threshold frequencies\n\n" + "\n".join(lines))

async def estimate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /estimate 2 (records a baseline estimate for the next observed round)")
        return
    try:
        threshold = float(context.args[0].lower().replace("x", ""))
        if threshold <= 1 or threshold > 1000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Enter a threshold above 1, such as /estimate 2 or /estimate 5")
        return
    v = values()
    if len(v) < 30:
        await update.message.reply_text("Please record at least 30 results before logging a baseline estimate.")
        return
    # A transparent smoothed empirical baseline, not a claim about the next round.
    successes = sum(x >= threshold for x in v)
    p = (successes + 1) / (len(v) + 2)
    with db() as con:
        con.execute("INSERT INTO estimates(threshold, estimated_probability) VALUES (?, ?)", (threshold, p))
    await update.message.reply_text(
        f"Logged baseline estimate for threshold {threshold:g}x: {p*100:.1f}% based on {len(v)} historical results.\n"
        "This is an empirical baseline, not advance knowledge of the next multiplier. "
        "The current version does not yet automatically match estimates to round outcomes."
    )

async def recent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        rows = con.execute("SELECT multiplier,created_at FROM rounds ORDER BY id DESC LIMIT 10").fetchall()
    if not rows:
        await update.message.reply_text("No results yet.")
        return
    await update.message.reply_text("🕘 Latest results\n" + "\n".join(
        f"{i}. {float(r[0]):.2f}x — {r[1]}" for i, r in enumerate(rows, 1)
    ))

def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN as an environment variable.")
    db().close()
    app = ApplicationBuilder().token(TOKEN).build()
    for cmd, fn in [("start",start),("help",help_cmd),("add",add_cmd),
                    ("stats",stats_cmd),("risk",risk_cmd),("estimate",estimate_cmd),
                    ("recent",recent_cmd)]:
        app.add_handler(CommandHandler(cmd, fn))
    print("Aviator Risk Analyzer is running.")
    app.run_polling()

if __name__ == "__main__":
    main()
