import React, {useEffect, useRef, useState} from 'react';
import {overlayAt} from './videoTimeline';
import {overlayLabel} from './wearingStatus';

const PLAYBACK_DELAY = 0.55;

export function useNativePlayback(source, run, connected) {
  const video=useRef(null), clock=useRef(null), synced=useRef('');
  const [position,setPosition]=useState(0), [dimensions,setDimensions]=useState(null);
  const [mediaError,setMediaError]=useState(''), [buffering,setBuffering]=useState(false);
  useEffect(()=>{
    setPosition(0);setDimensions(null);setMediaError('');setBuffering(false);synced.current='';
  },[source?.id]);
  useEffect(()=>{clock.current={run,connected,received:performance.now()};},[run,connected]);
  useEffect(()=>{
    const timer=setInterval(()=>{
      const element=video.current, state=clock.current;
      if(!element||!state||element.readyState<1) return;
      const current=state.run;
      setPosition(element.currentTime);
      if(!state.connected||performance.now()-state.received>1800){element.pause();return;}
      if(!current){element.pause();return;}
      const running=current.status==='RUNNING';
      const elapsed=running?(performance.now()-state.received)/1000:0;
      const raw=Math.min(current.duration_s||element.duration, (current.playback_time_s??current.source_time_s)+elapsed);
      const target=running?Math.max(current.playback_epoch_start_s||0,raw-PLAYBACK_DELAY):raw;
      const key=`${current.id}:${current.generation}`;
      const changed=synced.current!==key;
      if(changed){
        synced.current=key;
        element.currentTime=Math.max(0,Math.min(target,element.duration-0.01));
      }
      if(!running){
        // Let the small presentation buffer finish naturally when analysis reaches EOF.
        if(current.status==='FINISHED'&&!changed&&!element.paused&&!element.ended) return;
        element.pause();element.playbackRate=1;
        if(Math.abs(element.currentTime-target)>0.15) element.currentTime=Math.max(0,Math.min(target,element.duration-0.01));
        return;
      }
      if(raw-(current.playback_epoch_start_s||0)<PLAYBACK_DELAY){element.pause();return;}
      const drift=target-element.currentTime;
      if(Math.abs(drift)>1.25) element.currentTime=Math.max(0,Math.min(target,element.duration-0.01));
      element.playbackRate=drift>0.15?1.04:drift< -0.15?0.96:1;
      if(element.paused&&!element.ended) element.play().catch(error=>{
        if(error.name!=='AbortError')setMediaError('영상 재생이 차단되었습니다. 재생 버튼을 다시 눌러 주세요.');
      });
    },100);
    return()=>clearInterval(timer);
  },[]);
  const loaded=()=>{
    const element=video.current;
    setDimensions([element.videoWidth,element.videoHeight]);setMediaError('');synced.current='';
  };
  return {video,position,dimensions,mediaError,buffering,loaded,
    waiting:()=>setBuffering(true), ready:()=>setBuffering(false),
    failed:()=>{setBuffering(false);setMediaError('원본 영상 재생 실패 · 연결 또는 영상 코덱을 확인해 주세요.');}};
}

export function TrackingOverlay({video,run,connected,sourceKey,onPresentedFrame}) {
  const canvas=useRef(null), state=useRef(null);
  useEffect(()=>{state.current={run,connected,received:performance.now()};},[run,connected]);
  useEffect(()=>{
    let handle,frameHandle,presentedTime=null,notified;
    const publish=(active,frame)=>{
      const key=frame?`${active.id}:${active.generation}:${frame.source_time_s}:${frame.scene_epoch}`:'none';
      if(key!==notified){notified=key;onPresentedFrame(frame?{...frame,run_id:active.id}:null);}
    };
    const nativeVideo=video.current;
    const onFrame=(_now,metadata)=>{
      presentedTime=metadata.mediaTime;
      frameHandle=nativeVideo.requestVideoFrameCallback(onFrame);
    };
    if(nativeVideo?.requestVideoFrameCallback)frameHandle=nativeVideo.requestVideoFrameCallback(onFrame);
    const draw=()=>{
      handle=requestAnimationFrame(draw);
      const surface=canvas.current, element=video.current, current=state.current;
      if(!surface||!element) return;
      const rect=surface.getBoundingClientRect(), ratio=window.devicePixelRatio||1;
      const width=Math.round(rect.width*ratio), height=Math.round(rect.height*ratio);
      if(surface.width!==width||surface.height!==height){surface.width=width;surface.height=height;}
      const context=surface.getContext('2d');
      context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,rect.width,rect.height);
      const position=presentedTime??element.currentTime;
      surface.dataset.videoTime=position.toFixed(3);
      surface.dataset.trackingTime='';surface.dataset.sceneEpoch='';surface.dataset.trackCount='0';
      const active=current?.run;
      if(!current?.connected||performance.now()-current.received>1800||active?.status!=='RUNNING'||element.seeking||element.readyState<2){publish(active,null);return;}
      const frame=overlayAt(active.overlay_frames||[],position,active.generation);
      if(!frame||!active.source_width||!active.source_height){publish(active,null);return;}
      publish(active,frame);
      surface.dataset.trackingTime=frame.source_time_s.toFixed(3);
      surface.dataset.sceneEpoch=String(frame.scene_epoch);
      surface.dataset.trackCount=String(frame.tracks.length);
      const scale=Math.min(rect.width/active.source_width,rect.height/active.source_height);
      const dx=(rect.width-active.source_width*scale)/2,dy=(rect.height-active.source_height*scale)/2;
      const box=(bounds,color,label)=>{
        const [x1,y1,x2,y2]=bounds;
        const x=x1*scale+dx,y=y1*scale+dy,w=(x2-x1)*scale,h=(y2-y1)*scale;
        context.strokeStyle=color;context.lineWidth=2;context.strokeRect(x,y,w,h);
        context.font='11px sans-serif';
        const textWidth=context.measureText(label).width+10;
        const labelX=Math.max(0,Math.min(x,rect.width-textWidth)),labelY=Math.max(0,y-21);
        context.fillStyle=color;context.fillRect(labelX,labelY,textWidth,20);
        context.fillStyle='#fff';context.fillText(label,labelX+5,labelY+14);
      };
      for(const track of frame.tracks){
        const fresh=track.source_time_s!=null&&position-track.source_time_s<=5;
        const wearing=fresh?track.wearing:'UNKNOWN';
        const alarm=track.active_violations?.length>0;
        box(track.bbox,wearing==='NOT_WORN'||alarm?'#c44748':['WORN','VISIBLE_WORN'].includes(wearing)?'#168063':'#a97419',
          `#${track.track_id} ${overlayLabel({...track,wearing})}`);
      }
      if(frame.scene.processing_state==='RUNNING') for(const item of frame.scene.detections) box(item.bbox,'#a97419','연무·분출 후보');
    };
    handle=requestAnimationFrame(draw);
    return()=>{cancelAnimationFrame(handle);if(frameHandle!==undefined)nativeVideo.cancelVideoFrameCallback(frameHandle);};
  },[video,sourceKey,onPresentedFrame]);
  return <canvas ref={canvas} className="tracking-canvas" aria-label="영상 시각에 맞춘 사람 추적 표시"/>;
}
