# Sales Agent v1 — Product Spec

## 1. Goal

営業活動で発生する「誰に、いつ、何をするか」の判断負荷とフォロー漏れを減らす。

v1ではAIが勝手に営業することよりも、営業担当者の判断を支援し、承認後に実行できる状態を重視する。

## 2. Primary user

最初のユーザーは開発者本人。

ただし、設計は個人固有にせず、将来的に中小企業の営業担当者・経営者が利用できることを前提とする。

## 3. Core objects

### Lead
- company_name
- contact_name
- contact_channel
- source
- status
- last_contact_at
- next_follow_up_at
- notes
- priority

### Sales status
- new
- contacted
- replied
- meeting_scheduled
- meeting_completed
- proposal_sent
- follow_up
- won
- lost

### Agent output
- current_status
- priority
- reasoning_summary
- next_action
- recommended_timing
- draft_message
- requires_human_approval

## 4. v1 capabilities

### A. Lead understanding
入力された顧客情報と過去の接触状況から現在の営業ステータスを整理する。

### B. Prioritization
見込み度、最終接触日、返信状況、商談状況などから対応優先度を提示する。

### C. Next Action
「再連絡」「返信」「商談準備」「提案送付」「保留」など次に行う営業行動を提示する。

### D. Message drafting
状況に応じたメール・DM等の文案を生成する。

### E. Follow-up
次回フォロー日時を提案し、期限超過のリードを検出できるようにする。

## 5. Human approval policy

v1では以下の操作はAI単独で実行しない。

- メール・DMの外部送信
- 顧客情報の削除
- 商談日時の確定
- 契約・価格に関わる確定回答

AIは提案または下書きを作成し、人間の承認後に実行する。

## 6. Architecture direction

```text
Input / Integrations
       ↓
Lead normalization
       ↓
Sales Agent Core
 ├─ classify
 ├─ prioritize
 ├─ next action
 └─ draft
       ↓
Approval layer
       ↓
Actions / Integrations
```

企業向けでは以下を差し替え可能にする。

- company profile
- sales rules
- tone
- products/services
- qualification criteria
- integrations
- approval policy

## 7. Initial success metrics

- フォロー漏れ件数
- 1リードあたりの判断・文章作成時間
- Agent提案の採用率
- 人間による修正率
- 誤分類・不適切提案件数

## 8. Not in v1

- 完全自動営業
- 大規模なCRM構築
- 複雑なマルチエージェント構成
- 電話の完全自動応対
- 契約締結の自動化

これらはv1の実運用結果を確認してから追加する。
