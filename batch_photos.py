"""Batch photo preparation, review, and image-only export. No API calls."""
import io,json,zipfile,hashlib
import fitz
from PIL import Image
from correction import detect_page,correct,apply_correction,FULL_QUAD

def signature(page):return hashlib.sha256(page['image']).hexdigest()

def prepare_candidate(page,auto_crop=True,auto_skew=True):
    base=page.get('original_image',page['image'])
    quad,note=detect_page(base) if auto_crop else (None,'台形補正なし。画像全体を保持。')
    if quad==FULL_QUAD:quad=None;note+=' 台形補正を見送り、画像全体を保持しました。'
    image,settings=correct(base,quad=quad,auto_skew=auto_skew)
    return {'image':image,'settings':settings,'note':note,'signature':signature(page)}

def adopt(page,candidate):
    if signature(page)!=candidate['signature']:raise ValueError('候補作成後に画像が変更されています。候補を作り直してください。')
    apply_correction(page,candidate['image'],candidate['settings'])
    page['photo_reviewed']=True

def export_photos(pages):
    if not pages:raise ValueError('出力するページを選んでください。')
    out=io.BytesIO();pdf=fitz.open();mapping=[]
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(pages,1):
            name=f'page_{i:04d}.jpg';z.writestr(name,p['image'])
            with Image.open(io.BytesIO(p['image'])) as im:w,h=im.size
            scale=842/max(w,h);page=pdf.new_page(width=w*scale,height=h*scale)
            page.insert_image(page.rect,stream=p['image'])
            mapping.append({'output_file':name,'source':p['source'],'source_page':p['source_page'],'printed_page':p['label'],'corrected':bool(p.get('original_image')),'reviewed':bool(p.get('photo_reviewed'))})
        z.writestr('page_order.json',json.dumps(mapping,ensure_ascii=False,indent=2))
    data=pdf.tobytes(garbage=4,deflate=True);pdf.close()
    return out.getvalue(),data

def render(project,save):
    import streamlit as st
    st.subheader('まとめて補正 → 一覧確認 → 一括出力')
    st.caption('API不要です。自動処理するのは傾きと台形です。湾曲は「写真の補正（無料）」で個別に調整してください。')
    pages=project['pages']
    if not pages:st.info('「1　資料を追加」から写真・PDFを取り込んでください。');return
    state_key='batch_'+project['id']
    if state_key not in st.session_state:st.session_state[state_key]={}
    candidates=st.session_state[state_key]
    ids={p['id'] for p in pages}
    for pid in list(candidates):
        if pid not in ids:del candidates[pid]
    overwrite=st.checkbox('補正済み・画像確認済みのページも候補を作る',value=False)
    crop=st.checkbox('四隅を自動検出して台形を補正',value=True)
    skew=st.checkbox('小さな傾きを自動補正する',value=True)
    count=st.number_input('今回まとめて処理する枚数',1,150,min(20,len(pages)))
    if st.button('未処理ページの補正候補をまとめて作る',type='primary'):
        targets=[p for p in pages if p['id'] not in candidates and (overwrite or not(p.get('original_image') or p.get('photo_reviewed')))][:count]
        progress=st.progress(0);done=0
        for i,p in enumerate(targets):
            try:candidates[p['id']]=prepare_candidate(p,crop,skew);done+=1
            except Exception as exc:candidates[p['id']]={'error':str(exc)}
            progress.progress((i+1)/len(targets))
        st.success(f'{done}ページの候補を作成しました。まだ原本には反映していません。')
    st.caption('候補はこのセッション内のみ保持します。採用した結果は「途中保存」に含まれます。失敗したページはそのまま残り、他のページは続けて処理します。')
    # A stale candidate never silently replaces an individually edited page.
    valid={p['id']:candidates[p['id']] for p in pages if p['id'] in candidates and not candidates[p['id']].get('error') and candidates[p['id']]['signature']==signature(p)}
    review_token=hashlib.sha256(json.dumps([(pid,hashlib.sha256(c['image']).hexdigest()) for pid,c in sorted(valid.items())]).encode()).hexdigest()
    all_ok=st.checkbox('未採用候補をすべて確認し、文字・図が欠けていないことを確認した',key='batch_confirm_'+review_token)
    if st.button('確認した候補をまとめて採用',disabled=not(all_ok and valid)):
        for p in pages:
            if p['id'] in valid:adopt(p,valid[p['id']]);del candidates[p['id']]
        save();st.session_state.notice='確認した候補をまとめて採用しました。';st.rerun()
    def open_detail(page,candidate):
        st.session_state.work_menu='写真の補正（無料）'
        st.session_state.correction_page=page['id']
        settings=(candidate or {}).get('settings',page.get('correction',{}))
        prefix='correction_'+page['id']
        quad=settings.get('quad') or FULL_QUAD
        for j,point in enumerate(quad):
            for axis,val in zip(('x','y'),point):st.session_state[f'{prefix}_{j}_{axis}']=float(val)
        st.session_state[prefix+'_auto']=True
        st.session_state[prefix+'_angle']=float(settings.get('angle',0))
        st.session_state[prefix+'_turns']=int(settings.get('quarter_turns',0))
    st.markdown('#### 補正前後の一覧（5ページずつ）')
    group=st.selectbox('表示範囲',range((len(pages)+4)//5),format_func=lambda n:f'{n*5+1}〜{min((n+1)*5,len(pages))}ページ')
    for idx in range(group*5,min((group+1)*5,len(pages))):
        p=pages[idx];pid=p['id'];candidate=candidates.get(pid)
        st.markdown(f'**{idx+1:03d} ｜ {p["source"]} ｜ 原書 {p["label"]}**')
        left,right=st.columns(2)
        left.image(p.get('original_image',p['image']),caption='補正前',width=320)
        right.image(candidate['image'] if candidate and not candidate.get('error') else p['image'],caption='候補（未採用）' if candidate and not candidate.get('error') else '現在の画像',width=320)
        if candidate:
            if candidate.get('error'):st.error(candidate['error'])
            else:
                st.caption(candidate['note'])
                if pid not in valid:st.warning('画像が変更済みです。候補を破棄して再作成してください。')
            a,b=st.columns(2)
            if a.button('この候補を採用',key='adopt_'+pid,disabled=pid not in valid):
                adopt(p,candidate);del candidates[pid];save();st.rerun()
            if b.button('候補を破棄',key='discard_'+pid):del candidates[pid];st.rerun()
        else:
            st.caption('画像確認済み' if p.get('photo_reviewed') else '未確認')
            if st.button('現在の画像を確認済みにする',key='review_'+pid):p['photo_reviewed']=True;save();st.rerun()
        st.button('湾曲・四隅を個別に調整',key='detail_'+pid,on_click=open_detail,args=(p,candidate))
        a,b=st.columns(2)
        if a.button('↑ ページを前へ',key='up_'+pid,disabled=idx==0):pages[idx-1],pages[idx]=pages[idx],pages[idx-1];save();st.rerun()
        if b.button('↓ ページを後ろへ',key='down_'+pid,disabled=idx==len(pages)-1):pages[idx+1],pages[idx]=pages[idx],pages[idx+1];save();st.rerun()
        st.divider()
    st.markdown('#### ChatGPTへ渡すデータを出力')
    reviewed=st.checkbox('画像確認済みのページだけ出力',value=True)
    selected=[p for p in pages if not reviewed or p.get('photo_reviewed')]
    st.caption(f'対象：{len(selected)}ページ。未採用の候補は含めず、現在の採用済み画像を出力します。原本のまま使うページも「確認済み」にできます。')
    if st.button('PDF・プロンプト・画像ZIPを作成',disabled=not selected,type='primary'):
        with st.spinner('ファイルをまとめています…'):z,pdf=export_photos(selected)
        from handoff import handoff_files
        prompt,handoff=handoff_files(project,selected,pdf)
        st.session_state.photo_exports={'zip':z,'pdf':pdf,'prompt':prompt,'handoff':handoff,'revision':st.session_state.rev,'reviewed':reviewed,'project':project['id']}
    result=st.session_state.get('photo_exports')
    if result and result['revision']==st.session_state.rev and result['reviewed']==reviewed and result['project']==project['id'] and 'prompt' in result:
        st.success('PDFと依頼文ができました。2点をChatGPTへ一緒に添付し、「添付の依頼文に従って進めてください」と送信してください。続きの場合は前回の統合版PDF・辞書・作業記録も添付します。')
        st.download_button('PDF＋プロンプトの2点セット（ZIP）',result['handoff'],'ChatGPT_handoff.zip','application/zip',on_click='ignore')
        st.download_button('ChatGPTへの依頼文をダウンロード',result['prompt'],'ChatGPT_prompt.txt','text/plain',on_click='ignore')
        with st.expander('作成した依頼文を確認・コピー'):
            st.code(result['prompt'].decode('utf-8-sig'),language=None)
        st.caption('2点セットZIPは展開して、PDFとTXTの2ファイルを添付してください。ChatGPTへの送信は手動です。')
        st.download_button('画像を一括ダウンロード（ZIP）',result['zip'],'corrected_images.zip','application/zip',on_click='ignore')
        st.download_button('補正済みPDFをダウンロード',result['pdf'],'corrected_pages.pdf','application/pdf',on_click='ignore')
        st.caption('ChatGPTへ写真として渡す場合はZIPを展開し、page_0001.jpgから順に添付します。PDFは画像だけのPDFです。図や文字を読み取れない環境では画像を使用してください。')
    elif result:st.info('ページや出力設定が変わりました。一括出力を作り直してください。')
