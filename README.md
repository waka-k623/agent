# Sales Agent

自分で実際に使いながら検証し、将来的に企業向けへ横展開することを目的とした営業・顧客対応 AI Agent プロジェクトです。

## Product direction

最初の1体は **Sales Agent v1** とします。

このAgentは、営業先・問い合わせ・見込み客について「次に何をすべきか」を判断し、返信案やフォローアップを支援します。

最初は自分専用として運用し、実運用で得た改善点と実績をもとに、企業ごと・業界ごとに設定や連携先を差し替えられる構成へ発展させます。

## v1 workflow

```text
顧客 / 見込み客情報
        ↓
   Sales Agent
        ↓
1. 状況を理解・分類
2. 優先度を判断
3. 次の営業アクションを提案
4. 返信・フォロー文を生成
5. フォロー期限を管理
6. 人間が確認・承認
        ↓
      実行
```

## Design principles

- 最初から完全自動化しない
- 外部への送信・更新は原則として人間の承認を挟む
- 共通ロジックと企業固有設定を分離する
- Gmail / Calendar / Sheets / CRM などを後から追加できるようにする
- 1社向けのハードコードではなく再利用できる構造にする
- 実際の業務削減時間・精度・失敗例を計測できるようにする

## Roadmap

### Phase 1 — Personal Sales Agent
- 顧客情報入力
- 営業ステータス分類
- 優先順位付け
- Next Action生成
- 返信案生成
- フォローアップ管理

### Phase 2 — Integrations
- Gmail
- Google Calendar
- Google Sheets / CRM

### Phase 3 — Business-ready
- 企業別設定
- 承認フロー
- 操作ログ
- 権限管理
- KPI / 効果測定

### Phase 4 — Industry variants
- 建設
- 不動産
- 人材
- 美容・店舗
- その他BtoB営業

詳細は `docs/PRODUCT_SPEC.md` を参照してください。
