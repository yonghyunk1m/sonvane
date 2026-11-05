"""Editable system figures with existing approved character illustrations. No model calls."""
from pathlib import Path
import base64
import tempfile
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from matplotlib import font_manager
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'app/static/report'
# Use the same locally licensed Inter as the website; static instances let
# Matplotlib embed accurate regular/semibold outlines in PDF and PNG exports.
_FONT_TEMP = tempfile.TemporaryDirectory(prefix='sonvane-figure-fonts-')
for weight, style in ((400, 'Regular'), (600, 'SemiBold')):
 font = TTFont(ROOT/'app/static/assets/inter.woff2')
 font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
 font.flavor = None
 for name_id, value in ((1, 'Inter'), (2, style), (4, f'Inter {style}'), (6, f'Inter-{style}')):
  font['name'].setName(value, name_id, 3, 1, 0x409)
 target = Path(_FONT_TEMP.name)/f'Inter-{style}.ttf'
 font.save(target)
 font_manager.fontManager.addfont(target)
plt.rcParams.update({'font.family':'Inter','svg.fonttype':'none','pdf.fonttype':42,'svg.hashsalt':'sonvane-report'})
BLUE='#075ee8';INK='#202b38';MUTED='#526273';LINE='#a7b4c3'
def canvas(height):
 f,a=plt.subplots(figsize=(11,height));f.subplots_adjust(0,0,1,1);a.set_xlim(0,11);a.set_ylim(0,height);a.axis('off');return f,a

def box(a,x,y,w,h,title,body,accent=False):
 a.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025,rounding_size=0.07',facecolor='#edf4ff' if accent else '#f5f7f9',edgecolor='#b1c9ec' if accent else '#d4dce5',linewidth=1))
 a.text(x+.13,y+h-.23,title,fontsize=13,weight='semibold',color=BLUE if accent else INK,va='top')
 a.text(x+.13,y+h-.57,body,fontsize=11.5,color=MUTED,va='top',linespacing=1.45)
def arrow(a,start,end,label=None,curve=0):
 a.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=13,color=LINE,linewidth=1.4,connectionstyle=f'arc3,rad={curve}'))
 if label:a.text((start[0]+end[0])/2,(start[1]+end[1])/2+.12,label,fontsize=10,color=MUTED,ha='center')
def save(f,name):
 OUT.mkdir(parents=True,exist_ok=True)
 for fmt in (('svg','pdf','png') if name=='pipeline' else ('svg','pdf')):
  metadata={'Date':None} if fmt=='svg' else {'CreationDate':None,'ModDate':None} if fmt=='pdf' else {}
  f.savefig(OUT/f'{name}.{fmt}',facecolor='white',dpi=180,metadata=metadata)
 svg=OUT/f'{name}.svg'
 encoded=base64.b64encode((ROOT/'app/static/assets/inter.woff2').read_bytes()).decode()
 source=svg.read_text().replace('<defs>', '<defs><style>@font-face{font-family:Inter;src:url(data:font/woff2;base64,'+encoded+") format('woff2');font-weight:100 900}</style>", 1)
 svg.write_text('\n'.join(line.rstrip() for line in source.splitlines())+'\n')
 plt.close(f)

def illustrated_pipeline():
 # Text and connectors remain vector; approved artwork is embedded unchanged.
 f,a=plt.subplots(figsize=(14,10));f.subplots_adjust(0,0,1,1)
 a.set_xlim(0,14);a.set_ylim(0,10);a.axis('off')
 colors=[INK]*4
 titles=['Suggest a plan','Review & approve','Create & compare','Mix & keep']
 art=['situation-brief-v1.png','situation-criteria-v2.png','situation-compare-v2.png','situation-record-v1.png']
 roles=['Meta Muse Spark','Creator in control','ACE-Step + TuneJury','Sonvane + creator']
 descriptions=['Video + request → cues\nMusic and effect timings',
               'Preview, edit or remove\nApprove before generation',
               'Generate music variations\nScore music, then rank',
               'Hear the mix in your video\nKeep, revise or export']
 outputs=['Editable sound plan','Approved cue version','3 music variations','Video + audio + record']
 for i in range(4):
  x=i*3.5;cx=x+1.75;c=colors[i]
  if i:a.plot([x,x],[4.85,9.6],color='#dce1e6',lw=1)
  a.text(cx,9.85,f'{i+1:02d}',ha='center',va='top',fontsize=12,weight='semibold',color=c)
  a.text(cx,9.53,titles[i],ha='center',va='top',fontsize=21,weight='semibold',color=c)
  a.imshow(plt.imread(ROOT/'app/static/demo'/art[i]),extent=(x+.18,x+3.32,7.13,9.223),aspect='auto',zorder=2)
  a.text(cx,6.92,roles[i],ha='center',fontsize=12.8,weight='semibold',color=c)
  a.text(cx,6.58,descriptions[i],ha='center',va='top',fontsize=17,linespacing=1.5,color=INK)
  a.add_patch(FancyBboxPatch((x+.16,5.17),3.18,.62,boxstyle='round,pad=0.015,rounding_size=.07',facecolor='#f6f8fa',edgecolor='#d4dce5',lw=1))
  a.text(cx,5.48,outputs[i],ha='center',va='center',fontsize=16.6,color=INK)
  arrow(a,(cx,5.98),(cx,5.8))
  if i<3:arrow(a,(x+3.35,5.48),(x+3.63,5.48))
 a.text(.2,4.58,'How the approved plan becomes sound',fontsize=21,weight='semibold',color=INK)
 a.text(.2,4.18,'Music is evaluated. Effects are synthesized separately. Your choices stay editable.',fontsize=16.5,color=MUTED)
 def node(x,y,w,h,title,body,color=BLUE):
  a.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.015,rounding_size=.07',facecolor='#f7f9fc',edgecolor='#d4dce5',lw=1))
  a.text(x+w/2,y+h-.2,title,ha='center',va='top',fontsize=18,weight='semibold',color=color)
  a.text(x+w/2,y+h-.58,body,ha='center',va='top',fontsize=16,linespacing=1.3,color=INK)
 def route(points,color):
  xs,ys=zip(*points[:-1]);a.plot(xs,ys,color=color,lw=1.4)
  a.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=14,color=color,lw=1.4))
 node(.2,2.58,2.6,1.13,'Approved cues','Times + prompts',colors[1])
 node(3.65,2.58,2.6,1.13,'ACE-Step','3 variants / section',colors[0])
 node(7.1,2.58,2.6,1.13,'TuneJury + CLAP','Music-only signals',colors[2])
 node(10.55,2.58,3.25,1.13,'Rank + mix','Selected video output',colors[3])
 for x,y in [(2.8,3.65),(6.25,7.1),(9.7,10.55)]:arrow(a,(x+.02,3.14),(y-.03,3.14))
 a.text(3.22,3.36,'Music',ha='center',fontsize=13.5,color=MUTED)
 node(3.65,.95,2.6,1.12,'Local effects','5 synthesized types',colors[2])
 route([(1.5,2.56),(1.5,1.51),(3.62,1.51)],colors[2])
 a.text(2.55,1.72,'SFX cues',ha='center',fontsize=14,color=colors[2])
 route([(6.28,1.51),(6.63,1.51),(6.63,.65),(13.15,.65),(13.15,2.55)],colors[2])
 a.text(10.0,.83,'Effects bypass music evaluation',ha='center',fontsize=14.5,color=colors[2])
 node(7.1,1.14,2.6,.95,'Personal ranking','Explicit A/B feedback',colors[3])
 route([(9.72,1.61),(10.08,1.61),(10.08,2.81),(10.52,2.81)],colors[3])
 a.text(.2,.15,'Existing models stay fixed. Saved text guides Muse. Blue companion: original artwork, not a Meta mascot.',fontsize=13,color=MUTED)
 save(f,'pipeline')

def main():
 illustrated_pipeline()
 f,a=canvas(2.7)
 stages=[('Plan','Validated JSON'),('Generate','Saved candidates'),('Evaluate','Saved track scores'),('Mix','Playable output')]
 for i,(title,body) in enumerate(stages):
  x=.2+i*2.75;box(a,x,1.15,2.3,1.2,title,body,accent=i==3)
  if i<3:arrow(a,(x+2.33,1.75),(x+2.72,1.75))
 a.text(5.5,.65,'Stop / failure → retain checkpoints → resume unfinished work',ha='center',fontsize=13,color=BLUE)
 a.text(5.5,.2,'A failed revision keeps the previous playable selection.',ha='center',fontsize=11.5,color=MUTED)
 save(f,'recovery')
if __name__=='__main__':main()
