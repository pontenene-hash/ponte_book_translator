from __future__ import annotations
import io, json, os, tempfile, time, uuid
from pathlib import Path
import streamlit as st
from PIL import Image
from core import (new_project, ingest, pack, unpack, apply_result, normalize_result,
                  parse_result, figure_bytes, glossary_dict, MAX_PAGES)
from ai import translate, make_prompt
from exports import export_bundle
from google_export import upload_docx

st.set_page_config(page_title='PONTE｜洋書翻訳ノート',page_icon='📖',layout='wide')
st.markdown('''<style>
.stApp{background:#f7f6f1} [data-testid="stSidebar"]{background:#e8eee8}
h1,h2,h3{color:#214d47} .stButton>button,.stDownloadButton>button{min-height:44px;border-radius:10px}
[data-testid="stMetric"]{background:white;padding:14px;border-radius:14px;border:1px solid #e1e6df}
.block-container{padding-top:2rem;max-width:1350px} .eyebrow{font-size:12px;letter-spacing:.18em;color:#53756b}
.intro{color:#64756d;font-size:16px;margin-bottom:25px} textarea{line-height:1.7!important}
@media(max-width:640px){.block-container{padding-top:1rem;padding-left:1rem;padding-right:1rem}}
</style>''',unsafe_allow_html=True)

def secret(name,default=''):
    try: return st.secrets.get(name,default)
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError): return default

access_password=secret('APP_PASSWORD')
if access_password and not st.session_state.get('authenticated'):
    import hmac
    st.title('PONTE｜洋書翻訳ノート')
    with st.form('login'):
        entered=st.text_input('アプリのパスワード',type='password')
        if st.form_submit_button('開く'):
            if hmac.compare_digest(entered,str(access_password)):
                st.session_state.authenticated=True;st.rerun()
            else: st.error('パスワードを確認してください。')
    st.stop()

if 'project' not in st.session_state:
    st.session_state.project=new_project()
    st.session_state.rev=0
    st.session_state.backup=pack(st.session_state.project)
    st.session_state.added=[]
    st.session_state.autosave_dir=tempfile.mkdtemp(prefix='ponte-book-')
    st.session_state.exports=None
    st.session_state.google_url=None

p=st.session_state.project

def save():
    st.session_state.rev+=1
    st.session_state.backup=pack(st.session_state.project)
    st.session_state.exports=None;st.session_state.google_url=None
    try:
        dest=Path(st.session_state.autosave_dir)/'latest.ponte'
        tmp=dest.with_suffix('.tmp');tmp.write_bytes(st.session_state.backup);tmp.replace(dest)
        st.session_state.autosave_error=''
    except OSError:
        st.session_state.autosave_error='一時保存できませんでした。「途中保存」をダウンロードしてください。'

def replace_project(project):
    st.session_state.project=project
    st.session_state.added=[]
    st.session_state.pop('selected_page',None)
    save()

def status_message(msg):
    st.session_state.notice=msg

def run_translation(page,provider,key,model,glossary,instructions):
    result,usage=translate(page,provider,key,model,glossary,instructions)
    apply_result(page,result,provider,model,usage)
    save()

with st.sidebar:
    advanced=st.toggle('従来の翻訳・編集画面を使う',value=False,key='advanced_mode')
if not advanced:
    from simple_app import render
    render(p,save,replace_project)
    st.stop()

with st.sidebar:
    st.markdown('### 📖 PONTE\n洋書翻訳ノート')
    st.caption('v1.3.1 ・ PDF＋プロンプト出力対応')
    step=st.radio('作業メニュー',['1　資料を追加','一括補正・画像出力','写真の補正（無料）','2　翻訳・確認','3　用語辞書','4　出力'],label_visibility='collapsed',key='work_menu')
    st.caption('写真補正・編集・PDF作成はAPI不要。追加API料金を使わない場合は「手動」を選択してください。')
    st.divider()
    with st.expander('翻訳エンジン・設定',expanded=True):
        provider=st.selectbox('翻訳方法',['手動（APIなし）','Gemini','OpenAI'])
        key='';model=''
        if provider!='手動（APIなし）':
            key=st.text_input('APIキー',type='password',value=secret('GEMINI_API_KEY' if provider=='Gemini' else 'OPENAI_API_KEY'),key='key_'+provider)
            model=st.text_input('モデルID',value='gemini-2.5-flash' if provider=='Gemini' else 'gpt-4.1-mini',key='model_'+provider)
            st.caption('Geminiには対象モデルの無料枠がありますが回数制限があります。課金設定済みのキーでは料金が発生する場合があります。アプリから課金区分は判定できません。')
        else:
            st.caption('ChatGPTなどで翻訳した文章を貼り付けて利用できます。自動翻訳はしません。')
        instructions=st.text_area('翻訳への追加指示',placeholder='例：専門用語には初出のみ英語を併記',height=80)
    st.divider()
    st.download_button('💾 途中保存をダウンロード',st.session_state.backup,'translation_project.ponte','application/zip',on_click='ignore',use_container_width=True)
    st.caption('閉じる前に保存してください。次回「資料を追加」から続きを再開できます。APIキーは保存されません。')
    if st.session_state.get('autosave_error'): st.warning(st.session_state.autosave_error)

st.markdown('<div class="eyebrow">PONTE / BOOK TRANSLATOR</div>',unsafe_allow_html=True)
st.title('原書と日本語を、となりに。')
st.markdown('<div class="intro">写真やPDFを順番に読み込み、確認しながら自分の翻訳ノートをつくる。</div>',unsafe_allow_html=True)
if st.session_state.get('notice'): st.success(st.session_state.pop('notice'))
for issue in st.session_state.pop('issues',[]): st.error(issue)
cols=st.columns(3)
cols[0].metric('取り込んだページ',len(p['pages']))
cols[1].metric('翻訳入力済み',sum(bool(x['translation']) for x in p['pages']))
cols[2].metric('確認済み',sum(x['status']=='確認済み' for x in p['pages']))
st.write('')

if step=='1　資料を追加':
    st.subheader('1. 資料をまとめて追加')
    with st.form('project_title'):
        title=st.text_input('プロジェクト名',p['title'],max_chars=150)
        if st.form_submit_button('名前を保存'):
            p['title']=title or '洋書の日本語ノート';save();st.rerun()
    uploads=st.file_uploader('JPG・PNG・PDFを選択',type=['jpg','jpeg','png','pdf'],accept_multiple_files=True)
    st.caption('1ファイル50MBまで・1プロジェクト150ページまで。写真は縦横補正後に最大2400×3200pxへ縮小します。')
    if st.button('選んだ資料を追加',type='primary',disabled=not uploads):
        import hashlib
        added=0;issues=[]
        with st.spinner('ページを取り込んでいます…'):
            for f in uploads:
                data=f.getvalue();fingerprint=hashlib.sha256(f.name.encode()+data).hexdigest()
                if fingerprint in st.session_state.added: continue
                try:
                    pages=ingest(f.name,data,MAX_PAGES-len(p['pages']))
                    p['pages'].extend(pages);st.session_state.added.append(fingerprint);added+=len(pages)
                    save()
                except Exception as exc: issues.append(f'{f.name}：{exc}')
        status_message(f'{added}ページを追加しました。同じ資料の二重追加はスキップします。')
        st.session_state.issues=issues;st.rerun()
    st.markdown('#### 続きから再開')
    restore=st.file_uploader('途中保存ファイル（.ponte）',type=['ponte'])
    confirm=st.checkbox('現在の作業を、読み込む保存データに切り替える')
    if st.button('保存データを開く',disabled=not(restore and confirm)):
        try: replace_project(unpack(restore.getvalue()));status_message('保存データを開きました。API設定は必要に応じて再入力してください。');st.rerun()
        except Exception as exc: st.error(f'読み込めませんでした：{exc}')
    with st.expander('操作デモ・新しいプロジェクト'):
        st.caption('デモはアプリで作成した短い英文と日本語です。自動翻訳の実行結果ではありません。')
        demo_file=Path(__file__).parent/'demo_project.ponte'
        replace_ok=st.checkbox('現在の作業を保存済みで、切り替えてよい')
        if st.button('デモを開く',disabled=not(replace_ok and demo_file.exists())):
            replace_project(unpack(demo_file.read_bytes()));st.rerun()
        if st.button('空のプロジェクトを作る',disabled=not replace_ok):
            replace_project(new_project());st.rerun()
    if p['pages']:
        st.markdown('#### 現在のページ順')
        st.dataframe([{'順番':i+1,'ファイル':x['source'],'ファイル内ページ':x['source_page'],'原書ページ':x['label'],'状態':x['status']} for i,x in enumerate(p['pages'])],hide_index=True,use_container_width=True)
        st.info('順番の変更や翻訳は、メニューの「2　翻訳・確認」へ進んでください。')

elif step=='一括補正・画像出力':
    from batch_photos import render
    render(p,save)

elif step=='写真の補正（無料）':
    from correction import detect_page, correct, overlay, apply_correction, restore_original, FULL_QUAD
    st.subheader('写真をまっすぐに整える')
    st.info('補正はAPIを使わず、このアプリ内で処理します。補正前の画像を残し、いつでも戻せます。先に補正してから翻訳すると確認しやすくなります。')
    st.caption('傾き・台形は自動候補と手動調整に対応。湾曲は簡易補正と、文字行をなぞる詳細補正に対応します。隠れた文字やピンぼけは復元できません。')
    if not p['pages']: st.info('「1　資料を追加」で写真かPDFを追加してください。')
    else:
        ids=[x['id'] for x in p['pages']]
        if st.session_state.get('correction_page') not in ids:st.session_state.correction_page=ids[0]
        pid=st.selectbox('補正するページ',ids,key='correction_page',format_func=lambda pid:next(f'{i+1:03d} ｜ {x["source"]} ｜ 原書 {x["label"]}' for i,x in enumerate(p['pages']) if x['id']==pid))
        page=next(x for x in p['pages'] if x['id']==pid)
        base=page.get('original_image',page['image'])
        prefix='correction_'+pid
        def set_quad(q):
            for j,point in enumerate(q):
                for axis,value in zip(('x','y'),point):st.session_state[f'{prefix}_{j}_{axis}']=float(value)
        if f'{prefix}_0_x' not in st.session_state:set_quad(FULL_QUAD)
        a,b=st.columns(2)
        if a.button('ページの四隅を自動検出',use_container_width=True):
            detected,note=detect_page(base);set_quad(detected);st.session_state[prefix+'_note']=note
        if b.button('枠を画像全体に戻す',use_container_width=True):set_quad(FULL_QUAD)
        if st.session_state.get(prefix+'_note'):st.caption(st.session_state[prefix+'_note'])
        with st.expander('四隅を調整（赤い番号と合わせてください）',expanded=True):
            quad=[]
            for j,label in enumerate(['1 左上','2 右上','3 右下','4 左下']):
                xcol,ycol=st.columns(2)
                x=xcol.number_input(label+'：横位置 %',0.,100.,step=.1,key=f'{prefix}_{j}_x')
                y=ycol.number_input(label+'：縦位置 %',0.,100.,step=.1,key=f'{prefix}_{j}_y')
                quad.append([x,y])
        st.image(overlay(base,quad),caption='補正元の画像と切り出す枠。ページ全体が枠の内側にあるか確認してください。',width=550)
        auto=st.checkbox('文字・罫線から小さな傾きを自動補正',value=True,key=prefix+'_auto')
        turns=st.selectbox('写真の向き',range(4),format_func=lambda n:['そのまま','左へ90度','180度','右へ90度'][n],key=prefix+'_turns')
        angle=st.slider('傾きの微調整（度・＋は左回り）',-20.,20.,0.,.1,key=prefix+'_angle')
        with st.expander('本のページの湾曲を調整（簡易補正）'):
            st.write('文字の行の中央が下へたわんでいる場合は＋、上へ膨らんでいる場合は−へ少しずつ調整してください。上部と下部で違う値にできます。')
            top=st.slider('上部の湾曲量（高さに対する %）',-20.,20.,0.,.5,key=prefix+'_top')
            bottom=st.slider('下部の湾曲量（高さに対する %）',-20.,20.,0.,.5,key=prefix+'_bottom')
            st.caption('曲がりを自動認識する機能ではありません。原本の図も変形するため、文字と図の両方を確認してください。端が欠ける場合は量を減らすか、補正を採用しないでください。')
        with st.expander('明るさ・コントラスト'):
            bright=st.slider('明るさ',.6,1.8,1.,.05,key=prefix+'_bright')
            contrast=st.slider('コントラスト',.6,1.8,1.,.05,key=prefix+'_contrast')
        mesh_lines=None
        with st.expander('湾曲の詳細補正：文字行に合わせる（3本×5点）'):
            mesh_enabled=st.checkbox('詳細な湾曲補正を使う',key=prefix+'_mesh_enabled')
            st.write('上部・中央・下部から文字の行を1本ずつ選び、色の線がその行の下端に重なるように表の数値を調整します。数値は画像の上端からの位置（%）です。左端・25%・中央・75%・右端の5点で曲がり方を指定します。')
            if mesh_enabled:
                import pandas as pd
                from correction import mesh_overlay
                grid=st.data_editor(pd.DataFrame([[15.]*5,[50.]*5,[85.]*5],index=['上の行（赤）','中央の行（緑）','下の行（青）'],columns=['左端','左25%','中央','右75%','右端']),key=prefix+'_mesh_grid',num_rows='fixed',use_container_width=True)
                mesh_lines=grid.to_numpy(dtype=float).tolist()
                st.caption('文字がない左右の余白は、行の曲がりを延長して指定してください。各列の線は上から赤→緑→青の順です。詳細補正を使うと、簡易補正の上下スライダーは使いません。')
                if st.button('基準線の重なりを確認',key=prefix+'_mesh_view'):
                    try:
                        base_view,_=correct(base,quad=quad,auto_skew=auto,angle=angle,quarter_turns=turns)
                        st.image(mesh_overlay(base_view,mesh_lines),caption='台形・傾き補正後の画像に基準線を表示',use_container_width=True)
                    except Exception as exc:st.error(str(exc))
        settings=dict(quad=quad,auto_skew=auto,angle=angle,quarter_turns=turns,top=top,bottom=bottom,brightness=bright,contrast=contrast,mesh_lines=mesh_lines)
        if st.button('補正結果をプレビュー',type='primary'):
            try:
                with st.spinner('補正しています…'):data,details=correct(base,**settings)
                st.session_state[prefix+'_preview']={'data':data,'details':details,'settings':settings}
            except Exception as exc:st.error(str(exc))
        preview=st.session_state.get(prefix+'_preview')
        if preview and preview['settings']==settings:
            before,after=st.columns(2)
            before.image(base,caption='補正前',use_container_width=True)
            after.image(preview['data'],caption='補正後（未採用）',use_container_width=True)
            st.caption(f'自動傾き補正：{preview["details"]["detected_angle"]}度。文字や図が欠けていないか確認してください。')
            st.download_button('補正画像だけダウンロード',preview['data'],'corrected_page.jpg','image/jpeg',on_click='ignore')
            st.caption('採用すると翻訳とPDFに使う画像が切り替わります。座標が変わるため図の切出し設定と過去の編集履歴はリセットし、訳文は残して「要確認」に戻します。')
            if st.button('この補正を採用する',type='primary'):
                apply_correction(page,preview['data'],preview['details']);save();status_message('補正を採用しました。以降の翻訳・出力は補正後の画像を使います。');st.rerun()
        elif preview:st.info('設定が変わりました。「補正結果をプレビュー」をもう一度押してください。')
        if page.get('original_image'):
            st.success('このページは補正済みです。')
            st.download_button('補正前の画像を保存',page['original_image'],'before_correction.jpg','image/jpeg',on_click='ignore')
            if st.button('補正前の画像に戻す'):
                restore_original(page);st.session_state.pop(prefix+'_preview',None);save();status_message('補正前の画像に戻しました。');st.rerun()

elif step=='3　用語辞書':
    st.subheader('専門用語を、同じ訳語に')
    st.caption('「英語 → 日本語」を1行ずつ登録してください。登録後の翻訳・再翻訳で使用します。過去の訳文は自動変更しません。')
    with st.form('glossary'):
        glossary=st.text_area('用語辞書',p['glossary'].replace('\t',' → '),height=330)
        if st.form_submit_button('辞書を保存',type='primary'):
            try:
                terms=glossary_dict(glossary)
                p['glossary']='\n'.join(k+'\t'+v for k,v in terms.items());save();status_message(f'{len(terms)}語を保存しました。');st.rerun()
            except ValueError as exc: st.error(str(exc))
    st.download_button('辞書をダウンロード',p['glossary'].encode('utf-8-sig'),'glossary.tsv','text/tab-separated-values',on_click='ignore')
    glossary_file=st.file_uploader('辞書を読み込む（TSV・TXT）',type=['tsv','txt'])
    if st.button('辞書を読み込んで置き換える',disabled=not glossary_file):
        try:
            text=glossary_file.getvalue().decode('utf-8-sig');glossary_dict(text)
            p['glossary']=text;save();st.rerun()
        except Exception as exc: st.error(str(exc))

elif step=='2　翻訳・確認':
    st.subheader('2. 原書と見比べて、翻訳を確認')
    if not p['pages']: st.info('「1　資料を追加」で写真かPDFを追加してください。')
    else:
        with st.expander('未翻訳ページを順番に自動翻訳',expanded=False):
            st.caption('1回に処理する枚数を決めて実行します。入力済みの訳文はスキップ。途中で失敗したら停止し、完了分は保持します。')
            count=st.number_input('今回処理するページ数',min_value=1,max_value=30,value=5,step=1)
            wait=st.number_input('ページ間の待ち時間（秒）',min_value=0,max_value=60,value=5,step=1)
            if st.button('未翻訳ページを翻訳する',type='primary',disabled=provider=='手動（APIなし）' or not key):
                targets=[x for x in p['pages'] if not x['translation']][:count]
                progress=st.progress(0);completed=0;issues=[]
                if not targets: st.info('未翻訳ページはありません。')
                for i,page in enumerate(targets):
                    try:
                        with st.spinner(f'{i+1}/{len(targets)}：{page["source"]} を翻訳中…'):
                            run_translation(page,provider,key,model,p['glossary'],instructions)
                        completed+=1;progress.progress((i+1)/len(targets))
                        st.download_button(f'{completed}ページ完了時点の保存',st.session_state.backup,'translation_project.ponte','application/zip',key='checkpoint_'+str(st.session_state.rev),on_click='ignore')
                        if i<len(targets)-1 and wait: time.sleep(wait)
                    except Exception as exc:
                        page['error']=str(exc);save();issues.append(f'停止しました：{exc}');break
                if targets:
                    status_message(f'{completed}ページ処理しました。完了した翻訳は「要確認」として保存しています。')
                    st.session_state.issues=issues;st.rerun()
        ids=[x['id'] for x in p['pages']]
        if st.session_state.get('selected_page') not in ids: st.session_state.selected_page=ids[0]
        selected=st.selectbox('確認するページ',ids,key='selected_page',format_func=lambda pid:next(f'{i+1:03d} ｜ 原書 {x["label"]} ｜ {x["status"]} ｜ {x["source"]}' for i,x in enumerate(p['pages']) if x['id']==pid))
        index=ids.index(selected);page=p['pages'][index]
        a,b,c=st.columns([1,1,3])
        if a.button('↑ 前へ移動',disabled=index==0,use_container_width=True):
            p['pages'][index-1],p['pages'][index]=p['pages'][index],p['pages'][index-1];save();st.rerun()
        if b.button('↓ 後ろへ移動',disabled=index==len(ids)-1,use_container_width=True):
            p['pages'][index+1],p['pages'][index]=p['pages'][index],p['pages'][index+1];save();st.rerun()
        dest=c.number_input('移動先の順番',1,len(ids),index+1,key='dest_'+selected)
        if c.button('指定した順番へ移動'):
            p['pages'].insert(dest-1,p['pages'].pop(index));save();st.rerun()
        left,right=st.columns(2,gap='large')
        with left:
            st.markdown('#### 原本')
            st.image(page['image'],caption=f'{page["source"]} ／ ファイル内 {page["source_page"]}ページ',use_container_width=True)
            st.download_button('原本画像を保存',page['image'],f'source_{index+1:03d}.jpg','image/jpeg',on_click='ignore')
        with right:
            st.markdown('#### 日本語版')
            if page['error']: st.error(page['error'])
            if provider!='手動（APIなし）':
                overwrite=st.checkbox('現在の翻訳を再翻訳で置き換える（過去5回分の履歴を保持）') if page['translation'] else True
                if st.button('このページを再翻訳' if page['translation'] else 'このページを翻訳',type='primary',disabled=not(key and overwrite)):
                    try:
                        with st.spinner('文字と図の範囲を読み取って翻訳中…'): run_translation(page,provider,key,model,p['glossary'],instructions)
                        st.rerun()
                    except Exception as exc:
                        page['error']=str(exc);save();st.session_state.issues=[str(exc)];st.rerun()
            with st.form('edit_'+selected+'_'+str(st.session_state.rev)):
                label=st.text_input('原書ページ番号・表紙など',page['label'])
                heading=st.text_input('日本語見出し',page['title'])
                translation=st.text_area('日本語訳（全文）',page['translation'],height=350)
                original=st.text_area('読み取った英文・修正欄',page['original'],height=150)
                notes=st.text_area('要確認メモ',page['notes'],height=80)
                reviewed=st.checkbox('原本と照合し、このページを確認済みにする',value=page['status']=='確認済み')
                if st.form_submit_button('編集を保存',type='primary'):
                    result={'title':heading,'label':label,'translation':translation,'original':original,'notes':notes,'figures':page['figures']}
                    apply_result(page,result,page.get('provider','手動'),page.get('model',''))
                    page['status']='確認済み' if reviewed and translation.strip() else ('要確認' if translation.strip() else '未翻訳')
                    save();status_message('編集を保存しました。');st.rerun()
            st.caption('編集したら「編集を保存」を押してください。日本語版は読みやすく再配置し、原書と完全同一の組版にはしません。')
        with st.expander('図・写真を日本語側にも掲載する'):
            st.caption('図の座標を確認・修正できます。左・上・右・下は画像全体を0〜1000で表した値です。本文の範囲は含めないでください。図中の英文は元画像のまま残ります。')
            fig_text=st.text_area('図の範囲（JSON）',json.dumps(page['figures'],ensure_ascii=False,indent=2),height=160,key='fig_'+selected+'_'+str(st.session_state.rev))
            if st.button('図の範囲を保存'):
                try:
                    page['figures']=normalize_result({'original':'x','translation':'x','figures':json.loads(fig_text)})['figures']
                    page['status']='要確認' if page['translation'] else '未翻訳';save();st.rerun()
                except Exception as exc: st.error(str(exc))
            for f in page['figures']: st.image(figure_bytes(page,f),caption=f['caption'],width=320)
        with st.expander('APIなし：ChatGPTで翻訳して貼り付ける'):
            st.write('① 原本画像を保存 → ② ChatGPTへ画像と下記の指示を送信 → ③ 日本語訳を上の欄に貼り付けて保存。JSON形式の回答は下の欄で読み込めます。')
            st.code(make_prompt(p['glossary'],instructions),language=None)
            response=st.text_area('JSON形式の翻訳回答を貼り付け',height=130)
            if st.button('翻訳回答を読み込む'):
                try: apply_result(page,parse_result(response),'手動','');save();st.rerun()
                except Exception as exc: st.error(f'読み込めません：{exc}')
        with st.expander('変更履歴・ページの削除'):
            if page['history']:
                version=st.selectbox('過去の編集',range(len(page['history'])),format_func=lambda i:f'{i+1} / {len(page["history"])}（大きい番号ほど新しい）')
                st.text(page['history'][version].get('translation','')[:1000])
                if st.button('選んだ履歴に戻す'):
                    old=page['history'][version].copy();apply_result(page,old);save();st.rerun()
            delete_ok=st.checkbox('このページを削除する')
            if st.button('ページを削除',disabled=not delete_ok):
                p['pages'].pop(index);save();st.rerun()

elif step=='4　出力':
    st.subheader('3. 確認した翻訳を、まとめて出力')
    st.write(p['title'])
    if not p['pages']: st.info('資料を追加してください。')
    else:
        unreviewed=sum(x['status']!='確認済み' for x in p['pages'])
        if unreviewed: st.info(f'{unreviewed}ページが未確認です。確認済みだけ出力するか、下書きとして全ページを出力できます。')
        only_reviewed=st.checkbox('確認済みのページだけ出力する')
        include_figures=st.checkbox('日本語ページにも図・写真を掲載',value=True)
        font_size=st.slider('PDF本文の文字サイズ',9.0,14.0,10.5,.5)
        st.caption('見開きPDF＝1枚の横長ページで左に原本・右に日本語。交互PDF＝原本→日本語の順。長文は続きのページへ送り、原本も再掲します。')
        options=(only_reviewed,include_figures,font_size)
        if st.button('PDF・Word・一括ZIPを作成',type='primary'):
            target={**p,'pages':[x for x in p['pages'] if not only_reviewed or x['status']=='確認済み']}
            if not target['pages']: st.warning('出力対象のページがありません。')
            else:
                try:
                    with st.spinner('日本語フォントを埋め込んで出力中…'):
                        files,bundle=export_bundle(target,include_figures,font_size)
                    st.session_state.google_url=None
                    st.session_state.exports={'options':options,'files':files,'zip':bundle,'rev':st.session_state.rev}
                except Exception as exc: st.error(f'出力できませんでした：{exc}')
        result=st.session_state.exports
        if result and result['options']==options and result['rev']==st.session_state.rev:
            st.success('出力できました。ダウンロードしても結果はそのまま残ります。')
            names={'facing_pages.pdf':'見開きPDF','alternating_pages.pdf':'原本・日本語 交互PDF','japanese_only.pdf':'日本語のみPDF','translation.docx':'Word（Google Docs取込用）','translation.txt':'日本語テキスト'}
            st.download_button('📦 すべて一括ダウンロード',result['zip'],'translation_exports.zip','application/zip',on_click='ignore',use_container_width=True)
            for name,label in names.items():
                mime='application/pdf' if name.endswith('.pdf') else ('application/vnd.openxmlformats-officedocument.wordprocessingml.document' if name.endswith('.docx') else 'text/plain')
                st.download_button(label,result['files'][name],name,mime,on_click='ignore')
            with st.expander('見開きPDFの先頭をプレビュー',expanded=True):
                import fitz
                with fitz.open(stream=result['files']['facing_pages.pdf'],filetype='pdf') as doc:
                    st.image(doc[0].get_pixmap(matrix=fitz.Matrix(1,1)).tobytes('png'),use_container_width=True)
                    st.caption(f'全{len(doc)}見開き。文字や図を確認してから利用してください。')
            st.markdown('#### Googleドキュメント')
            st.write('手軽な方法：Wordをダウンロード → Google Driveへアップロード →「Googleドキュメントで開く」。文章を編集できます。')
            st.caption('Google DocsやWordでは改ページ・画像配置が変わる場合があります。左右の配置を固定したい場合は見開きPDFを使用してください。')
            with st.expander('直接出力する（初回にGoogle連携設定が必要）'):
                st.caption('同梱の GOOGLE_SETUP.md に従い、ご自身のPCで google_token.json を作成して読み込みます。この情報は途中保存に含みません。')
                token_file=st.file_uploader('google_token.json',type=['json'])
                confirm_upload=st.checkbox('現在の出力内容を自分のGoogle Driveへ送信する')
                if st.button('Googleドキュメントを新規作成',disabled=not(token_file and confirm_upload) or bool(st.session_state.google_url)):
                    try:
                        with st.spinner('Googleドキュメントを作成中…'):
                            st.session_state.google_url=upload_docx(result['files']['translation.docx'],p['title'],json.loads(token_file.getvalue()))
                    except Exception:
                        st.error('Googleへの出力を確認できませんでした。認証設定を確認してください。再実行前にDriveを開き、文書が作成されていないか確認してください。')
                if st.session_state.google_url:
                    st.link_button('作成したGoogleドキュメントを開く',st.session_state.google_url)
        elif result: st.info('出力設定が変わりました。「PDF・Word・一括ZIPを作成」をもう一度押してください。')

st.divider()
st.caption('保存について：編集中はセッション内とサーバーの一時領域に保存します。ブラウザ終了やサーバー再起動後の復元には「途中保存」ファイルを使ってください。')
