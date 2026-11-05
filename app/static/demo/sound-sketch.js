'use strict';
// An original, locally synthesized musical sketch for the interactive hero.
class SoundSketch {
 constructor(onChange){this.onChange=onChange;this.context=null;this.graph=null;this.voices=new Set();this.wanted=false;this.revision=0;this.level=0;this.distanceGain=1;}
 async start(mood){
  this.stop();this.wanted=true;const revision=++this.revision;this.onChange('starting');
  try{
   const Audio=window.AudioContext||window.webkitAudioContext;
   if(!Audio)throw new Error('Audio unavailable');
   if(!this.context)this.context=new Audio();
   await this.context.resume();
   if(revision!==this.revision||!this.wanted)return;
   const c=this.context,filter=c.createBiquadFilter(),presence=c.createBiquadFilter(),pan=c.createStereoPanner(),delay=c.createDelay(1),feedback=c.createGain(),wet=c.createGain(),master=c.createGain(),analyser=c.createAnalyser(),distance=c.createGain(),limiter=c.createDynamicsCompressor();
   filter.type='lowpass';filter.frequency.value=1600;filter.Q.value=.6;
   presence.type='peaking';presence.frequency.value=650;presence.Q.value=1.4;presence.gain.value=0;pan.pan.value=-.38;
   delay.delayTime.value=.32;feedback.gain.value=.24;wet.gain.value=.2;
   master.gain.setValueAtTime(0,c.currentTime);master.gain.linearRampToValueAtTime(.48,c.currentTime+.25);
   distance.gain.value=this.distanceGain;limiter.threshold.value=-12;limiter.knee.value=12;limiter.ratio.value=4;
   filter.connect(presence);presence.connect(pan);pan.connect(master);pan.connect(delay);delay.connect(feedback);feedback.connect(delay);delay.connect(wet);wet.connect(master);master.connect(distance);distance.connect(limiter);limiter.connect(analyser);analyser.connect(c.destination);
   analyser.fftSize=256;
   this.graph={filter,presence,pan,delay,feedback,wet,master,distance,limiter,analyser};this.samples=new Float32Array(analyser.fftSize);
   this.setMood(mood);this.step=0;this.nextNote=c.currentTime+.04;
   this.schedule();this.timer=setInterval(()=>this.schedule(),25);this.onChange('playing');
  }catch{if(revision===this.revision){this.stop();this.onChange('error');}}
 }
 setMood(mood){
  this.mood=mood;
  const presets={focus:{root:174.61,bpm:72,chords:[[0,4,7,11],[-3,0,4,7],[5,9,12,16],[7,12,14,17]]},night:{root:146.83,bpm:82,chords:[[0,3,7,10],[-4,0,3,7],[3,7,10,14],[-2,2,5,12]]},air:{root:196,bpm:100,chords:[[0,4,7,14],[5,9,12,16],[-3,0,4,7],[7,11,14,21]]}};
  this.preset=presets[mood]||presets.focus;
  if(this.graph){
   const now=this.context.currentTime;
   for(const voice of this.voices){voice.gain.gain.cancelAndHoldAtTime(now);voice.gain.gain.setTargetAtTime(.0001,now,.09);try{voice.osc.stop(now+.5);}catch{}}
   this.step=0;this.nextNote=now+.06;
   this.graph.delay.delayTime.setTargetAtTime(60/this.preset.bpm*.5,now,.15);
  }
 }
 note(frequency,at,duration,volume,type='sine',attack=.018){
  const c=this.context,osc=c.createOscillator(),gain=c.createGain();osc.type=type;osc.frequency.value=frequency;
  gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(volume,at+attack);gain.gain.exponentialRampToValueAtTime(.0001,at+duration);
  osc.connect(gain);gain.connect(this.graph.filter);const voice={osc,gain};this.voices.add(voice);
  osc.onended=()=>{osc.disconnect();gain.disconnect();this.voices.delete(voice);};osc.start(at);osc.stop(at+duration+.04);
 }
 schedule(){
  if(!this.graph)return;
  const now=this.context.currentTime;
  if(this.nextNote<now-.2)this.nextNote=now+.02;
  while(this.nextNote<now+.16){
   const {root,bpm,chords}=this.preset,eighth=30/bpm,chord=chords[Math.floor(this.step/16)%4],at=this.nextNote;
   const frequency=semitones=>root*Math.pow(2,semitones/12);
   if(this.step%16===0)chord.forEach((n,i)=>this.note(frequency(n),at+i*.025,eighth*18,.045,'triangle',.25));
   if(this.step%8===0)this.note(frequency(chord[0]-12),at,eighth*7,.17,'sine',.035);
   if(this.mood!=='focus'||this.step%2===0){
    const n=chord[[0,2,1,3,2,1,3,2][this.step%8]];
    this.note(frequency(n+12),at,eighth*2.8,this.step%4===0?.12:.075,'triangle');
    this.note(frequency(n+24),at,eighth*1.6,.014);
   }
   this.step++;this.nextNote+=eighth;
  }
 }
 shape(pointer,width,height,rotation){
  if(!this.graph)return;
  const now=this.context.currentTime,clamp=v=>Math.max(0,Math.min(1,v));
  // Facing swaps the stereo emphasis at either horizontal or vertical half turns.
  const facing=Math.cos(rotation.x)*Math.cos(rotation.y),back=(1-facing)/2;
  const proximity=pointer.active?Math.pow(clamp(pointer.proximity||0),.65):0;
  const heightAtPointer=1-clamp(pointer.y/Math.max(height,1));
  const frequency=Math.max(120,Math.min(3200,pointer.frequency||650));
  const baseCutoff=1600*Math.pow(.6,back);
  const cutoff=baseCutoff+(Math.max(baseCutoff,frequency*1.6)-baseCutoff)*proximity;
  this.graph.filter.frequency.setTargetAtTime(cutoff,now,.12);
  this.graph.filter.Q.setTargetAtTime(.6,now,.12);
  this.graph.presence.frequency.setTargetAtTime(frequency,now,.09);
  this.graph.presence.gain.setTargetAtTime(proximity*10,now,.14);
  this.graph.wet.gain.setTargetAtTime(.18+back*.14+proximity*(.08+heightAtPointer*.12),now,.18);
  this.graph.pan.pan.setTargetAtTime(-.38*facing+Math.sin(rotation.y)*.32+Math.sin(rotation.z)*.1,now,.15);
  this.graph.analyser.getFloatTimeDomainData(this.samples);
  const rms=Math.sqrt(this.samples.reduce((sum,v)=>sum+v*v,0)/this.samples.length);
  this.level+=(Math.min(1,rms*8)-this.level)*.2;
 }
 setDistance(gain){
  this.distanceGain=Math.max(.4,Math.min(1.65,gain));
  if(this.graph)this.graph.distance.gain.setTargetAtTime(this.distanceGain,this.context.currentTime,.3);
 }
 stop(){
  this.wanted=false;this.revision++;clearInterval(this.timer);this.timer=null;
  const graph=this.graph;this.graph=null;this.level=0;
  if(graph){const now=this.context.currentTime;graph.master.gain.cancelAndHoldAtTime(now);graph.master.gain.setTargetAtTime(0,now,.025);for(const voice of this.voices){try{voice.osc.stop(now+.15);}catch{}}setTimeout(()=>Object.values(graph).forEach(node=>node.disconnect()),200);}
  this.onChange('stopped');
 }
}
