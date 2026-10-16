# 三紙ニュース比較（Mac / iPhone 共通Webアプリ）

朝日新聞・毎日新聞・読売新聞の公開ニュースメタデータを比較する静的Webアプリです。

## 固定URLを作る（最初だけ）

1. [GitHub](https://github.com/) に無料アカウントを作り、**Public** リポジトリを `threepapers` などの名前で作ります（公開データのみを使います）。
2. このZIPを解凍して、**中のファイルと `.github` フォルダを** リポジトリの最上位にアップロードします。隠しフォルダ `.github` がGitHub上で反映されているか確認してください。Gitが使える場合はリポジトリをcloneして中身をコピーしてcommit/pushする方が確実です。
3. リポジトリの **Settings → Actions → General → Workflow permissions** を **Read and write permissions** に設定します。
4. **Settings → Pages → Build and deployment → Source: GitHub Actions** を選択します。
5. **Actions → Update newspapers → Run workflow** を押して初回取得を実行します。完了後 `https://<GitHubユーザー名>.github.io/<リポジトリ名>/` にアクセスします。
6. SafariでURLをコピーし、Appleメモに貼り付ければ、Mac / iPhoneのどちらでも同じ画面が開きます。iPhoneのSafariから「ホーム画面に追加」もできます。

## 自動更新

- 毎日 **05:00・17:00 日本時間**（GitHub Actions のスケジュールはUTCで設定）。
- GitHub Actions の混雑により**定刻より遅れることがあります**。厳密な時間保証はありません。
- GitHub Pages の反映にもタイムラグが生じる場合があります。
- 無料プラン・Publicリポジトリ利用条件、GitHubのワークフロー停止ポリシーなどはGitHubの現行規約を確認してください。

## 利用上の注意

- **現段階では配信元に接続できる本番環境での取得成功は未確認**です。サイトのHTML変更・アクセス制限により取得ゼロになる場合があります。エラー理由はアプリに表示されます。
- 朝日・毎日は指定の分野別一覧から候補を抽出します。読売はYahooの読売配信一覧から、見出しのキーワードで分野判定します。曖昧な記事は除外するため漏れがあります。
- 読売のリンク・日時はYahoo配信先のものです。Yahoo側の構造化データで読売新聞オンラインの著者/発行元情報が確認できなければ採用しません。
- 有料本文や保護されたコンテンツを取得せず、公開HTMLのタイトル・description・構造化メタデータのみ扱います。有料・無料が検証できなければ「確認できず」と表示します。
- 公開GitHubリポジトリには、取得履歴・取得エラーも公開されます。個人的な情報は入れないでください。
- GitHub Pages の `docs/data` に過去100回の取得履歴を保管。古い履歴ファイルは自動削除していないため、長期運用でサイズが増加します。
- このソフトはChatGPTの既存ニュース配信タスクとは別に動作します。既存タスクは自動停止しません。

## ローカル試験

```bash
python -m pip install -r requirements.txt
python fetch.py
python -m http.server 8000 --directory docs
```

ブラウザから `http://localhost:8000` を開きます。


## 2026年10月16日版の画面更新

画面上部の「記事一覧 / 三紙比較」で切替できます。17時の配信は試作スナップショットであり元記事を再検証していないためリンクを無効化しています。自動取得の「最新版」は従来の `fetch.py` の記事を表示できますが、機械的な同一ニュース照合を検証なしに行わないため比較画面は空になります。公開URLはGitHub Pagesへの配置後に発行されます。
