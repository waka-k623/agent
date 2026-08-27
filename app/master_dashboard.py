from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.auth import UserContext
from app.demo_data import build_demo_queue
from app.goals import GoalEngine
from app.master_agent import MasterAgent
from app.runtime import RuntimeConfig

DATA = Path("data")
runtime = RuntimeConfig.from_env()

st.set_page_config(page_title="Master Sales Agent", page_icon="🤖", layout="wide")


def read_json(name: str, default: Any) -> Any:
    path = DATA / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def demo_dashboard() -> dict[str, Any]:
    return {
        "goal": {
            "title": "福井県の中小企業から1件以上受注する",
            "target_date": "2026-09-27",
            "target_wins": 1,
        },
        "funnel": {
            "prospects": 18,
            "outreaches": 7,
            "replies": 3,
            "meetings": 1,
            "proposals": 0,
            "wins": 0,
        },
        "revenue": {
            "open_pipeline_yen": 420000,
            "expected_revenue_yen": 180000,
            "won_revenue_yen": 0,
        },
        "pdca": {
            "health": "in_progress",
            "focus": "返信済み企業から商談化を優先する",
            "rates": {"reply_rate": 42.9, "meeting_rate_from_replies": 33.3},
        },
        "today": [
            "P0/P1候補の不足根拠を再調査",
            "返信済み1社へ商談CTAを準備",
            "承認待ち営業文を確認",
        ],
        "approvals": 3,
        "master_status": "demo",
    }


def live_dashboard() -> dict[str, Any]:
    goal = GoalEngine().load_or_create()
    executive = read_json("latest_executive_dashboard.json", {})
    pdca_file = read_json("latest_daily_sales_cycle.json", {})
    master = read_json("latest_master_agent_cycle.json", {})
    approvals = read_json("outreach_approval_queue.json", [])
    if isinstance(approvals, dict):
        approvals = approvals.get("items") or approvals.get("records") or []

    funnel = executive.get("funnel") or pdca_file.get("pdca", {}).get("actual") or {}
    revenue = executive.get("revenue") or {}
    pdca = pdca_file.get("pdca") or executive.get("pdca") or {}
    next_actions = master.get("next_human_actions") or pdca_file.get("next_actions") or []

    return {
        "goal": {"title": goal.title, "target_date": goal.target_date, "target_wins": goal.target_wins},
        "funnel": funnel,
        "revenue": revenue,
        "pdca": pdca,
        "today": next_actions,
        "approvals": len(approvals),
        "master_status": master.get("status", "not_run"),
    }


if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = runtime.demo_mode_default or runtime.is_demo

if st.session_state.current_user is None:
    st.title("Master Sales Agent")
    st.caption("KGIから企業発掘・営業・追客・PDCAまでを統合管理します。")
    if runtime.is_demo:
        st.info("公開デモです。実際のメール送信や外部サービスへの書き込みは行いません。")
        if st.button("デモを開始", type="primary", use_container_width=True):
            st.session_state.current_user = UserContext(
                username="demo", role="admin", company_id="default", display_name="Demo User"
            )
            st.rerun()
    else:
        st.warning("本番ログインは既存認証画面を使用してください。")
    st.stop()

st.sidebar.title("Master Sales Agent")
st.sidebar.caption("Goal-driven sales operating system")
st.sidebar.write(f"ログイン: **{st.session_state.current_user.display_name or st.session_state.current_user.username}**")

if runtime.is_demo:
    st.session_state.demo_mode = True
    st.sidebar.toggle("デモモード", value=True, disabled=True)
else:
    st.session_state.demo_mode = st.sidebar.toggle("デモモード", value=st.session_state.demo_mode)

if st.sidebar.button("ログアウト", use_container_width=True):
    st.session_state.current_user = None
    st.rerun()

page = st.sidebar.radio(
    "メニュー",
    ["Command Center", "承認キュー", "Pipeline & Revenue", "PDCA", "System"],
)

state = demo_dashboard() if st.session_state.demo_mode else live_dashboard()

st.title("Master Sales Agent")
st.caption("KGI → Research → Sales → Follow-up → Deal → PDCA を1つの画面で管理")

if page == "Command Center":
    goal = state["goal"]
    st.subheader("KGI")
    st.info(f"{goal['target_date']}までに「{goal['title']}」")

    f = state["funnel"]
    cols = st.columns(6)
    labels = [
        ("見込み企業", "prospects"),
        ("営業接触", "outreaches"),
        ("返信", "replies"),
        ("商談", "meetings"),
        ("提案", "proposals"),
        ("受注", "wins"),
    ]
    for col, (label, key) in zip(cols, labels):
        col.metric(label, int(f.get(key, 0) or 0))

    st.divider()
    left, right = st.columns([1.4, 1])
    with left:
        st.subheader("今日のAgentタスク")
        tasks = state.get("today") or ["次の自動サイクルを実行してタスクを生成"]
        for i, task in enumerate(tasks, 1):
            st.write(f"{i}. {task}")

        if not st.session_state.demo_mode:
            if st.button("Master Agentを実行", type="primary", use_container_width=True):
                with st.spinner("Master Agentを実行しています..."):
                    report = MasterAgent().run()
                if report.get("status") == "ok":
                    st.success("Master Agentサイクルを完了しました。")
                else:
                    st.error("一部工程でエラーが発生しました。System画面で確認してください。")
                st.rerun()
        else:
            st.button("Master Agentを実行（デモ）", disabled=True, use_container_width=True)

    with right:
        st.subheader("現在の判断")
        pdca = state.get("pdca") or {}
        health = pdca.get("health", "unknown")
        st.metric("KGI Health", str(health).upper())
        st.write("**重点施策**")
        st.write(pdca.get("focus") or "実績データ待ち")
        st.metric("承認待ち", state.get("approvals", 0))

    st.divider()
    st.subheader("自律ループ")
    stages = ["発掘", "2回検証", "P0/P1", "営業案", "承認", "返信監視", "追客/商談", "競合/価格", "PDCA"]
    st.write(" → ".join(stages))

elif page == "承認キュー":
    st.subheader("承認待ちアクション")
    if st.session_state.demo_mode:
        queue = build_demo_queue()
        for idx, item in enumerate(queue[:3]):
            analysis = item.get("analysis", {})
            with st.container(border=True):
                st.write(f"**{analysis.get('subject', '営業アクション')}**")
                st.caption(f"優先度: {str(analysis.get('priority','medium')).upper()}")
                st.write(analysis.get("next_action", "営業内容を確認"))
                c1, c2 = st.columns(2)
                c1.button("承認（デモ）", key=f"demo_approve_{idx}", use_container_width=True)
                c2.button("却下（デモ）", key=f"demo_reject_{idx}", use_container_width=True)
    else:
        queue = read_json("outreach_approval_queue.json", [])
        if isinstance(queue, dict):
            queue = queue.get("items") or queue.get("records") or []
        if not queue:
            st.info("現在、承認待ちはありません。")
        for idx, item in enumerate(queue):
            with st.container(border=True):
                st.write(f"**{item.get('company_name', '案件')}**")
                st.write(f"優先度: {item.get('priority', '')} / 状態: {item.get('status', '')}")
                st.write(item.get("message") or item.get("body") or item.get("reason") or "")
                st.caption("実行は既存の承認・ActionExecutorフローで行います。")

elif page == "Pipeline & Revenue":
    st.subheader("営業ファネル")
    f = state["funnel"]
    cols = st.columns(6)
    for col, (label, key) in zip(cols, labels):
        col.metric(label, int(f.get(key, 0) or 0))

    st.subheader("売上予測")
    revenue = state.get("revenue") or {}
    r1, r2, r3 = st.columns(3)
    r1.metric("Open Pipeline", f"¥{int(revenue.get('open_pipeline_yen', 0) or 0):,}")
    r2.metric("Expected Revenue", f"¥{int(revenue.get('expected_revenue_yen', 0) or 0):,}")
    r3.metric("Won Revenue", f"¥{int(revenue.get('won_revenue_yen', 0) or 0):,}")
    st.caption("期待売上は、明示された案件確率と提案価格が存在する案件のみ集計します。")

elif page == "PDCA":
    st.subheader("PDCA Engine")
    pdca = state.get("pdca") or {}
    st.metric("Health", str(pdca.get("health", "unknown")).upper())
    st.write("**現在の重点施策**")
    st.info(pdca.get("focus") or "実績データ待ち")
    rates = pdca.get("rates") or {}
    if rates:
        cols = st.columns(max(1, len(rates)))
        for col, (key, value) in zip(cols, rates.items()):
            col.metric(key.replace("_", " ").title(), "-" if value is None else f"{value}%")
    experiments = pdca.get("experiments") or []
    if experiments:
        st.subheader("改善実験")
        for exp in experiments:
            with st.container(border=True):
                st.write("**仮説:**", exp.get("hypothesis", ""))
                st.write("**テスト:**", exp.get("test", ""))

elif page == "System":
    st.subheader("System Status")
    master = read_json("latest_master_agent_cycle.json", {}) if not st.session_state.demo_mode else {}
    cap = master.get("capabilities", {})
    if st.session_state.demo_mode:
        cap = {"web_research": False, "ai_reasoning": False, "google_tracking": False, "persistent_memory": True}
    for key, value in cap.items():
        (st.success if value else st.warning)(f"{'READY' if value else 'MISSING'} — {key}")

    st.subheader("Guardrails")
    st.write("• 架空数値の生成禁止")
    st.write("• リサーチは最低2回検証")
    st.write("• P0/P1のみ営業対象")
    st.write("• 外部送信は人間承認")
    st.write("• 顧客提示価格も人間承認")
    st.write("• 過去Memoryを次サイクルへ再利用")

    if master.get("steps"):
        st.subheader("最新Master Cycle")
        for step in master["steps"]:
            icon = "✅" if step.get("status") == "ok" else "⏭️" if step.get("status") == "skipped" else "❌"
            st.write(f"{icon} {step.get('step')} — {step.get('status')}")
