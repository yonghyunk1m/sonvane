'use strict';
// Microphone recordings are converted to mono 16 kHz PCM WAV before upload.
// No browser speech-recognition service or voice-cloning API is used.
window.StudioRecorder = class {
  constructor(onAudio, onError) { this.onAudio=onAudio;this.onError=onError;this.active=false;this.cancelled=false; }
  async start() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw Error('Microphone recording is unavailable in this browser. You can type your message.');
    this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
    if(this.cancelled){this.stream.getTracks().forEach(t=>t.stop());return;}
    const preferred=['audio/webm;codecs=opus','audio/mp4','audio/webm'].find(t=>MediaRecorder.isTypeSupported(t));
    this.recorder=new MediaRecorder(this.stream,preferred?{mimeType:preferred}:{});
    this.chunks=[];
    this.recorder.ondataavailable=e=>{if(e.data.size)this.chunks.push(e.data);};
    this.recorder.onerror=()=>{this.cancel();this.onError(Error('Microphone recording failed. Please try again.'));};
    this.recorder.onstop=async()=>{
      if(this.cancelled)return;
      try {
        const context=new AudioContext();let decoded;
        try{decoded=await context.decodeAudioData(await new Blob(this.chunks,{type:this.recorder.mimeType}).arrayBuffer());}finally{await context.close();}
        const duration=Math.min(decoded.duration,30);
        if(duration<.3)throw Error('Record at least a short phrase before stopping.');
        const offline=new OfflineAudioContext(1,Math.ceil(duration*16000),16000);
        const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();
        const buffer=await offline.startRendering();const samples=buffer.getChannelData(0);
        const bytes=new ArrayBuffer(44+samples.length*2),view=new DataView(bytes);
        const text=(at,s)=>{for(let i=0;i<s.length;i++)view.setUint8(at+i,s.charCodeAt(i));};
        text(0,'RIFF');view.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');
        view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);
        view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,samples.length*2,true);
        for(let i=0;i<samples.length;i++){const n=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,n<0?n*32768:n*32767,true);}
        if(!this.cancelled)await this.onAudio(new Blob([bytes],{type:'audio/wav'}));
      } catch(e){if(!this.cancelled)this.onError(e);}
    };
    this.recorder.start();this.active=true;this.started=Date.now();this.timer=setTimeout(()=>this.stop(),30000);
  }
  stop(){clearTimeout(this.timer);if(this.recorder?.state==='recording')this.recorder.stop();this.stream?.getTracks().forEach(t=>t.stop());this.active=false;}
  cancel(){this.cancelled=true;this.stop();}
};
window.StudioSpeech = {
  voice(){return window.speechSynthesis?.getVoices().find(v=>v.localService&&v.lang.toLowerCase().startsWith('en'));},
  stop(){window.speechSynthesis?.cancel();},
  speak(text){const voice=this.voice();if(!voice)throw Error('This browser has no local English reading voice. The written reply remains available.');this.stop();const utterance=new SpeechSynthesisUtterance(text);utterance.voice=voice;utterance.lang=voice.lang;utterance.rate=1;window.speechSynthesis.speak(utterance);}
};
