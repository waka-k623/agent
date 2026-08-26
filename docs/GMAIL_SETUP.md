# Gmail Connector Setup

Sales Agent v1 では Gmail を読み取り専用で接続します。

## 1. Google Cloud project

1. Google Cloud Console でプロジェクトを作成します。
2. Gmail API を有効にします。
3. Google Auth Platform で OAuth 同意画面を設定します。
4. OAuth Client ID を作成し、アプリケーション種類は Desktop app を選択します。
5. OAuth クライアント JSON をダウンロードします。

## 2. Local credentials

ダウンロードした JSON をプロジェクト直下に `credentials.json` として保存します。

```text
agent/
├─ credentials.json   # GitHubにはコミットしない
├─ token.json         # 初回認証後に自動生成。コミットしない
├─ app/
└─ scripts/
```

`.gitignore` で `credentials.json` と `token.json` は除外済みです。

## 3. Install

```bash
pip install -r requirements.txt
```

## 4. First authentication and test

プロジェクト直下で次を実行します。

```bash
python scripts/gmail_check.py
```

初回はブラウザが開き、GoogleアカウントへのログインとGmail読み取り権限の許可が求められます。

認証が完了すると `token.json` が生成され、次回以降は再利用されます。

成功すると、接続中のメールアドレスと直近5件の受信メールの送信者・件名・日時・スニペットが表示されます。

## 5. Scope

現在使用するOAuth scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

v1では読み取りだけに限定します。下書き作成・送信は、読み取り機能を検証してから別スコープとして追加します。

## 6. Useful Gmail search queries

Gmail検索と同じ形式で `list_messages()` に渡せます。

```text
in:inbox
is:unread
newer_than:7d
from:customer@example.com
in:inbox newer_than:7d
```

## 7. Security

- `credentials.json` をGitHubにアップロードしない
- `token.json` をGitHubにアップロードしない
- `.env` をGitHubにアップロードしない
- 企業導入時は企業ごとにOAuth認証情報とトークンを分離する
- 必要最小限のOAuth scopeのみを要求する
