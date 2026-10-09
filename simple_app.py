"""Three-step photo preparation UI. Translation happens in ChatGPT."""
import base64,hashlib,io
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

def rotate_page(page,turns):
    image,settings=correct(page['image'],auto_skew=False,quarter_turns=turns)
    apply_correction(page,image,settings);page['photo_reviewed']=False

def prepare(page,crop=True):
    image,note=orient(page['image'])
    quad,_=detect_page(image) if crop else (None,'')
    if quad==FULL_QUAD:quad=None
    image,settings=correct(image,quad=quad)
    apply_correction(page,image,settings);page['photo_reviewed']=False
    return note

def render(project,save,replace_project):
    def go(n):st.session_state.pending_step=STEPS[n]
    def move(n):st.session_state.pending_page=n
    for pending,target in [('pending_step','simple_step'),('pending_page','simple_page')]:
        if pending in st.session_state:st.session_state[target]=st.session_state.pop(pending)
    st.title('写真を整えて、ChatGPTへ')
    st.caption('v2.0.1 ・ 補正と出力は無料・APIキー不要')
    st.radio('作業の順番',STEPS,horizontal=True,key='simple_step')
    step=st.session_state.simple_step
    pages=project['pages']
    with st.expander('途中保存・再開／本の名前・用語辞書'):
        title=st.text_input('本の名前',project['title'],key='simple_title_'+project['id'])
        glossary=st.text_area('用語辞書（英語 → 日本語）',project['glossary'],key='simple_glossary_'+project['id'])
        if title!=project['title'] or glossary!=project['glossary']:
            project['title']=title;project['glossary']=glossary;save()
        st.download_button('途中保存',pack(project),'photo_project.ponte',on_click='ignore')
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
        crop=st.checkbox('紙の四隅も自動で補正する',value=True)
        if st.button('向き・傾きをまとめて自動補正',type='primary',use_container_width=True):
            targets=[p for p in pages if not p.get('correction') and not p.get('photo_reviewed')]
            bar=st.progress(0)
            for i,p in enumerate(targets):
                try:
                    note=prepare(p,crop);st.session_state['orient_'+p['id']]=note;save()
                except Exception as e:st.session_state['orient_'+p['id']]='補正できませんでした：'+str(e)
                bar.progress((i+1)/len(targets))
            if not targets:st.info('未補正の写真はありません。やり直す場合は「取り込み時に戻す」を押してください。')
        index=min(st.session_state.get('simple_page',0),len(pages)-1)
        st.session_state.simple_page=index
        idx=st.selectbox('確認する写真',range(len(pages)),format_func=lambda i:f'{i+1}｜{pages[i]["source"]}'+(' ✓' if pages[i].get('photo_reviewed') else ''),key='simple_page')
        page=pages[idx];pid=page['id'];sig=hashlib.sha256(page['image']).hexdigest()[:12]
        st.image(page['image'],use_container_width=True)
        if st.session_state.get('orient_'+pid):st.caption(st.session_state['orient_'+pid])
        a,b,c=st.columns(3)
        for col,label,turn in [(a,'↶ 左回転',1),(b,'↷ 右回転',-1),(c,'上下反転',2)]:
            if col.button(label,use_container_width=True):rotate_page(page,turn);save();st.rerun()
        st.caption('横向き・逆さの場合は上のボタンで直せます。自動判定も必ず目で確認してください。')
        with st.expander('湾曲・切り取りを調整する'):
            mode=st.radio('調整する内容',['湾曲を伸ばす','紙の四隅を合わせる'],horizontal=True)
            quad=mode=='紙の四隅を合わせる'
            points=FULL_QUAD if quad else [[x,y] for y in (20.,50.,80.) for x in (0.,25.,50.,75.,100.)]
            identity=f'{pid}_{sig}_{quad}'
            result=editor(image='data:image/jpeg;base64,'+base64.b64encode(page['image']).decode(),points=points,mode='quad' if quad else 'curve',identity=identity,key=identity,default=points)
            try:
                settings={'quad':result} if quad else {'mesh_lines':[[result[i*5+j][1] for j in range(5)] for i in range(3)]}
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
                st.session_state['orient_'+pid]=prepare(page,crop);save();st.rerun()
            except Exception as e:st.error('補正できませんでした：'+str(e))
        a,b=st.columns(2)
        if a.button('順番を前へ',disabled=idx==0):
            pages[idx-1],pages[idx]=pages[idx],pages[idx-1];save();move(idx-1);st.rerun()
        if b.button('順番を後ろへ',disabled=idx==len(pages)-1):
            pages[idx+1],pages[idx]=pages[idx],pages[idx+1];save();move(idx+1);st.rerun()
        if st.button('この写真でOK → 次へ',type='primary',use_container_width=True):
            page['photo_reviewed']=True;save()
            remaining=[i for i in range(idx+1,len(pages)) if not pages[i].get('photo_reviewed')]+[i for i in range(idx) if not pages[i].get('photo_reviewed')]
            if remaining:move(remaining[0])
            else:go(2)
            st.rerun()
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
        st.download_button('① 補正済みPDFを保存',result['pdf'],'corrected_pages.pdf','application/pdf',on_click='ignore',use_container_width=True)
        st.download_button('② 翻訳の依頼文を保存',result['prompt'],'ChatGPT_prompt.txt','text/plain',on_click='ignore',use_container_width=True)
        st.info('ChatGPTに2つを添付し「添付の依頼文に沿って対訳PDFを作ってください」と送信します。アプリに翻訳を貼り戻す操作は不要です。')
        st.caption('続きの場合は前回の統合版PDF・用語辞書・作業記録も添付してください。原本の印刷ページ番号を使用します。')
        with st.expander('まとめて保存／写真として渡す'):
            st.download_button('PDF＋依頼文のZIP',result['bundle'],'ChatGPT_handoff.zip',on_click='ignore')
            st.download_button('写真のZIP',result['images'],'corrected_images.zip',on_click='ignore')
            st.caption('PDFの画像を読めない場合は、写真のZIPを展開してJPGをChatGPTへ添付してください。')
        st.divider()
        back_buttons('bottom')
