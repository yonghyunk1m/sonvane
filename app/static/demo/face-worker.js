'use strict';
// Run detection off the animation/audio thread. Frames never leave this worker.
var exports={};
importScripts('/assets/mediapipe/vision_bundle.js');
let detector;
onmessage=async({data})=>{
 try{
  if(data.type==='init'){
   const files=await exports.FilesetResolver.forVisionTasks('/assets/mediapipe/wasm');
   detector=await exports.FaceDetector.createFromOptions(files,{baseOptions:{modelAssetPath:'/assets/mediapipe/face_detector.tflite',delegate:'CPU'},runningMode:'VIDEO',minDetectionConfidence:.65});
   postMessage({type:'ready'});
  }else if(data.type==='frame'){
   try{
    const result=detector.detectForVideo(data.bitmap,data.timestamp);
    const faces=result.detections.map(d=>d.boundingBox).filter(Boolean).map(b=>({x:b.originX/data.width,y:b.originY/data.height,width:b.width/data.width,height:b.height/data.height}));
    postMessage({type:'faces',faces});
   }finally{data.bitmap.close();}
  }
 }catch{postMessage({type:'error'});}
};
