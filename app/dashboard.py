from __future__ import annotations

from typing import Any

import streamlit as st

from app.actions.approval import ProposedAction
from app.actions.executor import ActionExecutor
from app.audit import AuditLogger
from app.auth import UserContext
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
if "actor" not in st.session_state:
    st.session_state.actor = "local_user"
if "role" not in st.session_state:
    st.session_state.role = "user"

store = CompanyConfigStore()
audit = AuditLogger()
company_ids = store.list_company_ids() or ["default"]

st.session_state.actor = st.sidebar.text_input(
    "操作者",
    value=st.session_state.actor,
    help="監査ログに記録する操作者名です。企業導入時はログインユーザーIDに置き換えます。",
)
st.session_state.role = st.sidebar.selectbox(
    "権限",
    options=["user", "admin"],
    index=0 if st.session_state.role == "user" else 1,
    format_func=lambda value: "一般ユーザー" if value == "user" else "管理者",
)
user = UserContext(
    username=st.session_state.actor or "unknown",
    role=st.session_state.role,
)

if user.can_manage_company_settings():
    sidebar_company = st.sidebar.selectbox(
        "会社設定",
        options=company_ids,
        index=company_ids.index(st.session_state.company_id)
        if st.session_state.company_id in company_ids
        else 0,
    )
else:
    sidebar_company = st.session_state.company_id
    st.sidebar.caption(f"会社設定: {sidebar_company}")

if sidebar_company != st.session_state.company_id:
    st.session_state.company_id = sidebar_company
    st.session_state.queue = []
    st.session_state.decisions = {}

try:
    company = store.load(st.session_state.company_id)
    st.sidebar.caption(f"{company.company_name} / {company.industry}")
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


if user.can_view_audit_log():
    review_tab, audit_tab = st.tabs(["承認キュー", "監査ログ"])
else:
    review_tab = st.container()
    audit_tab = None

with review_tab:
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("受信箱を分析", type="primary", use_container_width=True):
            refresh_queue()
    with col2:
        st.info("承認ボタンを押すまで、Gmail・Calendar・CRMへの書き込みは実行されません。")

    queue = st.session_state.queue

    if not queue:
        st.write("まだ分析結果がありません。『受信箱を分析』を押してください。")
    else:
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

                        if not user.can_approve_actions():
                            st.warning("このユーザーには承認権限がありません。")
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
                                audit.log(
                                    event_type="approval",
                                    company_id=st.session_state.company_id,
                                    action_id=action.id,
                                    action_type=action.action_type,
                                    actor=user.username,
                                    status="approved",
                                    payload=action.payload,
                                    subject=str(subject),
                                    sender=str(sender),
                                )
                                try:
                                    result = ActionExecutor().execute(action)
                                    st.session_state.decisions[action_id] = {
                                        "status": "executed",
                                        "result": result,
                                    }
                                    audit.log(
                                        event_type="execution",
                                        company_id=st.session_state.company_id,
                                        action_id=action.id,
                                        action_type=action.action_type,
                                        actor=user.username,
                                        status="executed",
                                        payload=action.payload,
                                        result=result,
                                        subject=str(subject),
                                        sender=str(sender),
                                    )
                                except Exception as exc:
                                    st.session_state.decisions[action_id] = {
                                        "status": "error",
                                        "error": str(exc),
                                    }
                                    audit.log(
                                        event_type="execution",
                                        company_id=st.session_state.company_id,
                                        action_id=action.id,
                                        action_type=action.action_type,
                                        actor=user.username,
                                        status="error",
                                        payload=action.payload,
                                        error=str(exc),
                                        subject=str(subject),
                                        sender=str(sender),
                                    )
                                st.rerun()

                        with reject_col:
                            if st.button(
                                "却下",
                                use_container_width=True,
                                key=f"reject_{action_id}",
                            ):
                                st.session_state.decisions[action_id] = {"status": "rejected"}
                                audit.log(
                                    event_type="rejection",
                                    company_id=st.session_state.company_id,
                                    action_id=str(action_id),
                                    action_type=str(action_data.get("action_type", "")),
                                    actor=user.username,
                                    status="rejected",
                                    payload=action_data.get("payload", {}),
                                    subject=str(subject),
                                    sender=str(sender),
                                )
                                st.rerun()

if audit_tab is not None:
    with audit_tab:
        st.subheader("操作・監査ログ")
        st.caption("承認、却下、実行結果を時系列で確認できます。")
        events = audit.list_events(limit=200)
        company_only = st.checkbox("現在の会社設定だけ表示", value=True)
        if company_only:
            events = [e for e in events if e.get("company_id") == st.session_state.company_id]

        if not events:
            st.write("監査ログはまだありません。")
        else:
            for event in events:
                with st.expander(
                    f"{event.get('timestamp', '')} | {event.get('status', '')} | {event.get('action_type', '')} | {event.get('actor', '')}"
                ):
                    st.write("**会社:**", event.get("company_id", ""))
                    st.write("**案件:**", event.get("subject", ""))
                    st.write("**相手:**", event.get("sender", ""))
                    st.write("**イベント:**", event.get("event_type", ""))
                    st.write("**Action ID:**", event.get("action_id", ""))
                    st.json(event.get("payload", {}), expanded=False)
                    if event.get("result") is not None:
                        st.write("**実行結果**")
                        st.json(event.get("result"), expanded=False)
                    if event.get("error"):
                        st.error(event.get("error"))
