from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure the repository root is importable when Streamlit executes this file directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.actions.approval import ProposedAction
from app.actions.executor import ActionExecutor
from app.audit import AuditLogger
from app.auth import UserContext, UserStore
from app.company_config import CompanyConfigStore
from app.demo_data import build_demo_queue, calculate_demo_kpis
from app.preflight import run_preflight, summarize_preflight
from app.runtime import RuntimeConfig
from app.workflows.review_queue import SalesReviewQueue

st.set_page_config(page_title="Sales Agent Review", page_icon="🤖", layout="wide")

runtime = RuntimeConfig.from_env()

if "queue" not in st.session_state:
    st.session_state.queue = []
if "decisions" not in st.session_state:
    st.session_state.decisions = {}
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = runtime.demo_mode_default or runtime.is_demo

user_store = UserStore()
if not runtime.is_demo:
    user_store.ensure_demo_users()
company_store = CompanyConfigStore()
audit = AuditLogger()


def login_screen() -> None:
    st.title("Sales Agent Demo")
    st.caption("公開デモ環境です。誰でもテスト用ユーザーとして入れます。")

    if runtime.is_demo:
        st.info("この環境では実データの読み込み・外部サービスへのライブ書き込みは無効です。")
        if st.button("デモを開始", type="primary", use_container_width=True):
            st.session_state.current_user = UserContext(
                username="demo",
                role="admin",
                company_id="default",
                display_name="Demo User",
            )
            st.session_state.queue = []
            st.session_state.decisions = {}
            st.rerun()
        return

    st.caption("営業支援AIの管理画面にログインしてください。")
    with st.form("login_form"):
        username = st.text_input("ユーザー名")
        password = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)

    if submitted:
        record = user_store.authenticate(username, password)
        if record is None:
            st.error("ユーザー名またはパスワードが正しくありません。")
            return
        st.session_state.current_user = record.to_context()
        st.session_state.queue = []
        st.session_state.decisions = {}
        st.rerun()


if st.session_state.current_user is None:
    login_screen()
    st.stop()

user: UserContext = st.session_state.current_user
st.title("Sales Agent Review")
st.caption("営業案件を確認し、AIが提案した外部アクションを承認または却下します。")

st.sidebar.write(f"**ログイン:** {user.display_name or user.username}")
st.sidebar.caption("管理者" if user.role == "admin" else "一般ユーザー")

if runtime.is_demo:
    st.session_state.demo_mode = True
    st.sidebar.toggle(
        "デモモード",
        value=True,
        disabled=True,
        help="公開デモ環境では実データモードへ切り替えられません。",
    )
else:
    st.session_state.demo_mode = st.sidebar.toggle(
        "デモモード",
        value=st.session_state.demo_mode,
        help="サンプル案件を使い、外部サービスを書き換えずに動作確認します。",
    )

if st.sidebar.button("ログアウト", use_container_width=True):
    st.session_state.current_user = None
    st.session_state.queue = []
    st.session_state.decisions = {}
    st.rerun()

company_ids = company_store.list_company_ids() or ["default"]
if user.can_manage_company_settings():
    default_index = company_ids.index(user.company_id) if user.company_id in company_ids else 0
    company_id = st.sidebar.selectbox("会社設定", company_ids, index=default_index)
else:
    company_id = user.company_id
    st.sidebar.caption(f"会社設定: {company_id}")

try:
    company = company_store.load(company_id)
    st.sidebar.caption(f"{company.company_name} / {company.industry}")
except Exception:
    company = None


def refresh_queue() -> None:
    if st.session_state.demo_mode:
        st.session_state.queue = build_demo_queue()
        st.session_state.decisions = {}
        return

    if runtime.is_demo:
        st.error("公開デモ環境では実データを読み込めません。")
        return

    with st.spinner("Gmail / Contacts / CRM / Calendar を確認しています..."):
        st.session_state.queue = SalesReviewQueue(company_id=company_id).build(max_results=10)
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
    review_tab, audit_tab, preflight_tab = st.tabs(["承認キュー", "監査ログ", "公開前診断"])
else:
    review_tab = st.container()
    audit_tab = None
    preflight_tab = None

with review_tab:
    if st.session_state.demo_mode:
        st.success("デモモード: サンプル営業データを使用し、外部サービスへの書き込みは行いません。")

    col1, col2 = st.columns([1, 4])
    with col1:
        button_label = "デモ案件を読み込む" if st.session_state.demo_mode else "受信箱を分析"
        if st.button(button_label, type="primary", use_container_width=True):
            refresh_queue()
    with col2:
        if st.session_state.demo_mode:
            st.info("承認操作を試せますが、Gmail・Calendar・CRMは変更されません。")
        else:
            st.info("承認ボタンを押すまで、Gmail・Calendar・CRMへの書き込みは実行されません。")

    queue = st.session_state.queue
    if queue:
        kpis = calculate_demo_kpis(queue)
        st.subheader("営業オペレーションKPI")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("分析案件", kpis["messages_analyzed"])
        k2.metric("営業対象", kpis["sales_relevant"])
        k3.metric("高優先度", kpis["high_priority"])
        k4.metric("提案アクション", kpis["proposed_actions"])
        k5.metric("推定削減時間", f'{kpis["estimated_minutes_saved"]}分')
        st.caption("推定削減時間はデモ用の仮定値です。実導入時は実測値に置き換えます。")

    if not queue:
        empty_label = "『デモ案件を読み込む』" if st.session_state.demo_mode else "『受信箱を分析』"
        st.write(f"まだ分析結果がありません。{empty_label}を押してください。")
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
                            elif decision.get("status") == "simulated":
                                st.success("承認済み（デモ実行）")
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
                            if st.button("承認して実行", type="primary", use_container_width=True, key=f"approve_{action_id}"):
                                action = proposed_action_from_dict(action_data)
                                action.approve()
                                if st.session_state.demo_mode:
                                    st.session_state.decisions[action_id] = {
                                        "status": "simulated",
                                        "result": {"demo": True, "action_type": action.action_type},
                                    }
                                else:
                                    audit.log(
                                        event_type="approval",
                                        company_id=company_id,
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
                                        st.session_state.decisions[action_id] = {"status": "executed", "result": result}
                                        audit.log(
                                            event_type="execution",
                                            company_id=company_id,
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
                                        st.session_state.decisions[action_id] = {"status": "error", "error": str(exc)}
                                        audit.log(
                                            event_type="execution",
                                            company_id=company_id,
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
                            if st.button("却下", use_container_width=True, key=f"reject_{action_id}"):
                                st.session_state.decisions[action_id] = {"status": "rejected"}
                                if not st.session_state.demo_mode:
                                    audit.log(
                                        event_type="rejection",
                                        company_id=company_id,
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
        events = audit.list_events(limit=200)
        company_only = st.checkbox("現在の会社設定だけ表示", value=True)
        if company_only:
            events = [e for e in events if e.get("company_id") == company_id]

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

if preflight_tab is not None:
    with preflight_tab:
        st.subheader("公開前診断")
        st.caption("AI・Google連携・認証・安全設定の不足をまとめて確認します。")
        checks = run_preflight()
        summary = summarize_preflight(checks)

        p1, p2, p3 = st.columns(3)
        p1.metric("PASS", summary["passed"])
        p2.metric("ERROR", summary["errors"])
        p3.metric("WARNING", summary["warnings"])

        if summary["ready"]:
            st.success("必須チェックは通過しています。")
        else:
            st.error("公開前に解消すべき必須項目があります。")

        for check in checks:
            if check.ok:
                st.success(f"✅ {check.name}: {check.detail}")
            elif check.severity == "warning":
                st.warning(f"⚠️ {check.name}: {check.detail}")
            else:
                st.error(f"❌ {check.name}: {check.detail}")
