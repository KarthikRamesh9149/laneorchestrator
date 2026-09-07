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
SCENES=[(0,3,'One prompt.','intro'),(3,8,'Astra takes the lead.','reveal'),(8,14,'Start with the task.','prompt'),(14,20,'Astra reads the context.','assess'),(20,26,'Expertise. Model. Thinking.','select'),(26,33,'The specialist gets to work.','implement'),(33,39,'Verify the result.','verify'),(39,45,'Change the task. Change the model.','models'),(45,56,'The same skill. In your terminal.','cli'),(56,60,'172 specialists. Your choice of model.','network'),(60,65,'LaneOrchestrator. Led by Astra.','end')]
SOCIAL=[(0,3,'Astra takes the lead.','reveal'),(3,8,'Start with the task.','prompt'),(8,14,'Expertise. Model. Thinking.','select'),(14,19,'Verify the result.','verify'),(19,25,'The same skill. In your terminal.','cli'),(25,30,'LaneOrchestrator. Led by Astra.','end')]
TOUR=[(0,4,'Start with the task.','prompt'),(4,8,'Astra reads the context.','assess'),(8,12,'Expertise. Model. Thinking.','select'),(12,16,'Verify the result.','verify'),(16,20,'The same skill. In your terminal.','cli')]

def clamp(v):return max(0.,min(1.,v))
def ease(v):return 1-(1-clamp(v))**3

@lru_cache(maxsize=128)
def font(size,bold=False,mono=False):
    if mono:
        paths=['/System/Library/Fonts/Menlo.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
    else:
        paths=['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/SFNS.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
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

def desktop(stage,u,w,h):
    mobile=w<1200
    im=Image.new('RGB',(w,h),'#202022');d=ImageDraw.Draw(im)
    side=0 if mobile else 220
    if side:
        d.rectangle((0,0,side,h),fill='#171718')
        text(d,(25,30),'Codex',29,WHITE,True)
        d.rounded_rectangle((15,88,205,132),12,fill='#2A2A2D')
        text(d,(29,101),'+  New task',19)
        text(d,(27,178),'PROJECTS',13,GRAY,True)
        text(d,(28,214),'▸  demo-reports',18)
        d.rounded_rectangle((15,254,205,301),11,fill='#303034')
        d.ellipse((29,273,36,280),fill=CYAN)
        text(d,(47,267),'CSV export',18)
        text(d,(28,328),'README polish',17,GRAY)
        text(d,(28,378),'Streaming retries',17,GRAY)
        text(d,(27,h-56),'Local project',15,GRAY)
    x=side+42; cw=w-x-42
    text(d,(x,30),'Report CSV export',23,WHITE,True)
    pill(d,w-214,23,'Astra  ·  High',PURPLE,18)
    d.line((side,77,w,77),fill='#333336')
    text(d,(x,108),'CODEX  /  LANEORCHESTRATOR',14,GRAY,True)
    prompt='Add status filtering to CSV exports. Preserve commas, quotes and multiline text.'
    bx=x+60 if not mobile else x;bw=cw-60 if not mobile else cw
    d.rounded_rectangle((bx,150,bx+bw,274),18,fill='#303033')
    text(d,(bx+24,171),'$laneorchestrator',25,CYAN,True)
    visible=prompt[:max(1,int(clamp(u/.53)*len(prompt)))] if stage=='prompt' else prompt
    lines(d,visible,bx+24,212,bw-45,22,WHITE,spacing=1.25)
    # Bottom composer stays in frame, making the desktop context clear.
    d.rounded_rectangle((x,h-95,w-35,h-27),18,fill='#2A2A2D',outline='#3B3B40')
    text(d,(x+22,h-74),'Ask a follow-up',19,GRAY)
    d.ellipse((w-88,h-77,w-52,h-41),fill='#414146')
    d.line((w-70,h-49,w-70,h-69),fill='#B7B7C0',width=2)
    d.line([(w-78,h-61),(w-70,h-69),(w-62,h-61)],fill='#B7B7C0',width=2)
    if stage=='prompt':
        if u>.58:
            text(d,(x,320),'Astra',22,WHITE,True)
            lines(d,'I’ll inspect the export path, then choose the specialist, model and thinking for this task.',x,363,cw,24,GRAY)
        return im
    text(d,(x,310),'Astra',22,WHITE,True)
    if stage=='assess':
        text(d,(x,354),'Inspecting the implementation',25,WHITE,True)
        rows=['reports.py  ·  request filtering','csv_export.py  ·  output formatting','test_export.py  ·  existing checks']
        for i,row in enumerate(rows):
            y=414+i*52
            if u>i*.15:check(d,x+10,y+12);text(d,(x+34,y),row,22,GRAY)
        d.rounded_rectangle((x,599,x+cw,664),12,fill='#28252F')
        text(d,(x+19,618),'Known scope  /  routine implementation',22,PURPLE)
    elif stage=='select':
        text(d,(x,351),'Selected for this task',25,WHITE,True)
        y=407
        d.rounded_rectangle((x,y,x+cw,y+211),18,fill='#29262F',outline='#5E5078',width=2)
        text(d,(x+25,y+22),'Python specialist',27,WHITE,True)
        text(d,(x+25,y+77),'TERRA',55,WHITE,True)
        pill(d,x+260,y+87,'Medium thinking',CYAN,23)
        text(d,(x+25,y+163),'Two files. Existing pattern. Focused verification.',20,GRAY)
        text(d,(x,651),'Astra chooses both model and thinking.',23,PURPLE)
    elif stage=='implement':
        text(d,(x,353),'Python specialist  ·  Terra / medium',24,CYAN,True)
        y=408
        d.rounded_rectangle((x,y,x+cw,y+238),14,fill='#171C1A',outline='#364A3E')
        text(d,(x+22,y+17),'csv_export.py',19,GRAY,mono=True)
        code=['+ import csv, io','+ writer = csv.DictWriter(buffer, fieldnames=columns)','+ writer.writeheader()','+ writer.writerows(rows)']
        for i,row in enumerate(code):
            if u>i*.12:text(d,(x+22,y+63+i*35),row,18 if mobile else 21,GREEN,mono=True)
        text(d,(x,678),'Updated 2 files  ·  running focused checks…',21,GRAY)
    elif stage=='verify':
        text(d,(x,353),'Verification',27,WHITE,True)
        items=['Status filtering','Commas, quotes and multiline values','Headers, row order and input preservation']
        for i,row in enumerate(items):
            if u>i*.13:check(d,x+11,423+i*55);text(d,(x+37,410+i*55),row,22,WHITE)
        if u>.43:
            d.rounded_rectangle((x,592,x+cw,685),14,fill='#1D2C24',outline='#35533E')
            text(d,(x+21,608),'Independent review  ·  Sol / high',25,GREEN,True)
            text(d,(x+21,651),'Approve  ·  changed behavior and checks reviewed.',20,GRAY)
    elif stage=='models':
        text(d,(x,352),'Match the settings to the work.',25,WHITE,True)
        items=[('README typo','Luna','High'),('Integration change','Sol','High'),('Demanding implementation','Astra','Chosen thinking')]
        for i,(task,model,effort) in enumerate(items):
            y=410+i*85;active=min(2,int(u*3))==i
            d.rounded_rectangle((x,y,x+cw,y+72),12,fill='#342B45' if active else '#28282B',outline='#9F83D5' if active else '#36363B')
            text(d,(x+17,y+11),task,20,GRAY)
            text(d,(x+17,y+38),model+'  /  '+effort,23,PURPLE if active else WHITE,True)
    return im

def terminal(u,w,h):
    im=Image.new('RGB',(w,h),'#101115');d=ImageDraw.Draw(im)
    for i,c in enumerate(('#F06C66','#F0C05C','#65C46F')):d.ellipse((22+i*23,22,34+i*23,34),fill=c)
    center(d,'Codex CLI',21,w,19,GRAY,False)
    d.line((0,61,w,61),fill='#2A2B33')
    rows=[('› $laneorchestrator add CSV export filtering',WHITE),('',WHITE),('Astra  /  High',PURPLE),('Inspecting reports.py, csv_export.py and tests…',GRAY),('',WHITE),('Selected: Python specialist',WHITE),('Model:    gpt-5.6-terra',CYAN),('Thinking: medium',CYAN),('Reason:   bounded scope; established export pattern',GRAY),('',WHITE),('✓ Updated csv_export.py and reports.py',GREEN),('✓ Export formatting checks',GREEN),('✓ Status filtering checks',GREEN),('✓ Input preservation checks',GREEN),('',WHITE),('Ready for handoff.',WHITE)]
    visible=max(1,int(clamp(u/.83)*len(rows)))
    fs=24 if w<1000 else 25
    for i,(row,color) in enumerate(rows[:visible]):
        if len(row)>58 and w<1000:row=row[:58]
        text(d,(32,94+i*37),row,fs,color,mono=True)
    if int(u*24)%2==0:d.rectangle((32,97+visible*37,43,121+visible*37),fill=PURPLE)
    return im

def orb(d,cx,cy,r,t,color=PURPLE):
    for i in range(7):
        a=t*.55+i*math.pi/7
        pts=[]
        for q in range(101):
            v=q*math.tau/100
            px=math.cos(v)*r;py=math.sin(v)*r*.28
            pts.append((cx+px*math.cos(a)-py*math.sin(a),cy+px*math.sin(a)+py*math.cos(a)))
        d.line(pts,fill=color if i%3==0 else '#51416F',width=2)

def frame(t,scenes=SCENES,vertical=False):
    w,h=(1080,1920) if vertical else (1920,1080)
    im=background(w,h).copy();d=ImageDraw.Draw(im)
    scene=next(s for s in scenes if s[0]<=t<s[1]);start,end,caption,kind=scene;u=(t-start)/(end-start)
    text(d,(52,35),'LaneOrchestrator',24,WHITE,True)
    text(d,(w-276,39),'DEMO RE-CREATION',16,GRAY)
    if kind in ('intro','reveal','network','end'):
        cx=w/2;cy=h*.46
        orb(d,cx,cy,310 if vertical else 330,t)
        if kind=='intro':
            center(d,'ONE PROMPT.',h*.32,w,88 if vertical else 128)
            count=int(172*ease((u-.2)/.65))
            center(d,str(count)+' specialists.',h*.54,w,55 if vertical else 74,PURPLE)
        elif kind=='reveal':
            size=(155 if vertical else 240)+int(25*(1-ease(u*2)))
            center(d,'ASTRA',h*.32,w,size)
            center(d,'Choose the model.',h*.56,w,42 if vertical else 54,PURPLE,False)
            if u>.28:center(d,'Choose the thinking.',h*.56+75,w,42 if vertical else 54,CYAN,False)
        elif kind=='network':
            names=['Python','Frontend','Security','Data','Architecture','Testing','API','UX','DevOps','Database','Mobile','Research']
            for i,name in enumerate(names):
                a=i*math.tau/len(names)+t*.05
                x=cx+math.cos(a)*(365 if vertical else 685);y=cy+math.sin(a)*(400 if vertical else 290)
                text(d,(x-60,y),name,25,GRAY)
            center(d,'172',cy-112,w,165)
            center(d,'SPECIALISTS',cy+87,w,29,PURPLE)
        else:
            center(d,'LaneOrchestrator',h*.36,w,77 if vertical else 126)
            center(d,'Now led by Astra.',h*.54,w,45 if vertical else 62,PURPLE,False)
            center(d,'github.com/KarthikRamesh9149',h*.72,w,27 if vertical else 31,GRAY,False)
            center(d,'/laneorchestrator',h*.72+48,w,34 if vertical else 40,CYAN,False)
    else:
        center(d,caption,200 if vertical else 105,w,44 if vertical else 46)
        aw,ah=(960,1020) if vertical else (1540,820)
        app=terminal(u,aw,ah) if kind=='cli' else desktop(kind,u,aw,ah)
        # Slow camera push, combined with actual UI state progression.
        z=(.91+.09*ease(u)) if kind in ('select','implement','verify') else (.96+.035*ease(u))
        app=app.resize((int(aw*z),int(ah*z)),Image.Resampling.LANCZOS)
        x=(w-app.width)//2;y=(h-app.height)//2+(80 if vertical else 46)
        if u<.1:x+=int((1-ease(u/.1))*65)
        mask=Image.new('L',app.size,0);ImageDraw.Draw(mask).rounded_rectangle((0,0,app.width-1,app.height-1),24,fill=255)
        im.paste(app,(x,y),mask)
        d=ImageDraw.Draw(im)
        d.rounded_rectangle((x,y,x+app.width-1,y+app.height-1),24,outline='#5A4C70',width=2)
        if vertical:center(d,'ASTRA SELECTS  ·  CODEX EXECUTES',1580,w,21,PURPLE,False)
    d=ImageDraw.Draw(im)
    d.line((52,h-38,w-52,h-38),fill='#2D263C',width=2)
    d.line((52,h-38,52+(w-104)*t/scenes[-1][1],h-38),fill=PURPLE,width=3)
    # Very short transitions preserve momentum instead of long slide fades.
    fade=min(ease((t-start)/.16),ease((end-t)/.13))
    if fade<1:im=Image.blend(background(w,h),im,fade)
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
    for start in [0,3,8,14,20,26,33,39,45,56,60]:
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ffmpeg',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--format',choices=['launch','social','tour'],default='launch');p.add_argument('--preview',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);scenes={'launch':SCENES,'social':SOCIAL,'tour':TOUR}[a.format];vertical=a.format=='social';seconds=scenes[-1][1];name='laneorchestrator-astra-'+a.format
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
