"""Use user's drive.file OAuth credential, never a shared service account."""
import io
SCOPES=['https://www.googleapis.com/auth/drive.file']

def upload_docx(docx_bytes,title,token_info):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    if not isinstance(token_info,dict) or not token_info.get('refresh_token'):
        raise ValueError('google_token.json を設定してください。詳しくは手順書を参照してください。')
    # Never accept a token_uri supplied by an imported file (avoid secret exfiltration).
    safe={k:token_info[k] for k in ('client_id','client_secret','refresh_token','token','expiry') if k in token_info}
    safe['token_uri']='https://oauth2.googleapis.com/token'
    creds=Credentials.from_authorized_user_info(safe,SCOPES)
    if not creds.valid: creds.refresh(Request())
    drive=build('drive','v3',credentials=creds,cache_discovery=False)
    media=MediaIoBaseUpload(io.BytesIO(docx_bytes),mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',resumable=False)
    # No automatic retries: uncertain completion must be checked in Drive before creating another document.
    result=drive.files().create(body={'name':title,'mimeType':'application/vnd.google-apps.document'},media_body=media,fields='id,webViewLink').execute(num_retries=0)
    if not result.get('id'): raise RuntimeError('Googleから文書IDを取得できませんでした。Driveをご確認ください。')
    return result.get('webViewLink') or 'https://docs.google.com/document/d/'+result['id']+'/edit'
