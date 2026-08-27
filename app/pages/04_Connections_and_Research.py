from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.runtime import RuntimeConfig

st.set_page_config(page_title="Connections & Research", page_icon="🔌", layout="wide")

runtime = RuntimeConfig.from_env()
current_user = st.session_state.get("current_user")

if current_user is None:
    st.warning("先にメイン画面からログインしてください。")
    st.stop()

st.title("Connections & Research")
st.caption("外部接続の準備状況と、福井企業リサーチの実行状態を確認します。")

provider = os.getenv("LLM_PROVIDER", "openai").lower()
llm_key_name = "ANTHROPIC_API_KEY" if provider in {"anthropic", "claude"} else "OPENAI_API_KEY"

checks = [
    ("Web research", "TAVILY_API_KEY", bool(os.getenv("TAVILY_API_KEY"))),
    ("LLM", llm_key_name, bool(os.getenv(llm_key_name))),
    ("Persistent memory", "DATABASE_URL", bool(os.getenv("DATABASE_URL"))),
    ("Google OAuth credentials", "GOOGLE_CREDENTIALS_PATH", Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")).exists()),
]

cols = st.columns(len(checks))
for col, (label, key, ok) in zip(cols, checks):
    with col:
        st.metric(label, "READY" if ok else "MISSING")
        st.caption(key)

research_ready = bool(os.getenv("TAVILY_API_KEY")) and bool(os.getenv(llm_key_name))

if runtime.is_demo:
    st.info("公開デモではAPIコストや外部アクセスを発生させないため、ライブ企業調査は無効です。接続状態のみ確認できます。")

st.subheader("福井企業リサーチ")
industry = st.text_input("業種ヒント（任意）", placeholder="例：建設、製造、宿泊")
limit = st.slider("1サイクルの調査企業数", min_value=1, max_value=20, value=5)

blocked_reasons: list[str] = []
if not research_ready:
    blocked_reasons.append(f"TAVILY_API_KEY と {llm_key_name} の両方が必要です")
if runtime.is_demo:
    blocked_reasons.append("APP_ENV=demo ではライブ調査を実行しません")

if blocked_reasons:
    for reason in blocked_reasons:
        st.warning(reason)

if st.button("2回検証リサーチを実行", type="primary", disabled=bool(blocked_reasons)):
    try:
        from app.prospect_discovery import ProspectDiscovery

        with st.spinner("企業発掘 → 1回目調査 → 2回目検証 → スコアリングを実行しています..."):
            result = ProspectDiscovery().run(industry_hint=industry.strip(), research_limit=limit)
        st.session_state["latest_live_research"] = result
        st.success(
            f"完了: 発掘 {result.get('discovered_count', 0)}社 / "
            f"調査 {result.get('researched_count', 0)}社 / "
            f"P0/P1 {result.get('sales_ready_count', 0)}社"
        )
    except Exception as exc:
        st.error(f"リサーチ実行に失敗しました: {exc}")

result = st.session_state.get("latest_live_research")
if result:
    st.subheader("最新結果")
    sales_ready = result.get("sales_ready") or []
    if not sales_ready:
        st.info("このサイクルではP0/P1企業はありませんでした。根拠不足企業はRESEARCH/P2のまま保持されます。")
    for item in sales_ready:
        score = item.get("score") or {}
        memory = item.get("memory") or {}
        with st.expander(f"{item.get('company', '')} | {score.get('priority')} | {score.get('score')}"):
            st.write(f"Confidence: {score.get('confidence')}%")
            st.write(f"Research passes: {score.get('research_passes')}")
            st.write(memory.get("evidence", {}).get("evidence_summary", ""))
            st.write("Sources:")
            for url in memory.get("source_urls", []):
                st.write(url)

st.subheader("運用ルール")
st.write(
    "数値や企業課題が確認できない場合は空欄のまま保持し、推測値を補完しません。"
    "営業可能になるには2回のリサーチと独立ソース検証を通過し、P0またはP1判定が必要です。"
)
