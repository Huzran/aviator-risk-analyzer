import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("aviator.db")
st.set_page_config(page_title="Aviator Risk Analyzer", page_icon="📊", layout="wide")

def connect():
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

def load():
    with connect() as con:
        return pd.read_sql_query("SELECT id,multiplier,source,created_at FROM rounds ORDER BY id DESC", con)

st.title("📊 Aviator Risk Analyzer")
st.caption("1xBet history tracker • descriptive statistics, not exact prediction")
with st.sidebar:
    st.subheader("Add observed rounds")
    raw = st.text_area("Multipliers separated by commas/spaces", placeholder="1.24, 2.10, 1.03, 4.50")
    if st.button("Save results", use_container_width=True):
        try:
            import re
            nums = [float(x.lower().replace("x","")) for x in re.split(r"[,;\s]+",raw.strip()) if x]
            if not nums or any(x < 1 or x >= 100000 for x in nums):
                st.error("Enter valid multipliers, each at least 1.00x.")
            else:
                with connect() as con:
                    con.executemany("INSERT INTO rounds(multiplier,source) VALUES (?, 'dashboard')",[(x,) for x in nums])
                st.success(f"Saved {len(nums)} result(s).")
                st.rerun()
        except ValueError:
            st.error("Use numbers only.")
    if st.button("Delete all history", use_container_width=True):
        with connect() as con:
            con.execute("DELETE FROM rounds")
        st.rerun()

df = load()
if df.empty:
    st.info("Add historical results in the sidebar or via Telegram /add.")
    st.code("/add 1.24 2.10 1.03 4.50")
    st.stop()

v = df["multiplier"].astype(float)
a,b,c,d = st.columns(4)
a.metric("Rounds recorded",len(v))
b.metric("Median multiplier",f"{v.median():.2f}x")
c.metric("Below 2x",f"{(v<2).mean()*100:.1f}%")
d.metric("Reached 10x+",f"{(v>=10).mean()*100:.1f}%")

st.subheader("Recent results")
plot = df.head(100).iloc[::-1].copy()
plot["Round (record order)"] = range(1,len(plot)+1)
st.line_chart(plot.set_index("Round (record order)")["multiplier"],y_label="Multiplier (x)")

st.subheader("Observed threshold frequencies")
thresholds = [2,3,5,10]
freq = pd.DataFrame({
    "Threshold":[f"{t}x+" for t in thresholds],
    "Observed frequency (%)":[(v>=t).mean()*100 for t in thresholds],
    "Count":[int((v>=t).sum()) for t in thresholds],
    "Sample size":[len(v)]*len(thresholds)
})
st.dataframe(freq,use_container_width=True,hide_index=True)
st.subheader("Latest 50 saved rounds")
latest = df.head(50).copy()
latest["multiplier"] = latest["multiplier"].map(lambda x:f"{x:.2f}x")
st.dataframe(latest,use_container_width=True,hide_index=True)
st.warning("Past multipliers do not reveal the next crash point. Streaks are not proof that a high or low result is due. This app does not place bets or claim exact predictions.")
