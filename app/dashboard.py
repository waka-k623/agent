from __future__ import annotations

from typing import Any

import streamlit as st

from app.actions.approval import ProposedAction
from app.actions.executor import ActionExecutor
from app.company_config import CompanyConfigStore
from app.workflows.review_queue import SalesReviewQueue

st.set_page_config(page_title="Sales Agent Review", page_icon="🤖", layout="wide")

st.title("Sales Agent Review")
st.caption("営業案件を確認し、AIが提案した外部アクションを承認または却下します。")

if "queue" not in st.session_state:
    st.session_state.queue = []
if "decisions" not in st.session_state:
    st.session_state.decisions = {}
if "company_id" not in st.session_state:
    st.session_state.company_id = "default"

store = CompanyConfigStore()
company_ids = store.list_company_ids() or ["default"]
selected_company = st.selectbox(
    "会社設定",
    options=company_ids,
    index=company_ids.index(st.session_state.company_id)
    if st.session_state.company_id in company_ids
    else 0,
)

if selected_company != st.session_state.company_id:
    st.session_state.company_id = selected_company
    st.session_state.queue = []
    st.session_state.decisions = {}

try:
    company = store.load(st.session_state.company_id)
    st.caption(f"現在の設定: {company.company_name} / {company.industry}")
except Exception:
    company = None


def refresh_queue() -> None:
    with st.spinner("Gmail / Contacts / CRM / Calendar を確認しています..."):
        st.session_state.queue = SalesReviewQueue(
            company_id=st.session_state.company_id
        ).build(max_results=10)
        st.session_state.decisions = {}


def proposed_action_from_dict(data: dict[str, Any]) -> ProposedAction:
    return ProposedAction(
        action_type=data["action_type"],
        payload=data.get("payload", {}),
        reason=data.get("reason", ""),
        id=data.get("id"),
        approved=bool(data.get("approved", False)),
    )


col1, col2 = st.columns([1, 4])
with col1:
    if st.button("受信箱を分析", type="primary", use_container_width=True):
        refresh_queue()
with col2:
    st.info("承認ボタンを押すまで、Gmail・Calendar・CRMへの書き込みは実行されません。")

queue = st.session_state.queue

if not queue:
    st.write("まだ分析結果がありません。『受信箱を分析』を押してください。")
    st.stop()

for index, item in enumerate(queue):
    analysis = item.get("analysis", {})
    actions = item.get("proposed_actions", [])

    priority = str(analysis.get("priority", "low")).upper()
    sender = analysis.get("sender", "")
    subject = analysis.get("subject", "(件名なし)")

    with st.expander(f"[{priority}] {subject} — {sender}", expanded=index == 0):
        a, b, c = st.columns(3)
        a.metric("優先度", priority)
        b.metric("分類", str(analysis.get("category", "other")))
        c.metric("営業対象", "Yes" if analysis.get("sales_relevant") else "No")

        st.subheader("Agentの判断")
        st.write(analysis.get("current_status", ""))
        st.write("**理由:**", analysis.get("reasoning_summary", ""))
        st.write("**次のアクション:**", analysis.get("next_action", ""))
        st.write("**推奨タイミング:**", analysis.get("recommended_timing", ""))

        if analysis.get("draft_message"):
            st.text_area(
                "返信案",
                value=str(analysis.get("draft_message", "")),
                height=180,
                disabled=True,
                key=f"draft_{index}",
            )

        st.subheader("承認待ちアクション")
        if not actions:
            st.caption("この案件には外部実行の提案はありません。")
            continue

        for action_index, action_data in enumerate(actions):
            action_id = action_data.get("id", f"{index}-{action_index}")
            decision = st.session_state.decisions.get(action_id)

            with st.container(border=True):
                st.write(f"**{action_data.get('action_type', '')}**")
                st.caption(action_data.get("reason", ""))
                st.json(action_data.get("payload", {}), expanded=False)

                if decision:
                    if decision.get("status") == "executed":
                        st.success(f"承認・実行済み: {decision.get('result')}")
                    elif decision.get("status") == "rejected":
                        st.warning("却下済み")
                    elif decision.get("status") == "error":
                        st.error(f"実行エラー: {decision.get('error')}")
                    continue

                approve_col, reject_col = st.columns(2)
                with approve_col:
                    if st.button(
                        "承認して実行",
                        type="primary",
                        use_container_width=True,
                        key=f"approve_{action_id}",
                    ):
                        action = proposed_action_from_dict(action_data)
                        action.approve()
                        try:
                            result = ActionExecutor().execute(action)
                            st.session_state.decisions[action_id] = {
                                "status": "executed",
                                "result": result,
                            }
                        except Exception as exc:
                            st.session_state.decisions[action_id] = {
                                "status": "error",
                                "error": str(exc),
                            }
                        st.rerun()

                with reject_col:
                    if st.button(
                        "却下",
                        use_container_width=True,
                        key=f"reject_{action_id}",
                    ):
                        st.session_state.decisions[action_id] = {"status": "rejected"}
                        st.rerun()
