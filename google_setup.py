"""Run once on your own PC. Never run the loopback OAuth flow on Community Cloud."""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google_export import SCOPES
if __name__=='__main__':
    path=Path('google_client_secret.json')
    if not path.exists():
        raise SystemExit('Google Cloudのデスクトップアプリ用OAuth JSONを google_client_secret.json の名前でこのフォルダーへ保存してください。')
    creds=InstalledAppFlow.from_client_secrets_file(str(path),SCOPES).run_local_server(port=0,timeout_seconds=180,access_type='offline',prompt='consent')
    token=Path('google_token.json'); token.write_text(creds.to_json(),encoding='utf-8')
    try: token.chmod(0o600)
    except OSError: pass
    print('google_token.json を保存しました。アプリの「Googleドキュメント」設定へ読み込んでください。GitHubやチャットにはアップロードしないでください。')
