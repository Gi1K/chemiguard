import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, ArrowDownToLine, ArrowLeft, Bell, Camera, Check, CheckCircle2, ChevronRight,
  Clock3, Cpu, FileVideo, History, ImagePlus, Layers3, LoaderCircle, Maximize2, Pause, Play, Plus,
  Radio, RotateCcw, Search, Settings2, ShieldCheck, SlidersHorizontal, Square, UserRound, Users,
  Video, Volume2, VolumeX, X, XCircle, Eye, ExternalLink } from 'lucide-react';
import './style.css';
import {TrackingOverlay, useNativePlayback} from './videoPlayback';
import {ProductCheck,ProductComparisons} from './productComparison';
import {SiteCatalog,siteReferences} from './siteCatalog';
import {observationLabel, WEARING_LABELS} from './wearingStatus';
import {VideoStatus} from './videoStatus.jsx';
import './demoShowcase.css';

const LABEL = {
  RUNNING: '분석 중', WAITING: '대기', LOADING: '모델 준비 중', PAUSED: '일시정지', STOPPED: '중지',
  FINISHED: '분석 완료', INTERRUPTED: '연결 중단', ERROR: '오류', STALE: '관측 만료', DISABLED: '비활성',
  ...WEARING_LABELS,
  VIOLATION_SUSPECTED: '미착용 경보', RELEASE_SUSPECTED: '누출', REVIEW_REQUIRED: '확인 필요',
  PRODUCT_MISMATCH_SUSPECTED: '등록 보호복 불일치 의심',
  OPEN: '미검토', ACKNOWLEDGED: '확인', DISMISSED: '반려', DEFERRED: '보류',
  covered: '착용', uncovered: '미착용', unobservable: '확인 불가', closed: '닫힘', open: '열림',
  not_visible: '안 보임', uncertain: '판독 불가',
};
const PARTS = {torso: '몸통', left_arm: '왼팔', right_arm: '오른팔', left_leg: '왼다리', right_leg: '오른다리', hood: '후드', closure: '여밈', respirator: '전면형 방독면'};
const NAV = [{id:'monitor', title:'영상 관제', icon:Radio}, {id:'sources', title:'시연 영상', icon:FileVideo},
  {id:'events', title:'사건 검토', icon:Bell}, {id:'policies', title:'작업 기준', icon:SlidersHorizontal},
  {id:'references', title:'등록 사진', icon:Layers3}, {id:'runs', title:'실행 이력', icon:History}];
const activeStatus = (value) => ['RUNNING','PAUSED','LOADING'].includes(value);
const timecode = (value=0) => `${Math.floor(value/60).toString().padStart(2,'0')}:${Math.floor(value%60).toString().padStart(2,'0')}`;
const date = (value) => value ? new Date(value).toLocaleString('ko-KR', {hour12:false, month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '-';
const tone = value => ['NOT_WORN','VIOLATION_SUSPECTED','PRODUCT_MISMATCH_SUSPECTED','ERROR','uncovered','open'].includes(value) ? 'red' : ['RELEASE_SUSPECTED','REVIEW_REQUIRED','UNKNOWN','STALE','DEFERRED','unobservable','uncertain'].includes(value) ? 'amber' : ['WORN','VISIBLE_WORN','RUNNING','covered','closed','ACKNOWLEDGED'].includes(value) ? 'green' : 'muted';

async function api(path, options={}) {
  const result = await fetch(`/api${path}`, { ...options, headers: options.body instanceof FormData ? {} : {'Content-Type':'application/json', ...options.headers} });
  if (!result.ok) {
    const data = await result.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.map?.(row=>row.msg).join(', ') || `요청 실패 (${result.status})`);
  }
  return result.json();
}
function Badge({value, children}) { return <span className={`badge ${tone(value)}`}><i/>{children || LABEL[value] || value}</span>; }
function IconButton({icon:Icon, title, ...props}) { return <button className="icon-button" title={title} aria-label={title} {...props}><Icon size={18}/></button>; }
function Empty({icon:Icon=Eye, children}) { return <div className="empty"><Icon size={28}/><p>{children}</p></div>; }
function Field({label, children, wide=false}) { return <label className={`field ${wide?'wide':''}`}><span>{label}</span>{children}</label>; }
function Modal({title, children, onClose, wide=false}) {
  useEffect(()=> { const listener=e=>{if(e.key==='Escape') onClose();}; document.addEventListener('keydown',listener); return ()=>document.removeEventListener('keydown',listener); },[onClose]);
  return <div className="modal-backdrop" onClick={onClose}><section role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide?'modal-wide':''}`} onClick={e=>e.stopPropagation()}>
    <header><h2>{title}</h2><IconButton icon={X} title="닫기" onClick={onClose}/></header>{children}</section></div>;
}

function App(){
  const [page,setPage]=useState('monitor');
  const [boot,setBoot]=useState(null), [run,setRun]=useState(null), [events,setEvents]=useState([]), [runs,setRuns]=useState([]);
  const [presented,setPresented]=useState(null);
  const [sourceId,setSourceId]=useState(''), [policyId,setPolicyId]=useState(''), [size,setSize]=useState('large');
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [toast,setToast]=useState(''), [connected,setConnected]=useState(true);
  const [modal,setModal]=useState(null), [eventDetail,setEventDetail]=useState(null), [sound,setSound]=useState(false);
  const eventIds=useRef(new Set()), initialized=useRef(false), syncedRun=useRef(null);
  const runVersion=useRef(0);
  const load = async () => {
    const data=await api('/bootstrap'); setBoot(data); setRun(data.active);
    setSourceId(id=>data.sources.some(row=>row.id===id)?id:
      data.sources.some(row=>row.id===data.active?.source_id)?data.active.source_id:data.sources[0]?.id||'');
    setPolicyId(id=>id || (activeStatus(data.active?.status)?data.active.policy.id:data.policies[0]?.id) || '');
    if(data.active) setSize(data.active.person_size);
  };
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    let disposed=false, polling=false;
    const poll=async()=>{
      if(polling) return; polling=true;
      const version=runVersion.current;
      try{
        const next=await api('/runs/active');
        if(disposed||version!==runVersion.current) return;
        setRun(previous=>previous&&next&&previous.id===next.id&&previous.generation>next.generation?previous:next); setConnected(true);
        if(activeStatus(next?.status)){
          setSourceId(next.source_id);setPolicyId(next.policy.id);setSize(next.person_size);
          if(syncedRun.current!==next.id){
            const data=await api('/bootstrap');
            if(disposed) return;
            setBoot(data);syncedRun.current=next.id;
          }
        }
      }catch{ if(!disposed) setConnected(false); } finally{polling=false;}
    };
    poll(); const timer=setInterval(poll,250); return()=>{disposed=true;clearInterval(timer);};
  },[]);
  useEffect(()=>{
    let disposed=false,polling=false;
    const poll=async()=>{
      if(polling)return;polling=true;
      try{
        const list=await api('/events');if(disposed)return;setEvents(list);
        const fresh=list.filter(item=>!eventIds.current.has(item.id));
        if(initialized.current && fresh.length){
          setToast(`${LABEL[fresh[0].kind]} · ${fresh[0].reason}`);
          if(sound){ const context=new AudioContext(); const oscillator=context.createOscillator(), gain=context.createGain(); oscillator.connect(gain); gain.connect(context.destination); gain.gain.value=0.06; oscillator.frequency.value=660; oscillator.start(); oscillator.stop(context.currentTime+0.15); oscillator.onended=()=>context.close(); }
        }
        eventIds.current=new Set(list.map(item=>item.id)); initialized.current=true;
      }catch{/* Run polling owns the connection indicator. */}finally{polling=false;}
    };
    poll(); const timer=setInterval(poll,1200); return()=>{disposed=true;clearInterval(timer);};
  },[sound]);
  useEffect(()=>{if(page==='runs') api('/runs').then(setRuns).catch(e=>setError(e.message));},[page,run?.status]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),6000);return()=>clearTimeout(timer);},[toast]);
  const perform=async(task)=>{setBusy(true);setError('');try{return await task();}catch(e){setError(e.message);return null;}finally{setBusy(false);}};
  const changeRun=(task)=>{runVersion.current++;return perform(async()=>{try{return await task();}finally{runVersion.current++;}});};
  const startSource=(id,destination='monitor')=>changeRun(async()=>{const value=await api('/runs',{method:'POST',body:JSON.stringify({source_id:id,policy_id:policyId,person_size:size})});setRun(value);setSourceId(value.source_id);setPage(destination);});
  const start=()=>startSource(sourceId);
  const control=(action,position)=>changeRun(async()=>setRun(await api(`/runs/${run.id}/control`,{method:'POST',body:JSON.stringify({action,position})})));
  const openEvent=(id)=>perform(async()=>{setEventDetail(await api(`/events/${id}`));setModal('event');});
  const source=boot?.sources.find(row=>row.id===sourceId);
  const running=activeStatus(run?.status);
  const aligned=connected&&['RUNNING','FINISHED'].includes(run?.status)&&presented?.run_id===run.id&&presented.generation===run.generation;
  const visibleTracks=aligned?presented.tracks:[];
  const visibleScene=aligned?presented.scene:null;
  const currentEvents=events.filter(row=>row.run_id===run?.id);
  const chooseSource=(id)=>{if(running&&id!==run?.source_id){setError('현재 분석을 중지한 뒤 영상을 변경해 주세요.');return;}setSourceId(id);setPage('monitor');};
  return <div className={`app-shell${page==='sources'?' demo-page':''}`}>
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('monitor');}}><span className="brand-icon"><ShieldCheck size={24}/></span><div>ChemiGuard<small>SAFETY OPERATIONS</small></div></a>
      <div className="workspace-label">본선 워크스페이스<span>01</span></div>
      <nav>{NAV.map(({id,title,icon:Icon})=><button key={id} className={page===id?'selected':''} onClick={()=>setPage(id)}><Icon size={19}/><span>{title}</span>{id==='events' && events.some(e=>e.review_status==='OPEN') && <b>{events.filter(e=>e.review_status==='OPEN').length}</b>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="machine"><Cpu size={17}/><span>{boot?.system.gpu_name?.replace('NVIDIA GeForce ','') || 'GPU 확인 중'}</span><i className={boot?.system.gpu_available?'online':'offline'}/></div><div className="connection"><i className={connected?'online':'offline'}/>{connected?'로컬 연결됨':'연결 끊김'}</div><a href="https://github.com/Gi1K/chemiguard" target="_blank" rel="noreferrer">본선 개발 기록<ExternalLink size={13}/></a></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">워크스페이스<ChevronRight size={14}/><strong>{NAV.find(item=>item.id===page).title}</strong></div><div className="topbar-right"><span className="date">2026.10.09</span><IconButton icon={sound?Volume2:VolumeX} title={sound?'알림음 끄기':'알림음 켜기'} onClick={()=>setSound(!sound)}/><span className="operator"><UserRound size={16}/>관제 담당자</span></div></header>
      <main>
        {error && <div className="notice error" role="alert"><AlertTriangle size={18}/><span>{error}</span><IconButton icon={X} title="오류 닫기" onClick={()=>setError('')}/></div>}
        {!connected && <div className="notice error"><AlertTriangle size={18}/>서버 연결이 끊겼습니다. 표시된 관측은 최신 상태가 아닙니다.</div>}
        {!boot ? <Empty icon={LoaderCircle}>관제 환경 불러오는 중</Empty> : <>
          <div className="page-heading"><div><div className="eyebrow">CHEMIGUARD / {page==='monitor'?'LIVE MONITORING':page==='sources'?'DEMO STUDIO':page.toUpperCase()}</div><h1>{NAV.find(item=>item.id===page).title}</h1></div>
            <div className="heading-actions">{page==='monitor' && <Badge value={!connected?'ERROR':run?.status || 'WAITING'}/>}
              {page==='sources' && <span className="demo-library-count"><FileVideo size={17}/><b>{String(boot.sources.length).padStart(2,'0')}</b> VIDEOS</span>}
              {page==='policies' && <button className="button primary" onClick={()=>setModal('policy')}><Plus size={16}/>기준 만들기</button>}
              {page==='references' && <button className="button primary" disabled={running} onClick={()=>setModal('reference')}><ImagePlus size={17}/>사진 등록</button>}
            </div>
          </div>
          {page==='monitor' && <>
            <section className="setup-bar">
              <Field label="시연 영상"><select aria-label="시연 영상" value={sourceId} disabled={running} onChange={e=>setSourceId(e.target.value)}>{boot.sources.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></Field>
              <Field label="작업 기준"><select aria-label="작업 기준" value={policyId} disabled={running} onChange={e=>setPolicyId(e.target.value)}>{boot.policies.map(row=><option key={row.id} value={row.id}>{row.name} · v{row.revision}</option>)}</select></Field>
              <div className="field"><span>사람 감지</span><div className="segmented" role="group" aria-label="사람 감지 모델">{['medium','large'].map(value=><button key={value} aria-label={value==='medium'?'Medium':'Large'} aria-pressed={size===value} disabled={running} className={size===value?'active':''} onClick={()=>setSize(value)}>{value==='medium'?'Medium':'Large'}</button>)}</div></div>
              <button className="button primary start" disabled={busy || running || !sourceId || !policyId} onClick={start}>{busy || run?.status==='LOADING'?<LoaderCircle className="spin" size={18}/>:<Play size={18}/>}시연 시작</button>
            </section>
            {!boot.system.api_configured && <div className="notice warning"><AlertTriangle size={17}/>Luna 연결 대기 · 서버에 OPENAI_API_KEY를 설정해 주세요.</div>}
            <section className="metrics-band"><Metric label="현재 추적" value={visibleTracks.length} unit="명" icon={Users}/><Metric label="이번 실행 사건" value={currentEvents.length} unit="건" icon={Bell}/><Metric label="로컬 처리" value={run?.status==='RUNNING'?run.metrics.processing_fps:'-'} unit="FPS" icon={Activity}/><Metric label="Decisions 응답" value={run?.metrics.api_mean_ms? (run.metrics.api_mean_ms/1000).toFixed(2):'-'} unit="초" icon={Clock3}/></section>
            <div className="monitor-grid">
              <section className="video-section"><div className="section-title"><h2><Video size={18}/>시연 영상</h2><span className="subtle">{run?.id ? '파일 실시간 분석' : source?.case}</span></div>
                <VideoPanel source={source} run={run} connected={connected} control={control} busy={busy} onStart={start} canStart={!running&&Boolean(sourceId&&policyId)} onPresentedFrame={setPresented} presented={presented}/>
                <div className="pipeline-strip"><span><i className={run?.people_state==='RUNNING'?'online':'idle'}/>YOLO26 {size==='large'?'L':'M'} · ByteTrack</span><ChevronRight size={13}/><span><i className={boot.system.api_configured?'online':'offline'}/>Luna Decisions</span><ChevronRight size={13}/><span><i className={currentEvents.length?'online':'idle'}/>사건 · 근거</span></div>
                <div className="scene-line"><div><span className="mini-label">누출 관찰</span><strong>{visibleScene?.error || (visibleScene?.detections?.length?'누출':visibleScene?.processing_state==='RUNNING'?'누출 미관측':'관찰 대기')}</strong></div><Badge value={visibleScene?.processing_state || 'WAITING'}/><span className="subtle">{visibleScene?.detections?.length || 0}개 영역</span></div>
              </section>
              <section className="people-section"><div className="section-title"><h2><Users size={18}/>사람별 관찰</h2><span className="count">{visibleTracks.length}</span></div>
                <div className="people-list">{visibleTracks.length?visibleTracks.map(person=><Person key={person.track_token} person={person} fresh={aligned}/>):<Empty icon={UserRound}>{run?.status==='LOADING'?'모델을 준비하고 있습니다':'관찰 중인 사람이 없습니다'}</Empty>}</div>
                <div className="observation-note"><Eye size={15}/><span>영상 관찰 · 최종 판단은 담당자 확인</span></div>
              </section>
            </div>
            <ProductComparisons tracks={visibleTracks} references={boot.references} siteProducts={boot.site_products} run={run}/>
            <section className="recent-events"><div className="section-title"><h2>이번 실행 사건</h2><button className="text-button" onClick={()=>setPage('events')}>전체 사건<ChevronRight size={15}/></button></div><EventTable events={currentEvents.slice(0,6)} open={openEvent}/></section>
          </>}
          {page==='sources' && <SourcesView sources={boot.sources} choose={chooseSource} run={run} connected={connected} busy={busy} control={control}
            onStart={id=>startSource(id,'sources')} policies={boot.policies} policyId={policyId} setPolicyId={setPolicyId} size={size} setSize={setSize}/>}
          {page==='events' && <EventsView events={events} open={openEvent}/>}
          {page==='policies' && <PoliciesView policies={boot.policies} edit={(value)=>{setEventDetail(value);setModal('policy-edit');}}/>}
          {page==='references' && <><SiteCatalog references={boot.references} onChange={rows=>setBoot(old=>({...old,site_products:rows}))}/><ReferenceSelection references={boot.references} siteProducts={boot.site_products}/></>}
          {page==='runs' && <RunsView runs={runs} showEvents={(id)=>{setPage('events');setToast(`실행 ${id}의 사건은 목록에서 확인할 수 있습니다.`);}}/>}
        </>}
      </main>
      <footer className="footer"><span>ChemiGuard <b>MONITOR</b></span><span>본선 구현 · 사전 자산 사용</span></footer>
    </div>
    {toast && <div className="toast" role="status"><Bell size={17}/><span>{toast}</span><IconButton icon={X} title="알림 닫기" onClick={()=>setToast('')}/></div>}
    {error && modal && <div className="toast error-toast" role="alert"><AlertTriangle size={17}/><span>{error}</span><IconButton icon={X} title="오류 닫기" onClick={()=>setError('')}/></div>}
    {modal==='upload' && <UploadModal onClose={()=>setModal(null)} submit={(form)=>perform(async()=>{const row=await api('/sources',{method:'POST',body:form});await load();setSourceId(row.id);setModal(null);setToast('영상이 등록되었습니다.');})} busy={busy}/>}
    {['policy','policy-edit'].includes(modal) && <PolicyModal initial={modal==='policy-edit'?eventDetail:null} references={boot.references} onClose={()=>setModal(null)} busy={busy} submit={value=>perform(async()=>{const row=await api('/policies',{method:'POST',body:JSON.stringify(value)});await load();setPolicyId(row.id);setModal(null);setToast(`작업 기준 v${row.revision} 저장됨`);})}/>}
    {modal==='reference' && <ReferenceModal onClose={()=>setModal(null)} busy={busy} submit={form=>perform(async()=>{await api('/references',{method:'POST',body:form});await load();setModal(null);setToast('사진과 임베딩이 등록되었습니다. 작업 기준을 새 버전으로 저장해 주세요.');})}/>}
    {modal==='event' && eventDetail && <EventModal detail={eventDetail} onClose={()=>setModal(null)} busy={busy} submit={value=>perform(async()=>{await api(`/events/${eventDetail.event.id}/reviews`,{method:'POST',body:JSON.stringify(value)});setEventDetail(await api(`/events/${eventDetail.event.id}`));setEvents(await api('/events'));setToast('검토 기록이 저장되었습니다.');})}/>}
  </div>;
}

function Metric({label,value,unit,icon:Icon}){return <div className="metric"><div className="metric-label"><Icon size={16}/>{label}</div><div className="metric-number">{value}<span>{unit}</span></div></div>;}
function VideoPanel({source,run,connected,control,busy,onStart,canStart,onPresentedFrame,presented}){
  const [seek,setSeek]=useState(null); const panel=useRef();
  const current=run && run.source_id===source?.id;
  const playback=useNativePlayback(source,current?run:null,connected);
  const {video,position,dimensions,duration}=playback;
  const playing=current&&['RUNNING','PAUSED'].includes(run.status);
  const playTitle=playing?(run.status==='RUNNING'?'일시정지':'재개'):current?'시연 다시 시작':'시연 시작';
  const togglePlayback=()=>{
    if(run?.status!=='RUNNING')video.current?.play().catch(()=>{});
    if(playing)control(run.status==='RUNNING'?'pause':'resume',run.status==='RUNNING'?video.current?.currentTime:undefined);
    else onStart();
  };
  const commitSeek=()=>{if(seek!==null&&playing){control('seek',Math.min(seek,Math.max(0,run.duration_s-0.2)));setSeek(null);}};
  return <div className="video-tool" ref={panel}>
    <VideoStatus sourceId={source?.id} run={run} connected={connected} presented={presented}/>
    <div className="video-stage" style={{aspectRatio:dimensions?`${dimensions[0]}/${dimensions[1]}`:current&&run.source_width?`${run.source_width}/${run.source_height}`:'16/9'}}>
      {source?<video ref={video} key={source.id} src={source.video_url} poster={source.preview_url} aria-label={source.name}
        muted playsInline preload="metadata" onLoadedMetadata={playback.loaded} onWaiting={playback.waiting}
        onPlaying={playback.ready} onCanPlay={playback.ready} onError={playback.failed}/>:<Camera size={48}/>}
      <TrackingOverlay video={video} run={current?run:null} connected={connected} sourceKey={source?.id} onPresentedFrame={onPresentedFrame}/>
      <div className="video-tag"><i className={current&&run.status==='RUNNING'&&connected?'online':'idle'}/>{current?LABEL[run.status]:'시연 원본'}</div>
      <span className="video-time">{timecode(position)}</span>
      {(current&&run.status==='LOADING'||playback.buffering)&&<div className="video-loading"><LoaderCircle size={27} className="spin"/><span>{run?.status==='LOADING'?'분석 모델 준비 중':'영상 불러오는 중'}</span></div>}
      {(playback.mediaError||current&&run.error)&&<div className="video-error"><AlertTriangle size={18}/><span>{playback.mediaError||run.error}</span>{playback.mediaError&&<IconButton icon={RotateCcw} title="영상 다시 불러오기" onClick={playback.retry}/>}</div>}
    </div>
    <div className="video-controls"><IconButton icon={current&&run.status==='RUNNING'?Pause:Play} title={playTitle} disabled={busy||(!playing&&!canStart)} onClick={togglePlayback}/><IconButton icon={Square} title="분석 중지" disabled={!current||!activeStatus(run.status)||busy} onClick={()=>control('stop')}/><span className="duration">{timecode(position)}</span><input aria-label="영상 위치" type="range" min="0" max={(current?run.duration_s:duration)||1} step="0.1" value={seek??(current?position:0)} disabled={!playing||busy} onChange={e=>setSeek(Number(e.target.value))} onPointerUp={commitSeek} onKeyUp={commitSeek}/><span className="duration">{timecode(current?run.duration_s:duration)}</span><IconButton icon={Maximize2} title="전체 화면" onClick={()=>{if(document.fullscreenElement)document.exitFullscreen();else panel.current.requestFullscreen?.();}}/></div>
  </div>;
}
function Box({box,width,height,color,label}){return <div className={`bounding-box ${color}`} style={{left:`${box[0]/width*100}%`,top:`${box[1]/height*100}%`,width:`${(box[2]-box[0])/width*100}%`,height:`${(box[3]-box[1])/height*100}%`}}><span>{label}</span></div>;}
function Person({person,fresh}){
  const wearing=fresh?person.wearing:'UNKNOWN';
  const alarm=person.active_violations?.length>0||Object.keys(person.product_alerts||{}).length>0;
  return <article className="person"><div className="person-head"><span className="person-id"><UserRound size={16}/>PERSON <b>{String(person.track_id).padStart(2,'0')}</b></span><Badge value={alarm?'VIOLATION_SUSPECTED':wearing}>{observationLabel({...person,wearing})}</Badge></div>
    <div className="parts">{Object.entries(PARTS).filter(([name])=>!['hood','closure','respirator'].includes(name)||name in person.parts).map(([name,label])=><div key={name}><span>{label}</span><b className={tone(fresh?person.parts[name]:'UNKNOWN')}>{fresh?(LABEL[person.parts[name]]||'-'):'-'}</b></div>)}</div>
    <div className="person-reason">{fresh?person.reason:'유효한 최신 관측 없음'}</div>
    {fresh&&person.wearing==='VISIBLE_WORN'&&<div className="person-reason">전체 필수 부위 · 미확인 항목 있음</div>}
    {person.active_violations?.length>0&&<div className="person-reason red">미해제 경보 · {person.active_violations.join(' · ')}</div>}
    <ProductCheck check={fresh?person.product_check:{state:'STALE'}} alerts={person.product_alerts}/>
    <div className="person-meta"><Badge value={fresh?person.processing_state:'STALE'}/><span>{person.pending?'관찰 요청 중':person.confirmed?'연속 2회 관찰':['WORN','VISIBLE_WORN'].includes(wearing)?'착용 관찰 · 재확인 중':'합의 대기'}</span>{person.latency_ms!=null&&<span>{(person.latency_ms/1000).toFixed(2)}s</span>}</div>
    <div className="identity-line"><span>{person.product_check?.primary_backend==='decisions'?'Decisions 제품':'등록 제품 외형'}</span>{person.product_check?.primary_backend==='decisions'?<small>{fresh&&person.product_check.candidate?`${person.product_check.candidate.name} ${person.product_check.candidate.designation_basis==='site_standard_color_and_form'?'등록 표준':'계열 후보'}`:'제품 미확정'}</small>:person.identity.candidates?.length?<><strong>{person.identity.candidates[0].name}</strong><small>후보 · 미확정</small></>:<small>{person.identity.reason||'참고 사진 없음'}</small>}</div>
  </article>;
}

function EventTable({events,open}){return events.length?<div className="table-wrap"><table><thead><tr><th>영상 시각</th><th>사건</th><th>대상 / 영상</th><th>사유</th><th>검토</th><th/></tr></thead><tbody>{events.map(event=><tr key={event.id} onClick={()=>open(event.id)} tabIndex="0" onKeyDown={e=>e.key==='Enter'&&open(event.id)}><td className="mono">{timecode(event.source_time_s)}</td><td><Badge value={event.kind}/></td><td><span>{event.track_id!=null?`사람 #${event.track_id}`:'장면 전체'}</span><small className="cell-small">{event.source_name}</small></td><td className="reason-cell">{event.reason}</td><td><Badge value={event.review_status}/></td><td><ChevronRight size={16}/></td></tr>)}</tbody></table></div>:<Empty icon={Bell}>아직 기록된 사건이 없습니다</Empty>;}
function EventsView({events,open}){
  const [filter,setFilter]=useState('all');const list=events.filter(row=>filter==='all'||row.review_status===filter);
  return <><div className="view-toolbar"><div className="tabs">{[['all','전체'],['OPEN','미검토'],['ACKNOWLEDGED','확인'],['DISMISSED','반려'],['DEFERRED','보류']].map(([id,name])=><button key={id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{name}<span>{events.filter(row=>id==='all'||row.review_status===id).length}</span></button>)}</div><span className="subtle">원본 관찰 + 담당자 검토 이력</span></div><EventTable events={list} open={open}/></>;
}
function ReferenceSelection({references,siteProducts}){
  const selected=siteReferences(references,siteProducts);
  const ids=new Set(selected.map(row=>row.id));
  const archived=references.filter(row=>!ids.has(row.id));
  return <><div className="section-title"><h2>비교 사진</h2><span className="subtle">{selected.length}장</span></div><ReferencesView references={selected}/>{archived.length>0&&<details className="reference-archive"><summary>비교 제외 사진 · {archived.length}장 보관</summary><ReferencesView references={archived}/></details>}</>;
}

function SourcesView({sources,choose,run,connected,busy,control,onStart,policies,policyId,setPolicyId,size,setSize}){
  const sections=useRef(new Map());
  const indexRef=useRef(null);
  const [visibleSource,setVisibleSource]=useState(sources[0]?.id);
  const running=activeStatus(run?.status);
  useEffect(()=>{
    let frame=0;
    const update=()=>{
      frame=0;
      const boundary=(indexRef.current?.offsetHeight||0)+48;
      let current=sources[0]?.id;
      for(const source of sources){
        if((sections.current.get(source.id)?.getBoundingClientRect().top??Infinity)<=boundary) current=source.id;
      }
      if(window.scrollY+window.innerHeight>=document.documentElement.scrollHeight-2) current=sources.at(-1)?.id;
      setVisibleSource(current);
    };
    const schedule=()=>{if(!frame)frame=requestAnimationFrame(update);};
    update();window.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('scroll',schedule);window.removeEventListener('resize',schedule);};
  },[sources]);
  const jump=id=>sections.current.get(id)?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  return <div className="demo-showcase">
    <div className="demo-settings">
      <Field label="작업 기준"><select aria-label="시연 작업 기준" value={policyId} disabled={running||busy} onChange={e=>setPolicyId(e.target.value)}>{policies.map(row=><option key={row.id} value={row.id}>{row.name} · v{row.revision}</option>)}</select></Field>
      <div className="field"><span>사람 감지</span><div className="segmented" role="group" aria-label="시연 사람 감지 모델">{['medium','large'].map(value=><button key={value} aria-label={value==='medium'?'Medium':'Large'} aria-pressed={size===value} disabled={running||busy} className={size===value?'active':''} onClick={()=>setSize(value)}>{value==='medium'?'Medium':'Large'}</button>)}</div></div>
      <span className="demo-run-state"><i className={!connected?'offline':running?'online':'idle'}/>{!connected?'연결 끊김':running?`${sources.find(row=>row.id===run.source_id)?.name||'영상'} · ${LABEL[run.status]}`:'시연 대기'}</span>
    </div>
    <nav className="demo-index" ref={indexRef} aria-label="시연 영상 바로가기">{sources.map((source,index)=><button key={source.id} onClick={()=>jump(source.id)} aria-current={visibleSource===source.id?'location':undefined} aria-label={`${source.name} 영상으로 이동`}>
      <img src={source.preview_url} alt=""/><span><small>VIDEO {String(index+1).padStart(2,'0')}</small>{source.name}</span><ChevronRight size={16}/>
    </button>)}</nav>
    {sources.map((source,index)=><section className="demo-section" id={`demo-${source.id}`} key={source.id} aria-labelledby={`demo-title-${source.id}`}
      ref={element=>{if(element)sections.current.set(source.id,element);else sections.current.delete(source.id);}}>
      <DemoVideo source={source} index={index} run={run} connected={connected} busy={busy} control={control} onStart={()=>onStart(source.id)} canStart={!running&&Boolean(policyId)&&connected} choose={()=>choose(source.id)}/>
    </section>)}
    {!sources.length&&<Empty icon={FileVideo}>등록된 시연 영상이 없습니다</Empty>}
  </div>;
}
function DemoVideo({source,index,run,connected,busy,control,onStart,canStart,choose}){
  const [presented,setPresented]=useState(null);
  const current=run?.source_id===source.id?run:null;
  const otherRunning=activeStatus(run?.status)&&!current;
  return <>
    <header className="demo-section-heading"><div className="demo-heading-title"><span className="demo-number">{String(index+1).padStart(2,'0')}</span><div><small><Video size={13}/>{source.case}</small><h2 id={`demo-title-${source.id}`}>{source.name}</h2></div></div>
      <div className="demo-actions"><Badge value={current?.status||'WAITING'}>{otherRunning?'다른 영상 시연 중':undefined}</Badge>
        <IconButton icon={Radio} title={`${source.name} 관제에서 열기`} disabled={otherRunning||busy} onClick={choose}/>
        <button className="button primary" disabled={!canStart||busy} onClick={onStart}>{current?.status==='LOADING'?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}시연 시작</button>
      </div>
    </header>
    <VideoPanel source={source} run={current} connected={connected} control={control} busy={busy} onStart={onStart} canStart={canStart} onPresentedFrame={setPresented} presented={presented}/>
  </>;
}
function PoliciesView({policies,edit}){return <div className="policy-list">{policies.map(row=><article key={row.id} className="policy-row"><div className="policy-symbol"><SlidersHorizontal size={22}/></div><div className="policy-description"><h3>{row.name}<span>v{row.revision}</span></h3><p>{row.zone_id}</p><div className="policy-tags"><span>{row.wearing_assessment==='visible_regions'?'보이는 범위 관찰':'전체 부위 확인'}</span>{row.coverall_required&&<span>화학복 필수</span>}{row.hood_required&&<span>후드 필수</span>}{row.respirator_required&&<span>전면형 방독면 필수</span>}{row.closure_required&&<span>여밈 필수</span>}{row.identity_required&&<span>등록 제품 확인</span>}{row.release_monitoring&&<span>장면 관찰</span>}</div></div><div className="policy-version"><small>사진 revision {row.reference_revision}</small><span>{date(row.created_at)}</span></div><button className="button" onClick={()=>edit(row)}><Settings2 size={16}/>새 버전</button></article>)}</div>;}
function ReferencesView({references}){return references.length?<div className="reference-grid">{references.map(row=><article className="reference-item" key={row.id}><div className="reference-picture"><img src={row.crop_url} alt={row.product_name}/></div><div><small>{row.product_id} · {row.view}</small><h3>{row.product_name}</h3><p>{row.source}</p><div className="reference-details"><span>몸통 영역</span><span>revision {row.revision}</span><Badge value="RUNNING">임베딩 완료</Badge></div></div></article>)}</div>:<Empty icon={ImagePlus}>등록된 제품 참고 사진이 없습니다</Empty>;}
function RunsView({runs}){return runs.length?<div className="table-wrap"><table><thead><tr><th>실행</th><th>영상</th><th>모델</th><th>기준</th><th>상태</th><th>사건</th><th/></tr></thead><tbody>{runs.map(row=><tr key={row.id}><td>{date(row.created_at)}<small className="cell-small mono">{row.id.slice(-8)}</small></td><td>{row.source.name}</td><td>YOLO26 {row.person_size==='large'?'L':'M'}</td><td>{row.policy.name} · v{row.policy.revision}</td><td><Badge value={row.status}/></td><td>{row.metrics?.events||0}</td><td><a className="icon-button" aria-label="실행 JSON 다운로드" title="실행 JSON 다운로드" href={`/api/runs/${row.id}/export`}><ArrowDownToLine size={18}/></a></td></tr>)}</tbody></table></div>:<Empty icon={History}>아직 실행 이력이 없습니다</Empty>;}

function UploadModal({onClose,submit,busy}){return <Modal title="시연 영상 등록" onClose={onClose}><form onSubmit={e=>{e.preventDefault();submit(new FormData(e.currentTarget));}}><div className="form-grid"><Field label="영상 파일" wide><input name="video" type="file" accept="video/*,.mkv" required/></Field><Field label="출처 / 촬영자" wide><input name="source" required placeholder="직접 촬영 또는 원출처" maxLength={1000}/></Field></div><div className="modal-actions"><button type="button" className="button" onClick={onClose}>취소</button><button className="button primary" disabled={busy}>{busy?<LoaderCircle size={16} className="spin"/>:<Plus size={16}/>}등록</button></div></form></Modal>;}
function PolicyModal({initial,references,onClose,submit,busy}){
  const [value,setValue]=useState({name:initial?.name||'',zone_id:initial?.zone_id||'',coverall_required:initial?.coverall_required??true,hood_required:initial?.hood_required??true,respirator_required:initial?.respirator_required??!initial,closure_required:initial?.closure_required??true,closure_location:initial?.closure_location||'앞 중앙 지퍼 및 덮개',closure_assessment:'external_appearance',ppe_scope:'camera_view',wearing_assessment:initial?.wearing_assessment||(initial?'all_required':'visible_regions'),identity_required:initial?.identity_required??false,required_product_id:initial?.required_product_id||null,release_monitoring:initial?.release_monitoring??true,scene_roi:initial?.scene_roi||[0,0,1,1]});
  const set=(key,val)=>setValue(old=>({...old,...(key==='coverall_required'&&!val?{hood_required:false,respirator_required:false,closure_required:false,identity_required:false}:{}),...(val&&['hood_required','respirator_required','closure_required','identity_required'].includes(key)?{coverall_required:true}:{}),[key]:val}));
  const products=Object.values(Object.fromEntries(references.map(row=>[row.product_id,row])));
  return <Modal title={initial?'작업 기준 새 버전':'작업 기준 만들기'} onClose={onClose}><form onSubmit={e=>{e.preventDefault();submit(value);}}><div className="form-grid"><Field label="작업명"><input value={value.name} onChange={e=>set('name',e.target.value)} required maxLength={100}/></Field><Field label="감시 구역"><input value={value.zone_id} onChange={e=>set('zone_id',e.target.value)} required maxLength={100}/></Field><Field label="착용 관찰 기준" wide><select value={value.wearing_assessment} onChange={e=>set('wearing_assessment',e.target.value)}><option value="visible_regions">보이는 범위 착용 · 전체 충족 별도</option><option value="all_required">전체 필수 부위 확인</option></select></Field><div className="check-list wide">{[['coverall_required','화학보호복 필수'],['hood_required','후드 착용 필수'],['respirator_required','전면형 방독면 필수'],['closure_required','여밈 닫힘 필수'],['identity_required','등록 제품 확인 필수'],['release_monitoring','누출 관찰']].map(([key,label])=><label key={key}><input type="checkbox" checked={value[key]} onChange={e=>set(key,e.target.checked)}/><span>{label}</span></label>)}</div>{value.closure_required&&<Field label="여밈 위치" wide><input value={value.closure_location==='unknown'?'':value.closure_location} placeholder="예: 앞 중앙 지퍼와 덮개" required onChange={e=>set('closure_location',e.target.value)}/></Field>}{value.identity_required&&<Field label="등록 제품" wide><select required value={value.required_product_id||''} onChange={e=>set('required_product_id',e.target.value)}><option value="">제품 선택</option>{products.map(row=><option value={row.product_id} key={row.product_id}>{row.product_name}</option>)}</select></Field>}{value.release_monitoring&&<div className="wide"><span className="input-label">장면 감시 영역 (%)</span><div className="roi-fields">{['왼쪽','위쪽','오른쪽','아래쪽'].map((label,i)=><Field key={label} label={label}><input type="number" min="0" max="100" step="1" value={Math.round(value.scene_roi[i]*100)} onChange={e=>set('scene_roi',value.scene_roi.map((v,j)=>i===j?Number(e.target.value)/100:v))}/></Field>)}</div></div>}</div><div className="modal-actions"><button type="button" className="button" onClick={onClose}>취소</button><button className="button primary" disabled={busy}><Check size={16}/>기준 저장</button></div></form></Modal>;
}

function ReferenceModal({onClose,submit,busy}){
  const [file,setFile]=useState(null),[preview,setPreview]=useState(''),[dimensions,setDimensions]=useState([1,1]),[box,setBox]=useState(null);
  const drag=useRef(null),surface=useRef(null);
  useEffect(()=>{if(!file)return;const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
  const position=e=>{const rect=surface.current.getBoundingClientRect();return [Math.max(0,Math.min(dimensions[0],Math.round((e.clientX-rect.left)/rect.width*dimensions[0]))),Math.max(0,Math.min(dimensions[1],Math.round((e.clientY-rect.top)/rect.height*dimensions[1])))];};
  return <Modal title="제품 참고 사진 등록" onClose={onClose} wide><form onSubmit={e=>{e.preventDefault();if(!file||!box)return;const form=new FormData(e.currentTarget);const metadata={product_id:form.get('product_id'),product_name:form.get('product_name'),source:form.get('source'),usage_scope:form.get('usage_scope'),view:form.get('view'),region:'torso',bbox:box};const upload=new FormData();upload.append('image',file);upload.append('metadata',JSON.stringify(metadata));submit(upload);}}><div className="reference-form"><div><Field label="참고 사진"><input type="file" accept="image/*" required onChange={e=>{setFile(e.target.files[0]);setBox(null);}}/></Field>{preview?<><div className="crop-surface" ref={surface} onPointerDown={e=>{drag.current=position(e);e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!drag.current)return;const p=position(e);setBox([Math.min(p[0],drag.current[0]),Math.min(p[1],drag.current[1]),Math.max(p[0],drag.current[0]),Math.max(p[1],drag.current[1])]);}} onPointerUp={()=>{drag.current=null;}}><img src={preview} alt="등록할 참고 사진" draggable="false" onLoad={e=>{const w=e.target.naturalWidth,h=e.target.naturalHeight;setDimensions([w,h]);setBox([Math.round(w*.2),Math.round(h*.2),Math.round(w*.8),Math.round(h*.65)]);}}/>{box&&<Box box={box} width={dimensions[0]} height={dimensions[1]} color="green" label="몸통 영역"/>}</div><div className="crop-dimensions">{box?.join(', ')} px</div></>:<Empty icon={ImagePlus}>참고 사진 없음</Empty>}</div><div className="form-grid"><Field label="제품 ID"><input name="product_id" pattern="[A-Za-z0-9_-]+" placeholder="SUIT-001" required/></Field><Field label="제품명"><input name="product_name" required/></Field><Field label="촬영 방향"><select name="view"><option value="front">앞</option><option value="back">뒤</option><option value="side">옆</option><option value="other">기타</option></select></Field><Field label="비교 영역"><input value="몸통" readOnly/></Field><Field label="사진 출처" wide><input name="source" required/></Field><Field label="사용 범위" wide><input name="usage_scope" required defaultValue="허용된 해커톤 로컬 시연"/></Field></div></div><div className="modal-actions"><button className="button" type="button" onClick={onClose}>취소</button><button className="button primary" disabled={busy||!box||!file}>{busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}사진 · 임베딩 등록</button></div></form></Modal>;
}
function EventModal({detail,onClose,submit,busy}){
  const {event,observation,reviews,run}=detail;
  const [action,setAction]=useState('ACKNOWLEDGED');
  const result=observation.result;
  return <Modal title="사건 근거 · 담당자 검토" onClose={onClose} wide><div className="event-summary"><Badge value={event.kind}/><strong>{event.reason}</strong><span>{timecode(event.source_time_s)} · {event.track_id!=null?`사람 #${event.track_id}`:'장면 전체'}</span><a className="icon-button" title="사건 JSON 다운로드" aria-label="사건 JSON 다운로드" href={`/api/events/${event.id}/export`}><ArrowDownToLine size={18}/></a></div>
    <div className="evidence-layout"><div className="evidence-images"><figure><img src={observation.images.frame} alt="관측 시점의 원본 맥락"/><figcaption>관측 원본 · {timecode(observation.source_time_s)} · 프레임 {observation.source_frame}</figcaption></figure><div className="crop-grid">{Object.entries(observation.images).filter(([name])=>name!=='frame').map(([name,url])=><figure key={name}><img src={url} alt={`${name} 근거 crop`}/><figcaption>{{person:'사람 전체',torso:'몸통',legs:'다리',head:'머리·안면',release:'누출'}[name]||name}</figcaption></figure>)}</div></div>
      <div className="review-panel"><h3>관찰 정보</h3><dl><dt>입력 영상</dt><dd>{event.source_name}</dd><dt>작업 기준</dt><dd>{run.policy.name} · v{event.policy_revision}</dd><dt>관찰 결과</dt><dd>{LABEL[result.wearing]||'누출'}</dd><dt>관측 시각</dt><dd>{date(observation.created_at)}</dd><dt>API 응답</dt><dd>{result.latency_ms!=null?`${(result.latency_ms/1000).toFixed(3)}초`:'로컬 분석'}</dd></dl>
      <ProductCheck check={result.product_check}/>
      <h3>담당자 검토</h3><form onSubmit={e=>{e.preventDefault();const form=new FormData(e.currentTarget);submit({reviewer:form.get('reviewer'),action,note:form.get('note')});}}><div className="review-actions">{[['ACKNOWLEDGED','확인',CheckCircle2],['DISMISSED','반려',XCircle],['DEFERRED','보류',Clock3]].map(([id,label,Icon])=><button type="button" key={id} className={action===id?'active':''} onClick={()=>setAction(id)}><Icon size={16}/>{label}</button>)}</div><Field label="담당자"><input name="reviewer" required defaultValue={reviews[0]?.reviewer||''}/></Field><Field label="검토 의견"><textarea name="note" required rows="3" maxLength={2000}/></Field><button className="button primary full" disabled={busy}><Check size={16}/>검토 기록 저장</button></form>
      <div className="review-history"><h3>검토 이력 <span>{reviews.length}</span></h3>{reviews.length?reviews.map(review=><div className="review-record" key={review.id}><div><Badge value={review.action}/><strong>{review.reviewer}</strong></div><p>{review.note}</p><small>{date(review.created_at)}</small></div>):<p className="subtle">아직 검토 기록이 없습니다.</p>}</div></div></div>
      <details className="raw-result"><summary>원시 관찰 · 요청 추적 정보</summary><pre>{JSON.stringify({observation,supporting_observations:detail.supporting_observations},null,2)}</pre></details>
  </Modal>;
}

createRoot(document.getElementById('root')).render(<App/>);
