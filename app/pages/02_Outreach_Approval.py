from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.actions.approval import ProposedAction
from app.actions.executor import ActionExecutor
from app.outreach_queue import OutreachQueueStore
from app.runtime import RuntimeConfig


st.set_page_config(page_title="Outreach Approval", page_icon="📤", layout="wide")
runtime = RuntimeConfig.from_env()
store = OutreachQueueStore()

st.title("Outreach Approval")
st.caption("P0/P1企業への営業案を、根拠を確認してから承認・却下します。")

queue = store.load_queue()
decisions = store.load_decisions()

if not queue:
    st.info("営業承認キューはまだありません。先にDiscovery / Research / Outreach Plannerを実行してください。")
    st.stop()

ready = [x for x in queue if x.get("status") == "ready_for_approval"]
blocked = [x for x in queue if x.get("status") != "ready_for_approval"]

m1, m2, m3 = st.columns(3)
m1.metric("承認待ち", len(ready))
m2.metric("ブロック", len(blocked))
m3.metric("全候補", len(queue))

filter_priority = st.selectbox("優先度", ["ALL", "P0", "P1"], index=0)
plans = queue if filter_priority == "ALL" else [x for x in queue if x.get("priority") == filter_priority]

for idx, plan in enumerate(plans):
    key = store.key(plan)
    decision = decisions.get(key)
    company = str(plan.get("company_name", ""))
    priority = str(plan.get("priority", ""))
    score = plan.get("score")
    channel = str(plan.get("channel", ""))

    with st.expander(f"[{priority}] {company} / Score {score}", expanded=idx == 0):
        c1, c2, c3 = st.columns(3)
        c1.metric("Priority", priority)
        c2.metric("Score", score if score is not None else "-")
        c3.metric("Channel", channel)

        if plan.get("status") != "ready_for_approval":
            st.warning(f"営業停止: {plan.get('block_reason','理由未設定')}")
            continue

        st.subheader("提案仮説")
        st.write(plan.get("value_proposition", ""))

        st.subheader("使用した検証済み根拠")
        evidence = plan.get("evidence_used") or []
        if evidence:
            for item in evidence:
                st.write(f"- {item}")
        else:
            st.warning("根拠がありません。承認しないでください。")

        sources = plan.get("source_urls") or []
        if sources:
            st.caption("Sources")
            for url in sources:
                st.code(url, language=None)

        st.subheader("営業文案")
        if plan.get("subject"):
            st.text_input("件名", value=str(plan.get("subject", "")), disabled=True, key=f"subj_{idx}")
        st.text_area("本文", value=str(plan.get("message", "")), height=220, disabled=True, key=f"msg_{idx}")
        st.write("**接触先:**", plan.get("contact_target", ""))

        if decision:
            status = decision.get("status")
            if status == "approved_demo":
                st.success("承認済み（デモ）")
            elif status == "gmail_draft_created":
                st.success("承認済み・Gmail下書き作成済み")
            elif status == "approved_manual_web":
                st.success("承認済み・Web問い合わせ送信準備済み")
            elif status == "rejected":
                st.warning("却下済み")
            continue

        approve_col, reject_col = st.columns(2)
        with approve_col:
            if st.button("承認", type="primary", use_container_width=True, key=f"oa_{idx}"):
                if runtime.is_demo:
                    store.save_decision(plan, "approved_demo")
                    st.rerun()

                if channel == "email" and "@" in str(plan.get("contact_target", "")):
                    action = ProposedAction(
                        action_type="gmail_draft",
                        payload={
                            "to": plan.get("contact_target"),
                            "subject": plan.get("subject", ""),
                            "body": plan.get("message", ""),
                            "thread_id": None,
                        },
                        reason=f"P0/P1 prospect outreach approved for {company}",
                    )
                    action.approve()
                    try:
                        ActionExecutor().execute(action)
                        store.save_decision(plan, "gmail_draft_created")
                    except Exception as exc:
                        st.error(f"Gmail下書き作成に失敗しました: {exc}")
                        st.stop()
                elif channel == "web_contact":
                    store.save_decision(plan, "approved_manual_web")
                else:
                    st.error("検証済みの実行可能な接触チャネルがありません。")
                    st.stop()
                st.rerun()

        with reject_col:
            if st.button("却下", use_container_width=True, key=f"or_{idx}"):
                store.save_decision(plan, "rejected")
                st.rerun()
