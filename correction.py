"""Local deterministic page-photo correction. No network or generative image reconstruction."""
import io, math
import numpy as np
import cv2
from PIL import Image, ImageEnhance

FULL_QUAD=[[0.,0.],[100.,0.],[100.,100.],[0.,100.]]

def decode(data):
    with Image.open(io.BytesIO(data)) as im:
        if im.width*im.height>12_000_000: raise ValueError('補正対象の画像が大きすぎます。')
        return np.asarray(im.convert('RGB')).copy()

def encode(rgb):
    out=io.BytesIO();Image.fromarray(rgb).save(out,'JPEG',quality=95);return out.getvalue()

def order_quad(points):
    points=np.asarray(points,dtype=np.float32).reshape(4,2)
    # Clockwise around the center in image coordinates, starting from top-left.
    center=points.mean(axis=0)
    order=np.argsort(np.arctan2(points[:,1]-center[1],points[:,0]-center[0]))
    points=points[order]
    return np.roll(points,-int(np.argmin(points.sum(axis=1))),axis=0)

def detect_page(data):
    im=decode(data);h,w=im.shape[:2];scale=min(1.,1000/max(h,w))
    small=cv2.resize(im,None,fx=scale,fy=scale)
    gray=cv2.cvtColor(small,cv2.COLOR_RGB2GRAY)
    smooth=cv2.GaussianBlur(gray,(5,5),0)
    edges=cv2.Canny(smooth,40,130)
    edges=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    _,binary=cv2.threshold(smooth,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    candidates=[]
    for mask in (edges,binary):
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area=cv2.contourArea(c)/(small.shape[0]*small.shape[1])
            if not .25<area<.985: continue
            poly=cv2.approxPolyDP(c,.025*cv2.arcLength(c,True),True)
            if len(poly)==4 and cv2.isContourConvex(poly): candidates.append((area,poly))
    if not candidates:
        return FULL_QUAD, '四隅を確実に検出できませんでした。下の四隅を手動で調整してください。'
    _,poly=max(candidates,key=lambda c:c[0])
    q=order_quad(poly)/np.array([small.shape[1]-1,small.shape[0]-1])*100
    return np.clip(q,0,100).round(1).tolist(),'四隅の候補です。緑の枠がページの外周に合うか確認してください。'

def perspective(rgb,quad,preserve_frame=False):
    q=np.asarray(quad,dtype=np.float32)
    if q.shape!=(4,2) or not np.isfinite(q).all() or np.any(q<0) or np.any(q>100):
        raise ValueError('四隅は0〜100%で指定してください。')
    if not cv2.isContourConvex(q.reshape(-1,1,2)) or cv2.contourArea(q)<100:
        raise ValueError('四隅を左上→右上→右下→左下の順に指定し、枠が交差しないようにしてください。')
    a,b=q[1]-q[0],q[2]-q[1]
    if a[0]*b[1]-a[1]*b[0]<=0: raise ValueError('四隅の順番を確認してください。')
    h,w=rgb.shape[:2];src=q*np.array([w-1,h-1],dtype=np.float32)/100
    tw=max(np.linalg.norm(src[1]-src[0]),np.linalg.norm(src[2]-src[3]))
    th=max(np.linalg.norm(src[3]-src[0]),np.linalg.norm(src[2]-src[1]))
    if min(tw,th)<30 or max(tw,th)/min(tw,th)>10:raise ValueError('補正範囲が細すぎます。四隅を見直してください。')
    width,height=int(round(tw))+1,int(round(th))+1
    dst=np.float32([[0,0],[width-1,0],[width-1,height-1],[0,height-1]])
    matrix=cv2.getPerspectiveTransform(src.astype(np.float32),dst)
    if preserve_frame:
        corners=np.float32([[[0,0],[w-1,0],[w-1,h-1],[0,h-1]]])
        projected=cv2.perspectiveTransform(corners,matrix)[0]
        den=np.c_[corners[0],np.ones(4)]@matrix[2]
        if not np.isfinite(projected).all() or np.min(den)*np.max(den)<=0:
            raise ValueError('安全に全体を保持できない四隅です。切り取りなしで補正してください。')
        lo=np.floor(projected.min(axis=0))-8;hi=np.ceil(projected.max(axis=0))+8
        width,height=(hi-lo+1).astype(int)
        if width*height>12_000_000 or max(width,height)>6000:
            raise ValueError('変形が大きいため四隅の補正を見送りました。')
        matrix=np.array([[1,0,-lo[0]],[0,1,-lo[1]],[0,0,1]])@matrix
    return cv2.warpPerspective(rgb,matrix,(width,height),flags=cv2.INTER_CUBIC,borderValue=(255,255,255))

def estimate_curvature(rgb):
    """Conservative common quadratic text-line bend; reject sparse/mixed layouts."""
    h0,w0=rgb.shape[:2];scale=min(1.,1400/max(h0,w0))
    gray=cv2.cvtColor(cv2.resize(rgb,None,fx=scale,fy=scale),cv2.COLOR_RGB2GRAY)
    h,w=gray.shape
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,12)
    joined=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((1,max(9,int(w*.035))),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(joined)
    fits=[]
    for i in range(1,n):
        x,y,bw,bh,area=stats[i]
        if bw<w*.5 or bh>h*.10 or bh<4 or y<h*.04 or y+bh>h*.96:continue
        ys,xs=np.nonzero((labels[y:y+bh,x:x+bw]==i)&(ink[y:y+bh,x:x+bw]>0))
        if len(xs)<100:continue
        samples=[]
        for start in np.linspace(x,x+bw,25)[:-1]:
            take=(xs+x>=start)&(xs+x<start+bw/24)
            if take.sum()>5:samples.append(((start+bw/48)/w-.5,float(np.median(ys[take]+y))))
        if len(samples)<18:continue
        xx,yy=np.asarray(samples).T
        coeff=np.polyfit(xx,yy,2);res=np.median(np.abs(np.polyval(coeff,xx)-yy))
        # Straight rules and illustrations are not sufficient text evidence.
        cc=cv2.connectedComponentsWithStats(ink[y:y+bh,x:x+bw])[2][1:]
        chars=sum(2<=a[2]<=w*.04 and 3<=a[3]<=h*.04 for a in cc)
        if chars<15 or res>max(1.5,bh*.18):continue
        fits.append((coeff[0],float(np.median(yy))))
    if len(fits)<5:return None,'湾曲：本文の行を十分に検出できず、自動補正を見送りました。'
    values,rows=np.asarray(fits).T
    a=float(np.median(values));mad=float(np.median(np.abs(values-a)))
    if np.ptp(rows)<h*.30 or mad>max(3,abs(a)*.30) or abs(a)*.25<2 or abs(a)*.25>h*.035:
        return None,'湾曲：行の曲がりが不明確／不均一なため、自動補正を見送りました。'
    offsets=a*((np.linspace(0,1,5)-.5)**2-.125)/h*100
    grid=np.array([20.,50.,80.])[:,None]+offsets[None,:]
    return grid.tolist(),f'湾曲：{len(fits)}本の行から緩やかな曲がりを補正しました。仕上がりを確認してください。'

def brighten_paper(rgb):
    # Gentle global exposure lift; preserve colour and avoid aggressive whitening.
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    white=float(np.percentile(gray,85))
    gain=min(1.30,max(1.,235/max(white,1)))
    return np.clip(rgb.astype(np.float32)*gain,0,255).astype(np.uint8)

def detect_skew(rgb):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    scale=min(1.,1200/max(gray.shape));gray=cv2.resize(gray,None,fx=scale,fy=scale)
    edges=cv2.Canny(gray,60,160)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,40,minLineLength=max(30,int(gray.shape[1]*.12)),maxLineGap=12)
    angles=[]
    if lines is not None:
        for x0,y0,x1,y1 in np.asarray(lines).reshape(-1,4):
            angle=math.degrees(math.atan2(y1-y0,x1-x0))
            while angle>90:angle-=180
            while angle<-90:angle+=180
            if abs(angle)<15:angles.append(angle)
    return float(np.median(angles)) if len(angles)>=3 else 0.

def unbend(rgb,top=0.,bottom=0.):
    """Manual vertical remap between parabolic upper/lower baselines, not full 3D dewarping."""
    if not(-20<=top<=20 and -20<=bottom<=20):raise ValueError('湾曲は-20〜20%で調整してください。')
    if not top and not bottom:return rgb
    h,w=rgb.shape[:2]
    u=np.linspace(0,1,w,dtype=np.float32);v=np.linspace(0,1,h,dtype=np.float32)[:,None]
    curve=4*u*(1-u)
    mx=np.broadcast_to(np.arange(w,dtype=np.float32),(h,w)).copy()
    my=v*(h-1)+((1-v)*top+v*bottom)/100*(h-1)*curve[None,:]
    return cv2.remap(rgb,mx,my.astype(np.float32),cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))

def correct(data,quad=None,auto_skew=True,angle=0.,quarter_turns=0,top=0.,bottom=0.,brightness=1.,contrast=1.,mesh_lines=None,preserve_frame=False,auto_curve=False,auto_light=False):
    rgb=decode(data)
    if quad is not None: rgb=perspective(rgb,quad,preserve_frame=preserve_frame)
    detected=detect_skew(rgb) if auto_skew else 0.
    im=Image.fromarray(rgb)
    total=detected+float(angle)+90*int(quarter_turns)
    if total:im=im.rotate(total,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white')
    curve_note='';rgb=np.asarray(im)
    if auto_curve and mesh_lines is None:mesh_lines,curve_note=estimate_curvature(rgb)
    rgb=mesh_unbend(rgb,mesh_lines) if mesh_lines is not None else unbend(rgb,top,bottom)
    if auto_light:rgb=brighten_paper(rgb)
    im=Image.fromarray(rgb)
    im=ImageEnhance.Brightness(im).enhance(brightness)
    im=ImageEnhance.Contrast(im).enhance(contrast)
    im.thumbnail((3200,3200))
    return encode(np.asarray(im)),{'detected_angle':round(detected,2),'angle':angle,'quarter_turns':quarter_turns,'top':top,'bottom':bottom,'brightness':brightness,'contrast':contrast,'quad':quad,'mesh_lines':mesh_lines,'preserve_frame':preserve_frame,'auto_curve':auto_curve,'auto_light':auto_light,'curve_note':curve_note}

def overlay(data,quad):
    rgb=decode(data);h,w=rgb.shape[:2]
    pts=np.asarray(quad)*[w-1,h-1]/100;pts=pts.astype(np.int32)
    cv2.polylines(rgb,[pts],True,(24,160,100),max(2,w//300))
    for n,(x,y) in enumerate(pts):
        cv2.circle(rgb,(x,y),max(7,w//70),(210,65,40),-1)
        cv2.putText(rgb,str(n+1),(min(w-35,max(5,x+10)),min(h-10,max(30,y+30))),cv2.FONT_HERSHEY_SIMPLEX,max(.65,w/800),(210,65,40),2)
    return rgb

def apply_correction(page,image,settings):
    page.setdefault('original_image',page['image'])
    page['image']=image;page['correction']=settings;page['photo_reviewed']=True
    page['figures']=[]
    # Old figure boxes/history refer to different coordinates and must not be restored onto the new image.
    page['history']=[];page['error']=''
    page['status']='要確認' if page['translation'] else '未翻訳'

def restore_original(page):
    if 'original_image' not in page:return
    page['image']=page.pop('original_image');page.pop('correction',None);page['photo_reviewed']=False
    page['figures']=[];page['history']=[];page['error']=''
    page['status']='要確認' if page['translation'] else '未翻訳'

def mesh_unbend(rgb,lines):
    """Map three manually traced text baselines to straight lines; preserve full image edges.
    Each baseline has five source y percentages at x=0,25,50,75,100%.
    Monotonic vertical maps prevent folds and keep all source rows in the result.
    """
    grid=np.asarray(lines,dtype=np.float32)
    if grid.shape!=(3,5) or not np.isfinite(grid).all():raise ValueError('湾曲の基準線は3行×5点で指定してください。')
    full=np.vstack([np.zeros(5),grid,np.full(5,100)])
    if np.any(np.diff(full,axis=0)<3):raise ValueError('基準線は上から順に並べ、各列で3%以上の間隔を空けてください。')
    h,w=rgb.shape[:2];u=np.linspace(0,1,w);knots=np.linspace(0,1,5)
    # Smooth shape-preserving interpolation avoids abrupt changes at each control point.
    from scipy.interpolate import PchipInterpolator
    curves=PchipInterpolator(knots,full,axis=1)(u)
    if np.any(np.diff(curves,axis=0)<=0):raise ValueError('基準線が交差します。点の位置を調整してください。')
    target=np.mean(full,axis=1)/100*(h-1)
    mx=np.broadcast_to(np.arange(w,dtype=np.float32),(h,w)).copy()
    my=np.empty((h,w),np.float32);rows=np.arange(h)
    for x in range(w):my[:,x]=np.interp(rows,target,curves[:,x]/100*(h-1))
    return cv2.remap(rgb,mx,my,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)

def mesh_overlay(data,lines):
    from scipy.interpolate import PchipInterpolator
    rgb=decode(data);h,w=rgb.shape[:2];u=np.linspace(0,1,w)
    grid=np.asarray(lines,dtype=float)
    for i,line in enumerate(grid):
        curve=PchipInterpolator(np.linspace(0,1,5),line)(u)
        pts=np.stack([np.arange(w),curve/100*(h-1)],axis=1).astype(np.int32)
        color=[(215,60,30),(25,150,80),(35,85,215)][i]
        cv2.polylines(rgb,[pts],False,color,max(2,w//350))
        for x,y in zip(np.linspace(0,w-1,5),line/100*(h-1)):
            cv2.circle(rgb,(int(x),int(y)),max(5,w//100),color,-1)
    return rgb
