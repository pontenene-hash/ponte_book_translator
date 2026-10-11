"""Three-step photo preparation UI. Translation happens in ChatGPT."""
import base64,hashlib,io,json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from core import ingest,MAX_PAGES,pack,unpack
from correction import correct,detect_page,apply_correction,restore_original,FULL_QUAD
from orientation import orient
from batch_photos import export_photos
from handoff import handoff_files

editor=components.declare_component('ponte_photo_points',path=str(Path(__file__).parent/'curve_editor'))
STEPS=['① 写真を入れる','② 補正を確認','③ ChatGPT用に保存']

def save_html(data,filename,mime):
    """Share a local File, or download in a separate tab; never navigate the app."""
    payload=json.dumps({'data':base64.b64encode(data).decode(),'name':filename,'mime':mime},ensure_ascii=True).replace('<','\\u003c')
    return '''<!doctype html><html lang="ja"><meta charset="utf-8">
<style>body{font:16px system-ui;margin:0;color:#214d47}button,a{box-sizing:border-box;display:block;width:100%;padding:14px;border:1px solid #b8c8bd;border-radius:10px;background:#fff;color:#214d47;text-align:center;font:inherit;text-decoration:none;margin:8px 0;cursor:pointer}button:disabled{opacity:.5}p{font-size:14px;line-height:1.6;margin:8px 0}#share{background:#214d47;color:white} [hidden]{display:none!important}</style>
<button id="share" disabled>保存の準備中…</button>
<a id="download" hidden target="_blank" rel="noopener noreferrer">別タブで保存する</a>
<p id="status" role="status" aria-live="polite">準備が終わるまでお待ちください。</p>
<script>
const payload='''+payload+''';
const share=document.getElementById('share'), link=document.getElementById('download'), status=document.getElementById('status');
let file, url;
try {
  // Decode in blocks to avoid a second whole-file binary string for large ZIPs.
  const chunks=[];
  for(let i=0;i<payload.data.length;i+=1048576){
    const raw=atob(payload.data.slice(i,i+1048576));
    const bytes=new Uint8Array(raw.length);
    for(let j=0;j<raw.length;j++) bytes[j]=raw.charCodeAt(j);
    chunks.push(bytes);
  }
  file=new File(chunks,payload.name,{type:payload.mime});
  payload.data='';
  url=URL.createObjectURL(file);link.href=url;link.download=payload.name;
  let supported=false;
  try { supported=!!(navigator.share && navigator.canShare && navigator.canShare({files:[file]})); } catch (_) {}
  share.hidden=!supported;share.disabled=false;link.hidden=false;
  share.textContent='共有メニューから保存';
  status.textContent=supported?'上のボタンを押し「ファイルに保存」を選んでください。キャンセルしてもアプリに戻れます。':'この環境では共有保存を使えません。Safariで開き、下の説明を確認して別タブで保存してください。';
} catch (_) {
  share.hidden=true;
  status.textContent='保存の準備に失敗しました。写真を少なくして作り直すか、パソコンで開いてください。';
}
share.addEventListener('click',async()=>{
  share.disabled=true;
  try {
    // Invoke directly in the user's click, before any asynchronous work.
    await navigator.share({files:[file]});
    status.textContent='共有画面を閉じました。保存先を確認してください。続けて他のファイルも選べます。';
  } catch (e) {
    status.textContent=e.name==='AbortError'?'キャンセルしました。写真や補正内容はそのままです。':'共有できませんでした。Safariで開くか「別タブで保存する」を使ってください。';
  } finally { share.disabled=false; }
});
link.addEventListener('click',()=>{status.textContent='元のアプリはこのタブに残っています。別画面が開いたらSafariのタブ一覧から元のタブへ戻ってください。';});
window.addEventListener('pagehide',()=>{if(url) URL.revokeObjectURL(url);});
</script></html>'''

def save_file(data,filename,mime):
    components.html(save_html(data,filename,mime),height=260,scrolling=True)

def rotate_page(page,turns):
    image,settings=correct(page['image'],auto_skew=False,quarter_turns=turns)
    apply_correction(page,image,settings);page['photo_reviewed']=False

def prepare(page,crop=False,auto_curve=True,auto_light=True):
    image,note=orient(page.get('original_image',page['image']))
    quad,_=detect_page(image) if crop else (None,'')
    if quad==FULL_QUAD:quad=None
    try:
        image,settings=correct(image,quad=quad,preserve_frame=True,auto_curve=auto_curve,auto_light=auto_light)
    except ValueError:
        image,settings=correct(image,auto_curve=auto_curve,auto_light=auto_light)
        note+=' 四隅の変形が大きいため、四隅補正は見送りました。'
    apply_correction(page,image,settings);page['photo_reviewed']=False
    return note+' '+settings.get('curve_note','')

def render(project,save,replace_project):
    def go(n):st.session_state.pending_step=STEPS[n]
    def move(n):st.session_state.pending_page=n
    for pending,target in [('pending_step','simple_step'),('pending_page','simple_page')]:
        if pending in st.session_state:st.session_state[target]=st.session_state.pop(pending)
    st.title('写真を整えて、ChatGPTへ')
    st.caption('v2.1.1 ・ 端を保持・明るさ調整・自動湾曲補正')
    st.radio('作業の順番',STEPS,horizontal=True,key='simple_step')
    step=st.session_state.simple_step
    pages=project['pages']
    with st.expander('途中保存・再開／本の名前・用語辞書'):
        title=st.text_input('本の名前',project['title'],key='simple_title_'+project['id'])
        glossary=st.text_area('用語辞書（英語 → 日本語）',project['glossary'],key='simple_glossary_'+project['id'])
        if title!=project['title'] or glossary!=project['glossary']:
            project['title']=title;project['glossary']=glossary;save()
        if st.checkbox('途中保存のボタンを表示',key='show_checkpoint_save'):
            save_file(pack(project),'photo_project.ponte','application/octet-stream')
        upload=st.file_uploader('途中保存から再開',type=['ponte'],key='simple_restore')
        if st.button('保存した作業を開く',disabled=upload is None):
            try:
                replace_project(unpack(upload.getvalue()));st.session_state.simple_page=0
                st.session_state.pop('simple_result',None);st.rerun()
            except Exception as e:st.error(str(e))
        st.caption('画面を閉じる前に途中保存してください。')
    for message in st.session_state.pop('simple_errors',[]):st.error(message)
    if step==STEPS[0]:
        st.subheader('写真・PDFをまとめて選んでください')
        uploads=st.file_uploader('JPG・PNG・PDF',type=['jpg','jpeg','png','pdf'],accept_multiple_files=True,key='simple_upload')
        st.caption('1ファイル50MBまで。HEICはJPEGに変換してください。')
        if st.button('写真を取り込む',type='primary',disabled=not uploads,use_container_width=True):
            errors=[]
            with st.spinner('取り込んでいます…'):
                for f in uploads:
                    data=f.getvalue();token=hashlib.sha256(f.name.encode()+data).hexdigest()
                    if token in st.session_state.added:continue
                    try:
                        pages.extend(ingest(f.name,data,MAX_PAGES-len(pages)))
                        st.session_state.added.append(token);save()
                    except Exception as e:errors.append(f'{f.name}：{e}')
            st.session_state.simple_errors=errors
            if pages:go(1)
            st.rerun()
        if pages:
            st.success('写真が入っています。補正の確認へ進めます。')
            st.button('補正を確認する →',on_click=go,args=(1,),use_container_width=True)
        return
    if not pages:
        st.info('まず写真・PDFを入れてください。');st.button('写真を入れる',on_click=go,args=(0,));return
    if step==STEPS[1]:
        st.subheader('文字が上向きで、端まで読めるか確認')
        st.caption('自動補正は取り込み時の写真からやり直します。端を切り取らず、文字の欠けを防ぎます。')
        crop=st.checkbox('四隅の遠近も補正する（画像全体を保持）',value=False)
        auto_curve=st.checkbox('本文の湾曲を自動補正する',value=True)
        auto_light=st.checkbox('暗い写真を自動で明るくする',value=True)
        redo=st.checkbox('補正済みの写真も原本からまとめてやり直す',value=False)
        if redo:st.caption('手動で調整した向き・湾曲・明るさもやり直します。元の写真は保持します。')
        if st.button('向き・傾きをまとめて自動補正',type='primary',use_container_width=True):
            targets=[p for p in pages if redo or (not p.get('correction') and not p.get('photo_reviewed'))]
            bar=st.progress(0)
            for i,p in enumerate(targets):
                try:
                    note=prepare(p,crop,auto_curve,auto_light);st.session_state['orient_'+p['id']]=note;save()
                except Exception as e:st.session_state['orient_'+p['id']]='補正できませんでした：'+str(e)
                bar.progress((i+1)/len(targets))
            if not targets:st.info('未補正の写真はありません。やり直す場合は「取り込み時に戻す」を押してください。')
        index=min(st.session_state.get('simple_page',0),len(pages)-1)
        st.session_state.simple_page=index
        idx=st.selectbox('確認する写真',range(len(pages)),format_func=lambda i:f'{i+1}｜{pages[i]["source"]}'+(' ✓' if pages[i].get('photo_reviewed') else ''),key='simple_page')
        page=pages[idx];pid=page['id'];sig=hashlib.sha256(page['image']).hexdigest()[:12]
        st.image(page['image'],use_container_width=True)
        def accept_photo():
            page['photo_reviewed']=True;save()
            remaining=[i for i in range(idx+1,len(pages)) if not pages[i].get('photo_reviewed')]+[i for i in range(idx) if not pages[i].get('photo_reviewed')]
            if remaining:move(remaining[0])
            else:go(2)
        st.button('この写真でOK → 次へ',key='accept_photo_preview',on_click=accept_photo,type='primary',use_container_width=True)
        with st.expander('取り込み時の写真と比較'):
            st.image(page.get('original_image',page['image']),caption='取り込み時の写真：文字の欠け・曲がりを比較してください。',use_container_width=True)
        with st.expander('明るさ・コントラストを調整'):
            light=st.slider('明るさ',0.6,1.6,1.0,0.05,key='light_'+pid+'_'+sig)
            contrast=st.slider('コントラスト',0.7,1.4,1.0,0.05,key='contrast_'+pid+'_'+sig)
            if light!=1. or contrast!=1.:
                lit,lit_settings=correct(page['image'],auto_skew=False,brightness=light,contrast=contrast)
                st.image(lit,caption='明るさのプレビュー',use_container_width=True)
                if st.button('この明るさを使う'):
                    apply_correction(page,lit,lit_settings);page['photo_reviewed']=False;save();st.rerun()
        if st.session_state.get('orient_'+pid):st.caption(st.session_state['orient_'+pid])
        a,b,c=st.columns(3)
        for col,label,turn in [(a,'↶ 左回転',1),(b,'↷ 右回転',-1),(c,'上下反転',2)]:
            if col.button(label,use_container_width=True):rotate_page(page,turn);save();st.rerun()
        st.caption('横向き・逆さの場合は上のボタンで直せます。自動判定も必ず目で確認してください。')
        with st.expander('湾曲・切り取りを調整する'):
            mode=st.radio('調整する内容',['湾曲を伸ばす','紙の四隅を合わせる'],horizontal=True)
            quad=mode=='紙の四隅を合わせる'
            trim=st.checkbox('枠の外を切り取る（文字が欠けないか確認）',value=False) if quad else False
            points=FULL_QUAD if quad else [[x,y] for y in (20.,50.,80.) for x in (0.,25.,50.,75.,100.)]
            identity=f'{pid}_{sig}_{quad}'
            result=editor(image='data:image/jpeg;base64,'+base64.b64encode(page['image']).decode(),points=points,mode='quad' if quad else 'curve',identity=identity,key=identity,default=points)
            try:
                settings={'quad':result,'preserve_frame':not trim} if quad else {'mesh_lines':[[result[i*5+j][1] for j in range(5)] for i in range(3)]}
                preview,meta=correct(page['image'],auto_skew=False,**settings)
                st.image(preview,caption='この仕上がりで保存します',use_container_width=True)
                if st.button('この調整を使う',type='primary'):
                    apply_correction(page,preview,meta);page['photo_reviewed']=False;save();st.rerun()
            except (ValueError,IndexError,TypeError) as e:st.warning('点を上から順に、線が交差しないように配置してください。'+str(e))
            st.caption('湾曲は文字の行を伸ばす補正です。折れ目や隠れた文字の復元はできません。')
        a,b=st.columns(2)
        if a.button('取り込み時に戻す',disabled='original_image' not in page):
            restore_original(page);st.session_state.pop('orient_'+pid,None);save();st.rerun()
        if b.button('この写真だけ自動補正'):
            try:
                st.session_state['orient_'+pid]=prepare(page,crop,auto_curve,auto_light);save();st.rerun()
            except Exception as e:st.error('補正できませんでした：'+str(e))
        a,b=st.columns(2)
        if a.button('順番を前へ',disabled=idx==0):
            pages[idx-1],pages[idx]=pages[idx],pages[idx-1];save();move(idx-1);st.rerun()
        if b.button('順番を後ろへ',disabled=idx==len(pages)-1):
            pages[idx+1],pages[idx]=pages[idx],pages[idx+1];save();move(idx+1);st.rerun()
        st.button('この写真でOK → 次へ',key='accept_photo_bottom',on_click=accept_photo,type='primary',use_container_width=True)
        st.button('保存画面へ →',on_click=go,args=(2,),use_container_width=True)
        return
    def back_buttons(position):
        st.button('← 補正画面に戻る',key='back_review_'+position,on_click=go,args=(1,),use_container_width=True)
        st.button('＋ 写真を追加する',key='back_upload_'+position,on_click=go,args=(0,),use_container_width=True)
    st.subheader('ChatGPTに渡すファイルを保存')
    back_buttons('top')
    st.caption('戻っても写真・補正内容は保持されます。保存したファイルのプレビューを開いている場合は、先にプレビューを閉じてください。')
    if any(not p.get('photo_reviewed') for p in pages):
        st.warning('未確認の写真があります。文字の向き・湾曲・端の欠けを確認してください。')
        st.button('未確認の写真を見る',on_click=lambda:(move(next(i for i,p in enumerate(pages) if not p.get('photo_reviewed'))),go(1)),use_container_width=True)
        return
    if st.button('ChatGPT用ファイルを作る',type='primary',use_container_width=True):
        with st.spinner('PDFと依頼文を作っています…'):
            images,pdf=export_photos(pages);prompt,bundle=handoff_files(project,pages,pdf)
            st.session_state.simple_result={'revision':st.session_state.rev,'pdf':pdf,'prompt':prompt,'bundle':bundle,'images':images}
    result=st.session_state.get('simple_result')
    if result and result['revision']==st.session_state.rev:
        st.success('できました！ PDFと依頼文の2つをChatGPTへ添付してください。')
        st.info('iPhoneでは「共有メニューから保存」→「ファイルに保存」を選びます。PDFと依頼文を1つずつ保存してください。ZIPは通常不要です。')
        st.caption('別タブで保存する場合はSafariで開いてください。保存後はSafariのタブ一覧から元のアプリに戻れます。ホーム画面から開いた画面や他のアプリ内ブラウザでは、戻る操作が表示されない場合があります。')
        choices={'① 補正済みPDF':('pdf','corrected_pages.pdf','application/pdf'),
                 '② 翻訳の依頼文':('prompt','ChatGPT_prompt.txt','text/plain'),
                 'PDF＋依頼文のZIP（任意）':('bundle','ChatGPT_handoff.zip','application/zip'),
                 '写真のZIP（任意）':('images','corrected_images.zip','application/zip')}
        choice=st.selectbox('保存するファイル',list(choices),key='save_file_choice')
        data_key,filename,mime=choices[choice]
        # Send only the selected file to the browser, not all large ZIPs at once.
        save_file(result[data_key],filename,mime)
        st.info('ChatGPTにPDFと依頼文を添付し「添付の依頼文に沿って対訳PDFと編集用Wordを作ってください」と送信します。アプリに翻訳を貼り戻す操作は不要です。')
        st.caption('続きの場合は前回の統合版PDF・用語辞書・作業記録も添付してください。原本の印刷ページ番号を使用します。')
        st.caption('PDFの画像を読めない場合は「写真のZIP」を保存・展開してJPGをChatGPTへ添付してください。')
        st.divider()
        back_buttons('bottom')
