# 検証結果（2026-10-06）

## 実行済み

- Python 3.12 / Linuxでソースの構文確認。
- Streamlit AppTestで初期表示、デモ読込、訳文編集、並べ替え、出力操作、再実行後の出力保持を確認。
- 複数ページPDFの取込とページ上限を確認。
- 原本・訳文・辞書・図の範囲を含む途中保存と復元を確認。
- 約1万字の日本語を使い、複数ページへ継続し末尾まで残ることを確認。
- 見開きPDFと日本語PDFのページ数、および交互PDFがその2倍になることを確認。
- PDFの図・Wordの原本画像と図の収録を確認。
- 日本語フォントの埋込を確認（Droid Sans Fallbackのサブセット）。
- 見開きPDFを画像化し、左右配置・日本語・図の切出し・余白を目視確認。
- API成功・出力打切りを模擬応答で検証。
- 連続翻訳中のAPIエラーで停止し、完了ページが途中保存に残ることを模擬応答で確認。
- 不正な保存ファイル内の画像パスを拒否することを確認。
- APIキーが途中保存に含まれないことを確認。
- Streamlitを実際に起動し、同一プロセス環境からHTTPヘルスチェックで `ok` を確認。
- 旧版の自動テスト：8件成功。写真補正追加後の結果は末尾に追記。

## 未検証・利用者設定が必要な部分

- ご本人のAPIキーでのGemini/OpenAI実通信、実資料の翻訳品質、実際の利用料金。
- Google OAuthの本人認証とGoogleドキュメントの実作成。
- ご本人のGitHub・Streamlit Cloudへの配置。公開URLは未作成。
- Windows/iPhone実機の表示・操作。Windows用起動ファイルと配置手順は同梱。
- 原書と完全に同じ組版、図中文字の日本語への画像置換は対象外。

基本機能が通ることと、実際の専門書の翻訳精度を保証することは別です。最初に1ページを翻訳し、読取英文・訳文・図の範囲を原本と照合してください。

## 再現用の主な依存バージョン

- streamlit 1.65.0
- Pillow 12.3.0
- PyMuPDF 1.26.6
- reportlab 4.4.9
- python-docx 1.2.0
- requests 2.34.2
- google-auth 2.60.0
- google-auth-oauthlib 1.5.0
- google-api-python-client 2.201.0

## v1.1 写真補正追加後の検証

- 合成した台形の紙から四隅を検出し、期待位置との差が2%未満であることを確認。
- 四隅の交差など、不正な範囲指定を拒否することを確認。
- 人工的に湾曲させた3本の線に対し、既知の湾曲量を指定して補正。線の高さのばらつきが1px未満になることを確認し、補正前後を画像でも確認。
- 補正前の画像をバイト単位で保持し、保存→再読込→補正解除で一致することを確認。
- Streamlit画面から自動検出→プレビュー→採用→取り消しの操作を確認。
- API通信なしで全ての補正処理が完了。
- 既存の出力・編集・再開テストも含め **12件成功**。

写真補正は合成テスト画像と操作デモで検証しました。利用者の実際の製本写真での補正品質、Windows/iPhone実機、Gemini無料枠での実通信は未検証です。湾曲は手動の簡易補正であり、自動3D平坦化ではありません。

追加依存：
- opencv-python-headless 5.0.0.93
- numpy 2.3.5

## v1.2 一括補正・詳細湾曲補正

- 一括候補作成→一覧で確認→まとめて採用→画像ZIP/PDF作成の画面操作を確認。
- 一覧から個別調整へ移動し、詳細湾曲補正の基準線表示→プレビュー→採用→一括画面へ戻って出力する操作を確認。
- 元画像が変更された古い候補は採用できないことを確認。
- ZIPの連番ファイルと出典対応表、PDFのページ数・順番を確認。
- 採用前の候補が元画像を変更しないこと、採用後の確認状態が保存・復元できることを確認。
- 非対称の湾曲を持つ人工的な3本の線に詳細補正を適用し、各行の高さのばらつきが1.5px未満となることと、上下端が保持されることを確認。
- 基準線が交差する不正な設定を拒否することを確認。
- 既存テストを含む自動テスト：16件成功。

詳細湾曲補正は利用者が基準線を設定する方式です。実際の製本写真のあらゆる湾曲での精度は保証していません。Windows・iPhone実機の操作とホスティング配置は未検証です。

## v1.3 PDF・プロンプトの同時出力

- 出力対象のページ数と順番、プロジェクト名、用語辞書が依頼文に反映されることを確認。
- 2点セットZIPのPDFが同時作成したPDFと一致し、TXTも同じ生成結果であることを確認。
- 一括補正→採用→PDF・プロンプト作成の画面操作を確認。
- 既存機能も含め自動テスト17件成功。
- ChatGPTへの送信・翻訳・最終的な対訳PDF作成は、このアプリの自動実行範囲には含みません。

## v2.0 検証
- 19 tests passed: legacy tests + rotation/restore, optional orientation fallback, new review/reorder/export flow and stale output invalidation.
- Canvas component protocol and vertical drag behavior checked with a JavaScript DOM mock.
- Browser installation failed in this environment. Actual browser/touch rendering and iPhone/Windows operation are not verified.
- Tesseract orientation is confidence-gated; always visually confirm.
