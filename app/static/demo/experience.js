'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const moods={
 focus:{color:[7,94,232]},
 night:{color:[100,66,183]},
 air:{color:[11,119,110]}
};
let mood='focus',visualTime=0,previousTime=0,reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
let rotation={x:0,y:0,z:0},color=[...moods.focus.color],visible=true,drag=null,sculptureDirty=true;
const canvas=$('#sound-sculpture'),ctx=canvas.getContext('2d');let cw=0,ch=0;
const pointer={x:0,y:0,active:false,proximity:0,frequency:650};
const heroSound=new SoundSketch(state=>{
 const button=$('#hero-sound-toggle'),active=state==='playing'||state==='starting';
 button.setAttribute('aria-pressed',String(active));
 button.querySelector('span').textContent=active?'🔊':'🔇';
 const label=active?'Mute sound':'Turn sound on';button.setAttribute('aria-label',label);button.title=label;
 button.setAttribute('aria-busy',String(state==='starting'));
 $('#hero-sound-status').classList.toggle('sculpture-keyboard',state!=='error');$('#hero-sound-status').classList.toggle('control-error',state==='error');
 $('#hero-sound-status').textContent=state==='error'?'Sound could not start. Try turning it on again.':state==='playing'?'Sound on. Follow the curve to emphasize different frequencies; turn the shape over for a softer, more spacious sound.':state==='stopped'?'Sound off.':'';
});
const faceVolume=new FaceVolume(gain=>heroSound.setDistance(gain),(state,ratio)=>{
 const button=$('#face-volume-toggle'),active=!['off','unavailable','denied','missing','ended','error'].includes(state);
 button.setAttribute('aria-pressed',String(active));
 const label=active?'Turn camera off':'Use camera for volume';button.setAttribute('aria-label',label);button.title=label;
 button.setAttribute('aria-busy',String(['permission','loading','calibrating'].includes(state)));
 const messages={permission:'Allow camera access to control volume.',loading:'Loading face detection…',searching:'Looking for your face · Default volume',calibrating:'Hold still briefly to set your normal distance.',tracking:'Camera volume on · Move closer or farther',unavailable:'Camera requires HTTPS or localhost.',denied:'Camera permission was declined. You can try again.',missing:'No camera was found.',ended:'Camera disconnected.',error:'Camera could not start. Try again.',off:''};
 const status=$('#face-volume-state');
 const message=messages[state]||'';if(status.textContent!==message)status.textContent=message;
 const error=['unavailable','denied','missing','ended','error'].includes(state);status.classList.toggle('sculpture-keyboard',!error);status.classList.toggle('control-error',error);
});
$('#face-volume-toggle').addEventListener('click',()=>{if(faceVolume.wanted)faceVolume.stop();else faceVolume.start();});
$('#hero-sound-toggle').addEventListener('click',()=>{
 if(heroSound.wanted){heroSound.stop();return;}
 heroSound.start(mood);
});
function resetView(){rotation={x:0,y:0,z:0};sculptureDirty=true;}
function turn(axis,amount){rotation[axis]=(rotation[axis]+amount)%(Math.PI*2);sculptureDirty=true;}
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',e=>{reducedMotion=e.matches;sculptureDirty=true;});
function trackPointer(e){const r=canvas.getBoundingClientRect();pointer.x=e.clientX-r.left;pointer.y=e.clientY-r.top;pointer.active=true;}
canvas.addEventListener('pointerleave',()=>{pointer.active=false;});
canvas.addEventListener('pointerdown',e=>{
 if(drag || !e.isPrimary || e.button!==0)return;
 e.preventDefault();canvas.classList.add('pointer-input');trackPointer(e);canvas.focus({preventScroll:true});
 drag={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging');
});
canvas.addEventListener('pointermove',e=>{
 if(!e.isPrimary)return;
 trackPointer(e);
 if(!drag || drag.id!==e.pointerId)return;
 const r=canvas.getBoundingClientRect(),dx=(e.clientX-drag.x)/r.width*Math.PI*2,dy=(e.clientY-drag.y)/r.height*Math.PI*2;
 if(e.shiftKey)turn('z',dx);else{turn('y',dx);turn('x',dy);}
 drag.x=e.clientX;drag.y=e.clientY;
});
function finishDrag(e){if(e.pointerType==='touch'||e.type==='pointercancel')pointer.active=false;if(!drag || drag.id!==e.pointerId)return;drag=null;canvas.classList.remove('dragging');if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);}
for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(event,finishDrag);
document.addEventListener('keydown',e=>{if(e.key==='Tab')canvas.classList.remove('pointer-input');});
canvas.addEventListener('keydown',e=>{
 canvas.classList.remove('pointer-input');
 if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;
 e.preventDefault();
 if(e.key==='Home'){resetView();return;}
 const step=Math.PI/18;
 if(e.key==='ArrowLeft'||e.key==='ArrowRight')turn(e.shiftKey?'z':'y',e.key==='ArrowLeft'?-step:step);
 else turn('x',e.key==='ArrowUp'?-step:step);
});
function size(){const r=canvas.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);cw=r.width;ch=r.height;canvas.width=cw*d;canvas.height=ch*d;ctx.setTransform(d,0,0,d,0,0);sculptureDirty=true;}
const points=[];
const orbitRings=Array.from({length:12},(_,i)=>i*9);
for(let ring=0;ring<106;ring++)for(let bead=0;bead<30;bead++)points.push({u:ring/106*Math.PI*2,v:bead/30*Math.PI*2,ring,bead,offsetX:0,offsetY:0});
function drawSculpture(dt){
 ctx.clearRect(0,0,cw,ch);
 const t=visualTime*.00016,rx=-.48+rotation.x,ry=.18+rotation.y+t*.22,scale=Math.min(cw,ch)*.32;
 const wave=(mood==='night'?.17:mood==='air'?.37:.25)+heroSound.level*.12;
 const influenceRadius=Math.min(120,Math.min(cw,ch)*.24),ease=1-Math.exp(-dt/85);
 const plotted=points.map(p=>{
  const radius=1+wave*Math.cos(3*p.u+t*2),tube=.26+.08*Math.sin(2*p.u-t);
  let x=(radius+tube*Math.cos(p.v))*Math.cos(p.u),y=(radius+tube*Math.cos(p.v))*Math.sin(p.u),z=tube*Math.sin(p.v)+.26*Math.sin(3*p.u+t);
  let xx=x*Math.cos(ry)+z*Math.sin(ry),zz=-x*Math.sin(ry)+z*Math.cos(ry);x=xx;z=zz;
  let yy=y*Math.cos(rx)-z*Math.sin(rx);zz=y*Math.sin(rx)+z*Math.cos(rx);y=yy;z=zz;
  const tilt=-.53+rotation.z;xx=x*Math.cos(tilt)-y*Math.sin(tilt);yy=x*Math.sin(tilt)+y*Math.cos(tilt);
  const perspective=3.8/(3.8-z),screenX=cw*.5+xx*scale*perspective,screenY=ch*.49+yy*scale*perspective;
  p.screenX=screenX;p.screenY=screenY;p.depth=z;
  const dx=screenX-pointer.x,dy=screenY-pointer.y,distance=Math.hypot(dx,dy);
  const falloff=pointer.active&&!reducedMotion?Math.max(0,1-distance/influenceRadius):0;
  const push=falloff*falloff*influenceRadius*.42;
  p.offsetX+=(dx/Math.max(distance,1)*push-p.offsetX)*ease;
  p.offsetY+=(dy/Math.max(distance,1)*push-p.offsetY)*ease;
  if(Math.abs(p.offsetX)<.001)p.offsetX=0;
  if(Math.abs(p.offsetY)<.001)p.offsetY=0;
  return{x:screenX+p.offsetX,y:screenY+p.offsetY,z,p};
 }).sort((a,b)=>a.z-b.z);
 for(const p of plotted){const depth=(p.z+1.5)/3,light=Math.max(0,Math.sin(p.p.v+.7)*.6+.25),alpha=.22+depth*.7;const rgb=color.map(v=>Math.round(v+(255-v)*light*.68));ctx.fillStyle=`rgba(${rgb.join(',')},${alpha})`;ctx.beginPath();ctx.arc(p.x,p.y,Math.max(.5,(.65+depth*1.1)*Math.min(cw/750,1.2)),0,Math.PI*2);ctx.fill();}
 // Sparse orbit lines make the continuous shape legible between the particles.
 ctx.strokeStyle=`rgba(${color.map(Math.round).join(',')},.12)`;ctx.lineWidth=.6;
 for(const ring of orbitRings){const line=plotted.filter(p=>p.p.ring===ring).sort((a,b)=>a.p.bead-b.p.bead);ctx.beginPath();line.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.closePath();ctx.stroke();}
}
function animate(now){
 const dt=Math.min(now-previousTime,45);previousTime=now;
 if(!document.hidden){
  let nearest=Infinity,closest=null;
  if(pointer.active&&visible)for(const p of points){
   if(p.screenX<0||p.screenX>cw||p.screenY<0||p.screenY>ch)continue;
   const distance=Math.hypot(p.screenX-pointer.x,p.screenY-pointer.y);
   if(distance<nearest){nearest=distance;closest=p;}
  }
  const radius=Math.min(120,Math.min(cw,ch)*.24);
  pointer.proximity=radius>0?Math.max(0,1-nearest/radius):0;
  if(closest&&pointer.proximity>0){
   // Intrinsic position stays attached to the ribbon when it rotates. The closed loop
   // travels bass -> treble -> bass, avoiding a jump at its seam.
   let weight=0,tone=0;
   for(const p of points){
    const distance=Math.hypot(p.screenX-pointer.x,p.screenY-pointer.y);
    if(distance>nearest+14)continue;
    const w=Math.exp(-(distance-nearest)/5+p.depth);
    tone+=(1-Math.cos(p.u))*.5*w;weight+=w;
   }
   pointer.frequency=120*Math.pow(3200/120,weight?tone/weight:(1-Math.cos(closest.u))*.5);
  }
  heroSound.shape(pointer,cw,ch,rotation);

 }
 if(visible && !document.hidden){
  if(!reducedMotion)visualTime+=dt;
  if(!reducedMotion || sculptureDirty || points.some(p=>p.offsetX||p.offsetY)){drawSculpture(dt);sculptureDirty=false;}
 }
 requestAnimationFrame(animate);
}
new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)sculptureDirty=true;},{rootMargin:'200px'}).observe($('.hero'));
addEventListener('resize',size);size();requestAnimationFrame(animate);
$$('[data-mood]').forEach(button=>button.addEventListener('click',()=>{
 mood=button.dataset.mood;
 if(heroSound.wanted)heroSound.setMood(mood);
 color=[...moods[mood].color];sculptureDirty=true;
 $$('[data-mood]').forEach(el=>{el.classList.toggle('active',el===button);el.setAttribute('aria-pressed',String(el===button));});
}));
const chapters=[{src:'situation-clarify-v1.png',name:'Start with intent.',alt:'A creator describing a mood to an original illustrated companion'},{src:'situation-compare-v2.png',name:'Hear the alternatives.',alt:'A creator listening to music alternatives with the TuneJury character'},{src:'situation-record-v1.png',name:'Keep your decision.',alt:'A creator receiving her chosen music and decision record'}];let activeChapter=0;
function updateChapter(){let best=0,dist=Infinity;$$('.chapter').forEach((el,i)=>{const r=el.getBoundingClientRect(),d=Math.abs(r.top+r.height*.5-innerHeight*.57);if(d<dist){dist=d;best=i;}});if(best!==activeChapter){activeChapter=best;const c=chapters[best];$('#story-art').src=c.src;$('#story-art').alt=c.alt;$('#chapter-name').textContent=c.name;$('#chapter-count').textContent=`0${best+1} / 03`;$$('.chapter-indicator i').forEach((el,i)=>el.classList.toggle('active',i===best));}}
let scrollQueued=false;addEventListener('scroll',()=>{if(scrollQueued)return;scrollQueued=true;requestAnimationFrame(()=>{updateChapter();scrollQueued=false;});},{passive:true});
document.addEventListener('visibilitychange',()=>{if(document.hidden){pointer.active=false;faceVolume.stop();heroSound.stop();}});addEventListener('pagehide',()=>{faceVolume.stop();heroSound.stop();});
