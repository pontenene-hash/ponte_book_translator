# Googleドキュメントへ直接出力する設定

WordをGoogle Driveで開く方法なら、以下の設定は不要です。
ここでは、自分のGoogleアカウントへアプリから直接ドキュメントを作る方法を説明します。

## 前提

- 初回認証はWindowsなど、ご自身のPCで行います。
- Streamlit Community Cloud上で `google_setup.py` を実行しません。
- サービスアカウントではなく、ご自身のGoogleアカウントに対するOAuth認証を使います。
- アプリが作成したファイルを扱う `drive.file` スコープを使い、既存のDrive全体へのアクセスは要求しません。

## 初回設定

1. https://console.cloud.google.com/ でプロジェクトを作ります。
2. 「APIとサービス」で **Google Drive API** を有効にします。
3. Google Auth Platform／OAuth同意画面でアプリ名やメールアドレスなどの必要項目を設定します。
4. 個人で外部ユーザー向けのテスト設定を使う場合は、自分のGoogleアカウントをテストユーザーに追加します。
5. データアクセスのスコープに `https://www.googleapis.com/auth/drive.file` を追加します。
6. OAuthクライアントを作成し、種類は **デスクトップアプリ** を選びます。
7. ダウンロードしたJSONを、アプリのフォルダーに `google_client_secret.json` という名前で保存します。
8. `start_windows.bat` を一度実行して、必要なライブラリを入れます。アプリを閉じても構いません。
9. `google_setup_windows.bat` をダブルクリックします。ブラウザーが開くので、正しいGoogleアカウントを選び、内容を確認して許可します。
10. 同じフォルダーに `google_token.json` ができます。

Googleの設定画面の名称は更新で変わることがあります。公式手順：
https://developers.google.com/workspace/drive/api/quickstart/python

## アプリで使用

1. 翻訳を確認し、「4　出力」でPDF・Wordを作成します。
2. 「直接出力する」を開き、`google_token.json` を選択します。
3. 送信内容を確認し、「現在の出力内容を自分のGoogle Driveへ送信する」にチェックします。
4. 「Googleドキュメントを新規作成」を押します。
5. 成功すると文書を開くリンクが表示されます。

文書は新規作成です。途中で通信エラーになった場合は、再実行する前にGoogle Driveに文書ができていないか確認してください。文書作成の自動リトライは行いません。

## 認証ファイルの扱い

`google_client_secret.json` と `google_token.json` はGitHub、チャット、他人に渡すZIPへ入れないでください。アプリの `.gitignore` では除外していますが、Webからの手動アップロードは自分で確認してください。

Cloud版で直接出力する際は、このアプリのサーバーに認証ファイルを一時的に渡して処理します。ご自身が管理する個人用アプリだけで使用してください。認証情報は `.ponte`、PDF、Wordや出力ZIPには入りません。

OAuthアプリがテスト状態の場合などは、認証の有効期間や利用に制限があります。認証エラーになったら、Googleの設定を確認し、必要に応じて初回認証をやり直してください。直接連携を止める場合はGoogleアカウントの接続管理からアクセスを取り消せます。
