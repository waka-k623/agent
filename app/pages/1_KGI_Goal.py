from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.goals import GoalEngine, SalesMetrics

st.set_page_config(page_title="Sales Agent KGI", page_icon="🎯", layout="wide")

engine = GoalEngine()
goal = engine.load_or_create()

st.title("🎯 Sales Agent KGI")
st.caption("KGIから営業KPIと今日の優先タスクを逆算します。")

st.subheader(goal.title)
meta1, meta2, meta3 = st.columns(3)
meta1.metric("期限", goal.target_date)
meta2.metric("目標受注", f"{goal.target_wins}件以上")
meta3.metric("残り日数", f"{engine.days_remaining(goal)}日")

st.divider()
st.subheader("現在の営業実績")
st.caption("現段階では手動入力です。次の段階でCRM・営業実行ログから自動集計します。")

if "goal_metrics" not in st.session_state:
    st.session_state.goal_metrics = {
        "prospects": 0,
        "outreaches": 0,
        "replies": 0,
        "meetings": 0,
        "proposals": 0,
        "wins": 0,
    }

labels = [
    ("prospects", "見込み企業"),
    ("outreaches", "営業接触"),
    ("replies", "返信"),
    ("meetings", "商談"),
    ("proposals", "提案"),
    ("wins", "受注"),
]
cols = st.columns(6)
for col, (key, label) in zip(cols, labels):
    st.session_state.goal_metrics[key] = col.number_input(
        label,
        min_value=0,
        value=int(st.session_state.goal_metrics[key]),
        step=1,
        key=f"metric_{key}",
    )

actual = SalesMetrics(**st.session_state.goal_metrics)
evaluation = engine.evaluate(goal, actual)
targets = evaluation["targets"]

st.divider()
st.subheader("KPIファネル")
cols = st.columns(6)
for col, (key, label) in zip(cols, labels):
    current = st.session_state.goal_metrics[key]
    target = targets[key]
    col.metric(label, f"{current} / {target}", delta=f"残り {max(target-current, 0)}")

health = evaluation["health"]
if health == "achieved":
    st.success("KGI達成済みです。勝ちパターンを記録して再現性を高めます。")
elif health == "at_risk":
    st.error("KGI達成ペースにリスクがあります。Agentが改善を優先します。")
else:
    st.info("KGI達成に向けて進行中です。")

st.write("**Agentの現在の重点判断:**", evaluation["next_focus"])

st.divider()
st.subheader("今日のAgentタスク")
for i, task in enumerate(engine.daily_plan(goal, actual), start=1):
    st.checkbox(task, key=f"daily_task_{i}")

st.caption("このタスク一覧は現在のKPI実績から毎回再生成されます。")
