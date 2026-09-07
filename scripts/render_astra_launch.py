#!/usr/bin/env python3
"""Render cinematic, clearly labeled Codex desktop and CLI demo recreations.

Optional production dependencies: Pillow, NumPy and ffmpeg. No screenshots,
private app state, stock footage, or third-party music are used.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import math
from pathlib import Path
import subprocess
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BG=(8,9,14); WHITE='#F7F7FA'; GRAY='#A1A1AA'; PURPLE='#BCA4FF'; CYAN='#79E4DF'; GREEN='#88D7A4'
# Five editorial scenes: opening, three sustained use cases, closing.
SCENES=[(0,5,'LaneOrchestrator. Your task. The right team.','intro'),(5,28,'Complexity calls for Astra.','astra'),(28,51,'Astra leads. Sol implements.','sol'),(51,73,'Astra leads. Terra agents build.','terra'),(73,78,'LaneOrchestrator. Built around your task.','end')]
TOUR=[(0,7,'Complexity calls for Astra.','astra'),(7,14,'Astra leads. Sol implements.','sol'),(14,20,'Astra leads. Terra agents build.','terra')]

def clamp(v):return max(0.,min(1.,v))
def ease(v):return 1-(1-clamp(v))**3

@lru_cache(maxsize=128)
def font(size,bold=False,mono=False):
    if mono:
        paths=['/System/Library/Fonts/Menlo.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
    else:
        paths=['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for p in paths:
        if Path(p).exists():return ImageFont.truetype(p,int(size))
    raise RuntimeError('Install a supported production font')

def text(d,xy,value,size=26,color=WHITE,bold=False,mono=False):
    d.text(xy,value,font=font(size,bold,mono),fill=color)

def lines(d,value,x,y,width,size=26,color=WHITE,bold=False,spacing=1.4):
    face=font(size,bold); current=''
    for word in value.split():
        candidate=(current+' '+word).strip()
        if current and d.textlength(candidate,font=face)>width:
            text(d,(x,y),current,size,color,bold);y+=size*spacing;current=word
        else:current=candidate
    text(d,(x,y),current,size,color,bold)
    return y+size*spacing

def center(d,value,y,width,size,color=WHITE,bold=True):
    text(d,((width-d.textlength(value,font=font(size,bold)))/2,y),value,size,color,bold)

def pill(d,x,y,label,color=PURPLE,size=20):
    w=d.textlength(label,font=font(size))+32
    d.rounded_rectangle((x,y,x+w,y+size+22),radius=(size+22)//2,fill='#282332',outline='#453B59')
    text(d,(x+16,y+8),label,size,color)
    return w

def check(d,x,y,r=10):
    d.ellipse((x-r,y-r,x+r,y+r),fill=GREEN)
    d.line([(x-r*.45,y),(x-r*.1,y+r*.3),(x+r*.5,y-r*.4)],fill='#123021',width=2)

@lru_cache(maxsize=4)
def background(w,h):
    yy,xx=np.mgrid[0:h,0:w]
    field=np.exp(-((xx-w*.68)**2/(w*.43)**2+(yy-h*.52)**2/(h*.61)**2))
    arr=np.zeros((h,w,3),dtype=np.uint8)
    for c,v in enumerate((23,10,47)):arr[:,:,c]=np.clip(BG[c]+field*v,0,255)
    return Image.fromarray(arr)

CASES={
    'astra': {
        'number':'01', 'title':'Recover a broken event stream',
        'prompt':'Fix stream recovery after reconnects. Prevent duplicate events and checkpoint gaps.',
        'context':'Replay order, deduplication and checkpoint writes interact. A local retry patch is insufficient.',
        'model':'Astra', 'effort':'Xhigh', 'role':'Distributed-systems implementation',
        'reason':'Coupled state transitions. Deep reasoning across failure paths.',
        'file':'stream/recovery.py',
        'code':['  with checkpoint.transaction() as tx:', '+     for event in replay_from(tx.cursor):', '+         if tx.claim_once(event.id):', '+             apply(event, transaction=tx)', '+         tx.advance(event.sequence)', '  # Commit effects and cursor together.'],
        'checks':['Reconnect replay preserves event order', 'Duplicate delivery applies each event once', 'Crash recovery preserves the checkpoint'],
        'review':'Fresh Astra / high reviewer',
        'result':'Recovery paths checked. Ready for handoff.',
    },
    'sol': {
        'number':'02', 'title':'Ship notification preferences',
        'prompt':'Add notification preferences to settings. Save per user and restore them after reload.',
        'context':'Existing settings API and form components. The work spans UI state, persistence and defaults.',
        'model':'Sol', 'effort':'High', 'role':'Full-stack specialist',
        'reason':'Known architecture. Careful integration across three layers.',
        'file':'settings/notification-preferences.tsx',
        'code':['  const form = usePreferenceForm(initial);', '+ await settings.update({', '+   notifications: form.values,', '+ });', '+ cache.set(user.id, form.values);', '  // Existing settings contract retained.'],
        'checks':['Saved preferences survive a reload', 'Defaults work for existing users', 'Failed saves preserve the edited form'],
        'review':'Astra / high independent review',
        'result':'Settings UI, persistence and regression checks aligned.',
    },
}

def rule(d,x,y,w,color='#34373D'):
    d.line((x,y,x+w,y),fill=color,width=1)

def label(d,x,y,value,color=GRAY):text(d,(x,y),value,17,color,True)

def panel(d,box,fill='#202328',outline='#383B42',radius=16):
    d.rounded_rectangle(box,radius,fill=fill,outline=outline,width=1)

def desktop_case(kind,u):
    c=CASES[kind]; w,h=1720,738
    im=Image.new('RGB',(w,h),'#1B1D21');d=ImageDraw.Draw(im)
    stage=min(3,int(u*4)); phase=u*4-stage
    # Stable application frame; activity evolves inside it rather than cutting away.
    d.rectangle((0,0,190,h),fill='#15171A')
    text(d,(25,26),'Codex',27,WHITE,True)
    text(d,(25,92),'+  New task',19,GRAY)
    label(d,25,164,'PROJECTS')
    text(d,(25,208),'Product workspace',17,GRAY)
    panel(d,(12,252,177,300),'#2C3037','#363B44',8)
    text(d,(25,267),'Current task',18,WHITE)
    text(d,(25,330),'Recent tasks',17,GRAY)
    text(d,(25,h-48),'Local workspace',15,GRAY)
    x=224
    text(d,(x,24),c['title'],25,WHITE,True)
    label(d,1372,31,'ASTRA  /  COORDINATOR',PURPLE)
    rule(d,190,75,1530)
    label(d,x,103,'YOU')
    panel(d,(x,137,1680,226),'#292D33','#3B414A',12)
    text(d,(x+20,151),'$laneorchestrator',20,CYAN,True)
    # Prompt is complete and readable before any model is selected.
    text(d,(x+20,184),c['prompt'],23,WHITE)
    label(d,x,259,'ASTRA  /  TASK ASSESSMENT',PURPLE)
    lines(d,c['context'],x,299,615,25,WHITE,spacing=1.42)
    steps=['Inspect task and repository','Choose model and thinking','Implement and check behavior','Independent review']
    for i,name in enumerate(steps):
        yy=416+i*54
        d.ellipse((x,yy+3,x+24,yy+27),fill=('#BBADFF' if i==stage else '#466C59' if i<stage else '#343941'))
        text(d,(x+7,yy+5),str(i+1),13,'#15171A' if i<=stage else GRAY,True)
        text(d,(x+42,yy),name,23,WHITE if i<=stage else '#727983',i==stage)
    label(d,x,690,'AUTOMATIC SELECTION  ·  NO MODEL IN THE PROMPT',CYAN)
    rx=904; rw=776
    panel(d,(rx,258,rx+rw,704),'#22262C','#424852',14)
    if stage==0:
        label(d,rx+28,287,'INSPECTING THE REPOSITORY')
        files=(['stream/recovery.py','storage/checkpoint.py','tests/test_reconnect.py'] if kind=='astra' else ['settings/page.tsx','api/user_settings.py','tests/settings.spec.ts'])
        for i,f in enumerate(files):
            yy=355+i*75
            if phase < i*.12: continue
            text(d,(rx+28,yy),f,24,WHITE,mono=True)
            rule(d,rx+28,yy+51,rw-56)
        lines(d,'Selection follows the inspected scope and verification needs.',rx+28,603,rw-60,23,GRAY)
    elif stage==1:
        label(d,rx+28,287,'SELECTED FOR IMPLEMENTATION',CYAN)
        text(d,(rx+28,331),c['model'],72,WHITE,True)
        pill(d,rx+330,350,c['effort']+' thinking',PURPLE,23)
        text(d,(rx+28,437),c['role'],26,WHITE)
        rule(d,rx+28,493,rw-56)
        label(d,rx+28,521,'WHY THIS CHOICE')
        lines(d,c['reason'],rx+28,560,rw-60,27,WHITE)
    elif stage==2:
        label(d,rx+28,287,c['model'].upper()+' / '+c['effort'].upper()+'  ·  IMPLEMENTING',CYAN)
        text(d,(rx+28,343),c['file'],20,GRAY,mono=True)
        for i,row in enumerate(c['code']):
            if phase < i*.08: continue
            text(d,(rx+28,396+i*38),row,21,GREEN if row.startswith('+') else GRAY,mono=True)
        text(d,(rx+28,660),'Focused checks follow the changed behavior.',21,GRAY)
    else:
        label(d,rx+28,287,c['review'].upper(),PURPLE)
        text(d,(rx+28,338),'Diff + original acceptance criteria',26,WHITE,True)
        for i,row in enumerate(c['checks']):
            yy=407+i*62
            if phase < i*.14: continue
            check(d,rx+40,yy+15)
            text(d,(rx+66,yy),row,22,WHITE)
        rule(d,rx+28,612,rw-56)
        lines(d,c['result'],rx+28,639,rw-56,22,GREEN)
    if stage and phase < .12:
        im=Image.blend(desktop_case(kind,stage/4-.00001),im,ease(phase/.12))
    return im

def cli_case(u):
    w,h=1720,738;im=Image.new('RGB',(w,h),'#13171C');d=ImageDraw.Draw(im)
    for i,c in enumerate(('#EF7770','#E6BC69','#79BC8D')):d.ellipse((24+i*24,24,37+i*24,37),fill=c)
    text(d,(143,21),'Codex CLI  /  project-api',22,GRAY)
    label(d,1390,27,'ASTRA  /  COORDINATOR',PURPLE)
    rule(d,0,72,w)
    text(d,(38,99),'› $laneorchestrator',24,CYAN,mono=True)
    text(d,(38,142),'Add project pagination and update the typed client.',28,WHITE,mono=True)
    text(d,(38,186),'Reuse our existing cursor format and page schema.',24,GRAY,mono=True)
    rule(d,38,248,w-76)
    stage=min(3,int(u*4)); phase=u*4-stage
    label(d,38,276,'ASTRA / HIGH  ·  INSPECT → SPLIT → VERIFY',PURPLE)
    if stage==0:
        rows=['Reading routes/projects.py and shared/cursors.py', 'Reading sdk/projects.ts and Page<T>', 'Established cursor contract found.', 'Two file owners. One shared response schema.']
        for i,row in enumerate(rows):
            if phase >= i*.13:text(d,(38,344+i*67),row,25,WHITE if i>1 else GRAY,mono=True)
        text(d,(38,667),'Model and thinking selected after inspecting the scope.',23,CYAN)
        return im
    # Two bounded specialists with disjoint file ownership.
    agents=[('BACKEND SPECIALIST','Terra / medium','routes/projects.py','Reuse the existing cursor helper.'),('TYPESCRIPT SPECIALIST','Terra / high','sdk/projects.ts','Bounded typed-client change.')]
    for i,(role,model,path,reason) in enumerate(agents):
        x=38+i*835;panel(d,(x,331,x+805,573),'#1D242C','#3B4855',12)
        label(d,x+24,353,role,CYAN)
        text(d,(x+24,395),model,36,WHITE,True)
        text(d,(x+24,455),path,22,GRAY,mono=True)
        text(d,(x+24,513),reason,24,WHITE)
    if stage==1:
        text(d,(38,614),'Astra: known patterns; separate ownership; explicit contracts.',25,WHITE,mono=True)
        text(d,(38,668),'Dispatching both specialists with bounded task packets…',23,CYAN,mono=True)
    elif stage==2:
        text(d,(38,614),'[backend]  cursor validation + next_cursor response',24,GREEN,mono=True)
        text(d,(38,668),'[client]   typed page result + next-page traversal',24,GREEN,mono=True)
    else:
        text(d,(38,614),'Astra / high review: API and client agree on the contract.',24,PURPLE,mono=True)
        text(d,(38,668),'Checks: empty page  ·  invalid cursor  ·  last page',24,GREEN,mono=True)
    if stage and phase < .12:
        im=Image.blend(cli_case(stage/4-.00001),im,ease(phase/.12))
    return im

@lru_cache(maxsize=1)
def film_background():
    w,h=1920,1080;yy,xx=np.mgrid[:h,:w]
    glow=np.exp(-((xx-1330)**2/850**2+(yy-240)**2/590**2))
    a=np.zeros((h,w,3),dtype=np.uint8)
    for c,(base,amount) in enumerate([(11,9),(14,12),(19,20)]):a[:,:,c]=base+glow*amount
    return Image.fromarray(a)

def frame(t,scenes=SCENES,vertical=False):
    if vertical:raise ValueError('This production is one landscape film.')
    w,h=1920,1080;im=film_background().copy();d=ImageDraw.Draw(im)
    start,end,caption,kind=next(s for s in scenes if s[0]<=t<s[1]);u=(t-start)/(end-start)
    label(d,96,47,'LANEORCHESTRATOR',WHITE)
    text(d,(1544,47),'DEMO RE-CREATION',16,GRAY)
    if kind in ('intro','end'):
        # Restrained custom lane motif; no rotating stock-style orb.
        for i in range(3):
            y=370+i*125
            d.line((1100,y,1770,y),fill='#313A48',width=2)
            px=1100+670*ease((u-i*.10)/.75)
            d.line((1100,y,px,y),fill=PURPLE if i==0 else CYAN if i==1 else '#F1CF99',width=3)
            d.ellipse((px-7,y-7,px+7,y+7),fill=WHITE)
        text(d,(96,278),'LaneOrchestrator',98,WHITE,True)
        text(d,(102,430),'Your task.',66,WHITE)
        text(d,(102,519),'The right team.',66,PURPLE)
        if kind=='intro':
            text(d,(102,710),'Astra chooses the specialist, model and thinking.',29,GRAY)
            label(d,102,790,'THREE TASKS. THREE WAYS TO GET IT DONE.',CYAN)
        else:
            text(d,(102,710),'One Codex skill. 172 specialists. Automatic selection.',29,GRAY)
            text(d,(102,801),'github.com/KarthikRamesh9149/laneorchestrator',29,CYAN)
    else:
        num={'astra':'01','sol':'02','terra':'03'}[kind]
        label(d,98,118,num+' / '+('CODEX CLI' if kind=='terra' else 'CODEX DESKTOP'),CYAN)
        text(d,(94,157),caption,57,WHITE,True)
        app=cli_case(u) if kind=='terra' else desktop_case(kind,u)
        # Subtle arrival only. Text remains stationary for comfortable reading.
        y=273+int(14*(1-ease(u/.08)));x=100
        shadow=Image.new('RGB',(1720,738),'#090C10')
        im.paste(shadow,(x,y+14))
        mask=Image.new('L',app.size,0);ImageDraw.Draw(mask).rounded_rectangle((0,0,1719,737),18,fill=255)
        im.paste(app,(x,y),mask);d=ImageDraw.Draw(im)
        d.rounded_rectangle((x,y,x+1719,y+737),18,outline='#444C58',width=1)
    d=ImageDraw.Draw(im)
    # Three quiet navigation markers emphasize the smaller chapter count.
    for i,k in enumerate(['astra','sol','terra']):
        xx=1644+i*62;d.line((xx,1044,xx+42,1044),fill=PURPLE if kind==k else '#3C4551',width=3)
    fade=min(ease((t-start)/.22),ease((end-t)/.18))
    if fade<1:im=Image.blend(film_background(),im,fade)
    return im

def music(path,seconds):
    rate=48000;n=int(seconds*rate);t=np.arange(n)/rate;rng=np.random.default_rng(172)
    left=np.zeros(n);right=np.zeros(n)
    roots=[73.416,58.2705,65.4065,65.4065]
    def add(start,sound,pan=0):
        a=int(start*rate);b=min(n,a+len(sound))
        if b<=a:return
        left[a:b]+=sound[:b-a]*(1-pan*.35);right[a:b]+=sound[:b-a]*(1+pan*.35)
    for beat in np.arange(0,seconds,.5):
        u=np.arange(int(.32*rate))/rate
        kick=.32*np.sin(2*np.pi*(48*u+2.5*(1-np.exp(-u*22))))*np.exp(-u*18)
        add(beat,kick)
        if int(beat*2)%2:
            noise=rng.standard_normal(len(u))
            add(beat,.065*noise*np.exp(-u*25)+.075*np.sin(2*np.pi*180*u)*np.exp(-u*30))
    for beat in np.arange(0,seconds,.25):
        u=np.arange(int(.08*rate))/rate;noise=rng.standard_normal(len(u));noise=np.concatenate(([0],np.diff(noise)))
        add(beat,.018*noise*np.exp(-u*65),.6 if int(beat*4)%2 else -.6)
        root=roots[int(beat//4)%4];notes=[2,2.5,3,4];f=root*notes[int(beat*4)%4]
        u=np.arange(int(.45*rate))/rate
        tone=(np.sin(2*np.pi*f*u)+.22*np.sin(2*np.pi*f*2*u))*.042*np.exp(-u*8)*(1-np.exp(-u*100))
        add(beat,tone,math.sin(beat)*.8)
    for start in np.arange(0,seconds,4):
        u=np.arange(int(4*rate))/rate;root=roots[int(start//4)%4]
        env=np.minimum(u/.25,1)*np.minimum((4-u)/.5,1)
        pad=sum(np.sin(2*np.pi*root*mult*u) for mult in [2,2.4,3])*.023*env
        add(start,pad)
    for start in [0,5,28,51,73]:
        if start>=seconds:continue
        u=np.arange(int(.8*rate))/rate
        add(start,.15*np.sin(2*np.pi*38*u)*np.exp(-u*7))
        add(max(0,start-.28),rng.standard_normal(int(.28*rate))*.02*np.linspace(0,1,int(.28*rate)))
    stereo=np.stack((left,right),axis=1);envelope=np.minimum(t/.15,1)*np.minimum((seconds-t)/1.4,1)
    stereo=np.tanh(stereo*1.5)*envelope[:,None]
    stereo*=.78/max(.78,float(np.max(np.abs(stereo))))
    with wave.open(str(path),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(rate);out.writeframes((stereo*32767).astype('<i2').tobytes())

def timestamp(t):return f'00:{int(t)//60:02d}:{int(t)%60:02d},000'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ffmpeg',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--format',choices=['launch','tour'],default='launch');p.add_argument('--preview',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);scenes={'launch':SCENES,'tour':TOUR}[a.format];vertical=a.format=='social';seconds=scenes[-1][1];name='laneorchestrator-astra-'+a.format
    if a.preview:
        for i,s in enumerate(scenes):frame(s[0]+(s[1]-s[0])*.72,scenes,vertical).save(a.output/(name+f'-{i+1:02d}.png'))
        return
    wav=a.output/(name+'.wav');music(wav,seconds)
    width,height=(1080,1920) if vertical else (1200,676) if a.format=='tour' else (1920,1080)
    source='1080x1920' if vertical else '1920x1080'
    command=[a.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',source,'-r','30','-i','-','-i',str(wav),'-vf',f'scale={width}:{height}:flags=lanczos','-c:v','libx264','-preset','fast','-crf','22' if a.format!='tour' else '30','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k' if a.format!='tour' else '80k','-movflags','+faststart','-shortest',str(a.output/(name+'.mp4'))]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    try:
        for i in range(seconds*30):process.stdin.write(frame(i/30,scenes,vertical).tobytes())
    finally:process.stdin.close()
    if process.wait():raise RuntimeError('ffmpeg failed')
    a.output.joinpath(name+'.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(s[0])} --> {timestamp(s[1])}\n{s[2]}' for i,s in enumerate(scenes))+'\n')
    print(a.output/(name+'.mp4'))

if __name__=='__main__':main()
