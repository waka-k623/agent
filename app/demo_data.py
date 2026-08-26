from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.actions.approval import ProposedAction


def build_demo_queue() -> list[dict]:
    tz = ZoneInfo("Asia/Tokyo")
    tomorrow = datetime.now(tz) + timedelta(days=1)
    meeting_start = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    meeting_end = meeting_start + timedelta(hours=1)

    samples = [
        {
            "analysis": {
                "sales_relevant": True,
                "category": "new_lead",
                "priority": "high",
                "current_status": "新規問い合わせ。導入時期が近く、担当者から具体的な相談あり。",
                "reasoning_summary": "問い合わせ内容が具体的で、短期導入ニーズが確認できるため優先度は高い。",
                "next_action": "本日中に返信し、30分の初回ヒアリングを提案する。",
                "recommended_timing": "本日中",
                "meeting_slots": [meeting_start.isoformat(), meeting_end.isoformat()],
                "draft_message": "お問い合わせありがとうございます。内容を拝見し、現在の業務フローを確認した上で最適な進め方をご提案できればと思います。まずは30分ほどオンラインで状況を伺えますでしょうか。",
                "crm_status": "replied",
                "sender": "田中 太郎 <tanaka@example-build.jp>",
                "subject": "営業管理の自動化について相談",
            },
            "actions": [
                ProposedAction(
                    action_type="gmail_draft",
                    payload={
                        "to": "tanaka@example-build.jp",
                        "subject": "Re: 営業管理の自動化について相談",
                        "body": "お問い合わせありがとうございます。内容を拝見し、現在の業務フローを確認した上で最適な進め方をご提案できればと思います。まずは30分ほどオンラインで状況を伺えますでしょうか。",
                    },
                    reason="高優先度の新規問い合わせのため、即日返信を推奨。",
                ),
                ProposedAction(
                    action_type="calendar_event",
                    payload={
                        "summary": "初回ヒアリング - Example Build",
                        "start": meeting_start.isoformat(),
                        "end": meeting_end.isoformat(),
                        "attendees": ["tanaka@example-build.jp"],
                    },
                    reason="初回商談候補を作成。",
                ),
            ],
        },
        {
            "analysis": {
                "sales_relevant": True,
                "category": "follow_up_needed",
                "priority": "medium",
                "current_status": "提案送付から4日経過し、先方から返信なし。",
                "reasoning_summary": "失注判断には早く、軽いフォローを入れるタイミング。",
                "next_action": "短いフォローメールを下書きし、状況確認する。",
                "recommended_timing": "今日〜明日",
                "meeting_slots": [],
                "draft_message": "先日お送りしたご提案について、その後のご状況はいかがでしょうか。ご不明点や調整したい点があれば、短時間でもご説明できますのでお気軽にお知らせください。",
                "crm_status": "follow_up",
                "sender": "佐藤 花子 <sato@example-realestate.jp>",
                "subject": "Re: AI営業支援のご提案",
            },
            "actions": [
                ProposedAction(
                    action_type="gmail_draft",
                    payload={
                        "to": "sato@example-realestate.jp",
                        "subject": "Re: AI営業支援のご提案",
                        "body": "先日お送りしたご提案について、その後のご状況はいかがでしょうか。ご不明点や調整したい点があれば、短時間でもご説明できますのでお気軽にお知らせください。",
                    },
                    reason="提案後のフォロー漏れ防止。",
                ),
                ProposedAction(
                    action_type="crm_update",
                    payload={"email": "sato@example-realestate.jp", "updates": {"status": "follow_up", "priority": "medium"}},
                    reason="CRMを現在の追客状態へ更新。",
                ),
            ],
        },
        {
            "analysis": {
                "sales_relevant": False,
                "category": "other",
                "priority": "low",
                "current_status": "営業対応不要の定期通知メール。",
                "reasoning_summary": "顧客対応や商談には直接関係しないため、優先度は低い。",
                "next_action": "対応不要。",
                "recommended_timing": "なし",
                "meeting_slots": [],
                "draft_message": "",
                "crm_status": "",
                "sender": "System Notice <notice@example-service.com>",
                "subject": "月次システム通知",
            },
            "actions": [],
        },
    ]

    return [
        {
            "analysis": sample["analysis"],
            "proposed_actions": [asdict(action) for action in sample["actions"]],
        }
        for sample in samples
    ]


def calculate_demo_kpis(queue: list[dict]) -> dict[str, float | int]:
    total = len(queue)
    sales_relevant = sum(1 for item in queue if item.get("analysis", {}).get("sales_relevant"))
    high_priority = sum(1 for item in queue if str(item.get("analysis", {}).get("priority", "")).lower() == "high")
    proposed_actions = sum(len(item.get("proposed_actions", [])) for item in queue)

    # Demo assumptions: manual triage 5 min/message, draft/action preparation 4 min/action.
    estimated_minutes_saved = total * 5 + proposed_actions * 4
    response_coverage = round((sales_relevant / total) * 100, 1) if total else 0.0

    return {
        "messages_analyzed": total,
        "sales_relevant": sales_relevant,
        "high_priority": high_priority,
        "proposed_actions": proposed_actions,
        "estimated_minutes_saved": estimated_minutes_saved,
        "response_coverage_pct": response_coverage,
    }
