'use strict';
class FaceVolume {
 constructor(onVolume,onState){this.onVolume=onVolume;this.onState=onState;this.wanted=false;this.revision=0;this.reference=null;this.samples=[];this.lastFace=0;this.tracked=null;}
 async start(){
  this.stop();this.wanted=true;const revision=++this.revision;
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){this.stop();this.onState('unavailable');return;}
  this.onState('permission');
  try{
   const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:24}},audio:false});
   if(revision!==this.revision){stream.getTracks().forEach(t=>t.stop());return;}
   this.stream=stream;stream.getVideoTracks()[0].addEventListener('ended',()=>{if(this.wanted){this.stop();this.onState('ended');}});
   const video=document.createElement('video');video.muted=true;video.playsInline=true;video.srcObject=stream;this.video=video;
   await video.play();if(revision!==this.revision)return;
   this.onState('loading');this.worker=new Worker('/demo/face-worker.js?v=1');
   this.timeout=setTimeout(()=>{if(revision===this.revision){this.stop();this.onState('error');}},20000);
   this.worker.onerror=()=>{if(revision===this.revision){this.stop();this.onState('error');}};
   this.worker.onmessage=({data})=>{
    if(revision!==this.revision)return;
    if(data.type==='ready'){clearTimeout(this.timeout);this.onState('searching');this.capture(revision);}
    if(data.type==='faces'){
     clearTimeout(this.timeout);this.observe(data.faces,performance.now());
     this.timer=setTimeout(()=>this.capture(revision),120);
    }
    if(data.type==='error'){this.stop();this.onState('error');}
   };
   this.worker.postMessage({type:'init'});
  }catch(error){if(revision===this.revision){this.stop();this.onState(error.name==='NotAllowedError'?'denied':error.name==='NotFoundError'?'missing':'error');}}
 }
 async capture(revision){
  if(revision!==this.revision||!this.worker)return;
  try{
   const bitmap=await createImageBitmap(this.video);
   if(revision!==this.revision){bitmap.close();return;}
   this.worker.postMessage({type:'frame',bitmap,width:bitmap.width,height:bitmap.height,timestamp:performance.now()},[bitmap]);
   this.timeout=setTimeout(()=>{if(revision===this.revision){this.stop();this.onState('error');}},5000);
  }catch{if(revision===this.revision){this.stop();this.onState('error');}}
 }
 observe(faces,now){
  const valid=faces.filter(f=>f.width>.04&&f.height>.04&&Number.isFinite(f.x+f.y+f.width+f.height));
  // Choose a single centred face first, then prefer that face's previous position.
  const anchor=this.tracked||{x:.5,y:.5};
  valid.sort((a,b)=>Math.hypot(a.x+a.width/2-anchor.x,a.y+a.height/2-anchor.y)-Math.hypot(b.x+b.width/2-anchor.x,b.y+b.height/2-anchor.y));
  const face=valid[0];
  if(!face){
   if(now-this.lastFace>800){this.onVolume(1);this.onState('searching');this.samples=[];}
   if(now-this.lastFace>3000){this.reference=null;this.tracked=null;}
   return;
  }
  this.lastFace=now;this.tracked={x:face.x+face.width/2,y:face.y+face.height/2};
  const size=Math.sqrt(face.width*face.height);
  if(!this.reference){
   this.samples.push(size);this.onState('calibrating');
   if(this.samples.length<6)return;
   const sorted=[...this.samples].sort((a,b)=>a-b);this.reference=(sorted[2]+sorted[3])/2;
  }
  // Relative apparent face size is a distance cue, not a physical-distance measurement.
  const ratio=Math.max(.4,Math.min(1.65,Math.pow(size/this.reference,1.3)));
  this.onVolume(ratio);this.onState('tracking',ratio);
 }
 stop(){
  this.wanted=false;this.revision++;clearTimeout(this.timer);clearTimeout(this.timeout);
  this.worker?.terminate();this.worker=null;
  this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
  if(this.video){this.video.pause();this.video.srcObject=null;this.video=null;}
  this.reference=null;this.samples=[];this.tracked=null;this.lastFace=0;
  this.onVolume(1);this.onState('off');
 }
}
