import React, {useEffect, useRef, useState} from 'react';
import {AlertTriangle, CheckCircle2, LoaderCircle, Phone, RefreshCw} from 'lucide-react';
import './phoneAlerts.css';

const STATES = {queued:'발신 대기',connecting:'전화 연결 준비',ringing:'벨 울림','in-progress':'통화 중',
  completed:'통화 종료','no-answer':'부재중',busy:'통화 중으로 연결 실패',rejected:'수신 거절',
  failed:'연결 실패',unknown:'결과 확인 필요',interrupted:'중단 · 자동 재발신 안 함',
  canceled:'발신 취소',suppressed:'중복 알림 억제',expired:'오래된 알림 제외',timeout:'통화 시간 제한'};
const WHEN = value => value ? new Date(value).toLocaleString('ko-KR', {hour12:false}) : '—';
const ROLES = {site_safety_manager:'현장 안전관리자',external_119:'사내 119',safety_control_room:'안전 관제실'};
const KINDS = {VIOLATION_SUSPECTED:'미착용',PRODUCT_MISMATCH_SUSPECTED:'보호복 불일치',RELEASE_SUSPECTED:'누출 의심'};
const ERRORS = {recipient_cooldown:'등록번호의 50초 중복 제한',role_cooldown:'당시 개소·역할별 중복 제한',recipient_limit:'당시 등록번호 발신 횟수 제한',
  queue_full:'발신 대기열 가득 참',event_expired:'120초가 지난 사건',event_evidence_invalid_before_dispatch:'관찰 근거가 더 이상 유효하지 않음'};
const FIELDS = {CLAWOPS_API_KEY:'ClawOps API 키',CLAWOPS_ACCOUNT_ID:'ClawOps 계정 ID',
  CLAWOPS_FROM_NUMBER:'발신번호',CLAWOPS_TO_NUMBER:'안전관리자 수신번호',CLAWOPS_ZONE_ID:'담당 개소',OPENAI_API_KEY:'OpenAI API 키'};

const DEMO_STATES = {disarmed:'전화 예약 꺼짐',armed:'다음 시연 · 전화 1통 예약됨',collecting:'미착용·누출 사건 확인 중',
  deciding:'Decisions 연락 판단 중',submitted:'통합 전화 요청됨',incomplete:'두 사건 미확인 · 발신 안 함',
  failed:'연락 판단 또는 발신 준비 실패',canceled:'전화 예약 취소됨',expired:'전화 예약 만료'};

export function DemoPhoneStatus() {
  const [data,setData]=useState(null),[error,setError]=useState(''),[confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false);
  const requestId=useRef(null);
  const local=['127.0.0.1','localhost','[::1]'].includes(window.location.hostname);
  useEffect(()=>{
    let closed=false;
    const load=()=>phoneRequest('/api/phone').then(value=>{if(!closed){setData(value);setError('');}})
      .catch(()=>{if(!closed){setData(null);setError('전화 상태 연결 끊김');}});
    load();const timer=setInterval(load,3000);return()=>{closed=true;clearInterval(timer);};
  },[]);
  const pending=['armed','collecting','deciding'].includes(data?.demo?.status);
  const activeCall=['queued','connecting','ringing','in-progress'].includes(data?.demo?.call_status);
  const change=async action=>{
    setBusy(true);setError('');
    try {
      await phoneRequest('/api/phone/demo',{action,confirm:true,request_id:requestId.current});
      setData(await phoneRequest('/api/phone'));setConfirm(false);
    } catch(e){setError(e.message);} finally{setBusy(false);}
  };
  return <div className="demo-phone-status" aria-live="polite">
    <Phone size={17}/><div><strong>{data?.demo?.per_run_enabled?'매 시연 미착용 · 누출 통합 전화 1통':'미착용 · 누출 통합 안내 1통'}</strong><span>{data?(STATES[data.demo?.call_status]||DEMO_STATES[data.demo?.status]||'전화 상태 확인 중'):'전화 상태 확인 중'}{data?.demo?.per_run_enabled?' · 다음 시연도 자동 연결 · 발신 간격 50초':''}</span></div>
    {local&&<button className="button" disabled={busy||!data?.ready||activeCall} onClick={()=>{requestId.current=crypto.randomUUID();data?.demo?.per_run_enabled?change('disable'):pending?change('cancel'):setConfirm(true);}}>
      <Phone size={15}/>{data?.demo?.per_run_enabled?'매 시연 전화 끄기':pending?'전화 예약 취소':'매 시연 전화 켜기'}</button>}
    {confirm&&<div className="demo-phone-confirm"><span>공개 페이지를 포함해 세 번째 시연을 새로 시작할 때마다 두 사건 확인 후 등록번호에 실제 전화가 연결됩니다. 통화 요금이 발생합니다.</span>
      <button className="button primary" disabled={busy} onClick={()=>change('enable')}>자동 전화 켜기</button><button className="button" disabled={busy} onClick={()=>setConfirm(false)}>취소</button></div>}
    {error&&<p className="phone-error">{error}</p>}
  </div>;
}

export function PhoneCallHistory({calls=[]}) {
  return calls.length ? <div className="phone-history">{calls.map(call=><article key={call.id}>
    <div className="phone-call-title"><strong>{STATES[call.status]||'결과 확인 필요'}</strong><span>{call.recipient}</span></div>
    <p>{call.zone_id} · {call.event_id?call.reason:'연결 시험'}</p>
    <small>{WHEN(call.created_at)} · {ROLES[call.role]||'현장 안전관리자'} · {call.demo_replay?'이전 사건 시연':'시연 전화'}</small>
    {ERRORS[call.error_code]&&<p className="subtle">{ERRORS[call.error_code]}</p>}
    {call.realtime?.session_updated_at ? <p className="phone-realtime">
      OpenAI Realtime 연결 확인 · {call.realtime.model}<br/>
      상대 음성 전달 {((call.realtime.input_audio_bytes||0)/8000).toFixed(1)}초 · AI 음성 생성 {((call.realtime.output_audio_bytes||0)/8000).toFixed(1)}초<br/>
      발화 감지 {call.realtime.speech_turns||0}회 · 응답 완료 {call.realtime.completed_responses||0}회
    </p> : <p className="subtle">OpenAI Realtime 연결 아직 미확인</p>}
    {call.realtime?.failure_code&&<p className="phone-error">Realtime 오류 · 음성 대화가 정상 완료되지 않았습니다.</p>}
    <div className={call.acknowledged_at?'phone-received':'subtle'}>{call.acknowledged_at?<><CheckCircle2 size={15}/>수신 확인 · {WHEN(call.acknowledged_at)}</>:'관리자 수신 확인 미기록'}</div>
    {call.termination_unconfirmed&&<p className="phone-error">종료 요청 결과를 확인하지 못했습니다. ClawOps 통화 기록을 확인해 주세요.</p>}
  </article>)}</div> : <p className="subtle">전화 알림 기록이 없습니다.</p>;
}

async function phoneRequest(url, body) {
  const response=await fetch(url,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'전화 요청을 처리하지 못했습니다.');
  return result;
}

export function ContactRouting({eventId,eventCreatedAt,reviewed=false}) {
  const [data,setData]=useState(null),[phone,setPhone]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [role,setRole]=useState(''),[reason,setReason]=useState(''),[replay,setReplay]=useState(false),[confirm,setConfirm]=useState(false);
  const requestId=useRef(null);
  const accept=value=>setData(old=>(old?.plan?.revision||0)>(value.plan?.revision||0)?old:value);
  useEffect(()=>{
    let disposed=false,polling=false;
    const poll=async()=>{if(polling)return;polling=true;try{
      const [next,status]=await Promise.all([phoneRequest(`/api/events/${eventId}/contact`),phoneRequest('/api/phone')]);
      if(!disposed){accept(next);setPhone(status);}
    }catch(e){if(!disposed)setError(e.message);}finally{polling=false;}};
    poll();const timer=setInterval(poll,3000);return()=>{disposed=true;clearInterval(timer);};
  },[eventId]);
  useEffect(()=>{if(!role&&data?.plan){setRole(data.plan.role);setReason(data.plan.reason);setReplay(data.plan.demo_replay);}},[data,role]);
  const decision=data?.decision,plan=data?.plan;
  const override=role&&decision&&role!==decision.applied_role;
  const matches=plan&&role===plan.role&&reason.trim()===plan.reason&&replay===plan.demo_replay;
  const oldEvent=Date.now()-new Date(eventCreatedAt).getTime()>120000;
  const change=fn=>{fn();setConfirm(false);requestId.current=null;};
  const prepare=async()=>{
    setBusy(true);setError('');setConfirm(false);
    try{
      const next=await phoneRequest(`/api/events/${eventId}/contact`,{role:role||null,reason,demo_replay:replay});
      accept(next);setRole(next.plan.role);setReason(next.plan.reason);setReplay(next.plan.demo_replay);requestId.current=null;
    }catch(e){setError(e.message);}finally{setBusy(false);}
  };
  const call=async()=>{
    setBusy(true);setError('');
    requestId.current ||= crypto.randomUUID();
    try{
      await phoneRequest('/api/phone/calls',{plan_id:plan.id,revision:plan.revision,request_id:requestId.current,confirm:true});
      setConfirm(false);accept(await phoneRequest(`/api/events/${eventId}/contact`));
    }catch(e){setError(e.message);}finally{setBusy(false);}
  };
  return <section className="contact-routing" aria-label="사건 연락 대상">
    <h3>사건 연락 대상</h3>
    {decision?<div className="contact-recommendation"><strong>정책 적용 · {ROLES[decision.applied_role]}</strong>
      <p>{decision.status==='decisions'?`OpenAI Decisions 추천 일치 · ${ROLES[decision.recommended_role]}`:
        decision.recommended_role?`AI 추천 ${ROLES[decision.recommended_role]} · 정책과 달라 지정 규칙 적용`:'정책에 따른 선택 · AI 응답 미확인'}</p>
      {decision.error_code==='policy_mismatch'&&decision.recommended_role===decision.applied_role&&<p>AI 근거 판단이 정책과 달라 지정 규칙을 적용했습니다.</p>}
    </div>:<p className="subtle">사건 근거를 바탕으로 OpenAI Decisions가 연락 대상을 추천합니다.</p>}
    {decision&&<>
      <label className="contact-field">연락 역할<select value={role} disabled={busy||reviewed} onChange={e=>change(()=>setRole(e.target.value))}>
        {Object.entries(ROLES).map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></label>
      {override&&<label className="contact-field">선택 변경 사유<textarea value={reason} disabled={busy} maxLength={500} rows={2} placeholder="이 역할에 연락하는 이유" onChange={e=>change(()=>setReason(e.target.value))}/></label>}
      <label className="contact-replay"><input type="checkbox" checked={replay} disabled={busy||reviewed} onChange={e=>change(()=>setReplay(e.target.checked))}/>이전 사건으로 시연 전화</label>
      {oldEvent&&!replay&&<p className="subtle">120초가 지난 사건입니다. 발신하려면 이전 사건 시연을 선택해 주세요.</p>}
    </>}
    <p className="contact-destination">시연 연결 대상 <strong>{phone?.recipient||'등록번호 확인 중'}</strong><br/>세 역할 모두 현재 등록번호로 연결됩니다.{role==='external_119'&&' 사내 119를 선택해도 실제 119로 전화하지 않습니다.'}</p>
    {reviewed?<p className="notice">검토된 사건은 전화 대상에서 제외됩니다.</p>:<div className="phone-actions">
      <button className="button" disabled={busy||!!(override&&!reason.trim())} onClick={prepare}>{busy?<LoaderCircle size={16} className="spin"/>:<RefreshCw size={16}/>} {decision?'선택 저장':'연락 대상 추천 확인'}</button>
      {decision&&<button className="button primary" disabled={busy||!phone?.ready||!matches||(oldEvent&&!replay)} onClick={()=>setConfirm(true)}><Phone size={16}/>시연 전화</button>}
    </div>}
    {plan&&<small className="contact-plan">계획 v{plan.revision} · {plan.selected_by==='operator'?'담당자 선택':plan.selected_by==='decisions'?'AI 추천과 정책 일치':'지정 정책 적용'}</small>}
    {confirm&&matches&&<div className="phone-confirm" role="group" aria-label="사건 시연 발신 확인"><p><strong>{ROLES[plan.role]}</strong> 역할로 등록번호 <strong>{phone?.recipient}</strong>에 실제 시연 전화를 겁니다. 통화 요금이 발생합니다.{plan.demo_replay&&' 이전 사건의 시연임을 안내합니다.'}{plan.role==='external_119'&&' 실제 긴급 신고가 아닙니다.'}</p>
      <button className="button primary" disabled={busy} onClick={call}>지금 시연 전화 걸기</button><button className="button" disabled={busy} onClick={()=>setConfirm(false)}>취소</button></div>}
    {error&&<p className="notice error" role="alert">{error}</p>}
    <PhoneCallHistory calls={data?.calls||[]}/>
  </section>;
}

export function PhoneAlertsView() {
  const [data,setData]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false), [confirm,setConfirm]=useState(false);
  const [testRole,setTestRole]=useState('site_safety_manager'),[events,setEvents]=useState([]),[eventId,setEventId]=useState('');
  const testRequestId=useRef(null);
  const load=async()=>{
    const response=await fetch('/api/phone');
    if(!response.ok)throw new Error('전화 연결 상태를 불러오지 못했습니다.');
    const value=await response.json();setData(value);return value;
  };
  useEffect(()=>{
    let disposed=false, polling=false;
    const poll=async()=>{if(polling)return;polling=true;try{
      const response=await fetch('/api/phone');if(!response.ok)throw new Error('전화 연결 상태를 불러오지 못했습니다.');
      const next=await response.json();if(!disposed){setData(next);setError('');}
    }catch(e){if(!disposed)setError(e.message);}finally{polling=false;}};
    poll();const timer=setInterval(poll,3000);return()=>{disposed=true;clearInterval(timer);};
  },[]);
  useEffect(()=>{phoneRequest('/api/events').then(rows=>setEvents(rows.filter(row=>KINDS[row.kind]))).catch(e=>setError(e.message));},[]);
  const testCall=async()=>{
    setBusy(true);setError('');
    try{
      const response=await fetch('/api/phone/test',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:testRequestId.current||(testRequestId.current=crypto.randomUUID()),confirm:true,role:testRole})});
      const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'시연 전화 요청에 실패했습니다.');
      setConfirm(false);testRequestId.current=null;await load();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  };
  if(!data)return <p className="subtle">{error||'전화 연결 상태 확인 중…'}</p>;
  return <div className="phone-page">
    <section className="phone-card">
      <div className="phone-card-heading"><Phone size={22}/><div><h2>사건별 전화 알림</h2><p>사건에 맞는 담당 역할을 선택하고 OpenAI 음성으로 안내합니다.</p></div></div>
      <div className="phone-facts"><div><small>음성 인식 · 대화 · 음성 생성</small><strong>OpenAI만 사용</strong></div><div><small>전화망 연결</small><strong>ClawOps</strong></div><div><small>설정 상태</small><strong>{data.ready?'발신 설정 준비됨':data.enabled?'설정 확인 필요':'발신 꺼짐'}</strong></div></div>
      <div className="contact-rules"><div><span>미착용 · 보호복 불일치</span><strong>현장 안전관리자</strong></div><div><span>누출 의심</span><strong>안전 관제실</strong></div><div><span>담당자 직접 선택</span><strong>사내 119 시연</strong></div></div>
      <dl className="phone-settings"><dt>담당 개소</dt><dd>{data.zone_id||'미설정'}</dd><dt>공통 시연번호</dt><dd>{data.recipient||'수신번호 미설정'}</dd><dt>연락 추천</dt><dd>OpenAI Decisions</dd><dt>신규 사건 자동 전화</dt><dd>{data.automatic?'설정 켜짐':'꺼짐'}{!data.ready&&' · 발신 준비 대기'}</dd><dt>중복 알림 간격</dt><dd>등록번호 전체 {data.cooldown_s}초 · 역할이 달라도 동일 적용</dd></dl>
      <p className="notice">현재는 시연 모드입니다. 모든 전화에서 시연임을 먼저 알립니다. 수신 확인은 사건 검토·조치 완료와 별도로 기록합니다.</p>
      {!!data.missing.length&&<p className="notice warning"><AlertTriangle size={17}/>서버 설정 대기: {data.missing.map(key=>FIELDS[key]||key).join(', ')}</p>}
      {!data.dependencies_ready&&<p className="notice warning">전화 연결 구성요소 설치가 필요합니다. 서버 설정 안내를 확인해 주세요.</p>}
      {(data.worker_error||data.routing_error)&&<p className="notice error">전화 처리기를 확인해 주세요. 현재 자동 알림을 정상으로 간주하지 마세요.</p>}
      {error&&<p className="notice error" role="alert">{error}</p>}
      <label className="contact-field">연결 시험 역할<select value={testRole} disabled={busy} onChange={e=>{setTestRole(e.target.value);setConfirm(false);testRequestId.current=null;}}>{Object.entries(ROLES).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <div className="phone-actions"><button className="button primary" disabled={!data.ready||busy||!!data.worker_error} onClick={()=>setConfirm(true)}><Phone size={16}/>연결 시험</button><button className="button" onClick={()=>load().catch(e=>setError(e.message))}><RefreshCw size={16}/>상태 새로고침</button></div>
      {confirm&&<div className="phone-confirm" role="group" aria-label="시연 전화 발신 확인"><p>{ROLES[testRole]} 역할로 등록번호 {data.recipient}에 실제 시연 전화가 걸리고 통화 요금이 발생합니다.{testRole==='external_119'&&' 실제 119 신고가 아닙니다.'}</p><button className="button primary" disabled={busy} onClick={testCall}>{busy?<LoaderCircle size={16} className="spin"/>:<Phone size={16}/>}지금 시연 전화 걸기</button><button className="button" disabled={busy} onClick={()=>setConfirm(false)}>취소</button></div>}
    </section>
    <section className="phone-card"><h2>사건에서 연락하기</h2><p className="subtle">저장된 사건을 선택하거나 사건 상세에서 연락 대상을 지정할 수 있습니다.</p>
      <label className="contact-field">연락할 사건<select value={eventId} onChange={e=>setEventId(e.target.value)}><option value="">사건 선택</option>{events.map(event=><option key={event.id} value={event.id}>{KINDS[event.kind]} · {WHEN(event.created_at)} · {event.reason}</option>)}</select></label>
      {eventId&&<ContactRouting key={eventId} eventId={eventId} eventCreatedAt={events.find(e=>e.id===eventId)?.created_at} reviewed={!!events.find(e=>e.id===eventId)?.review_count}/>}
    </section>
    <section className="phone-card"><h2>전화 알림 이력</h2><p className="subtle">통화별 OpenAI 연결과 음성 처리량을 확인합니다. 음성 생성량은 휴대폰에서 실제로 들었는지까지 확인한 값은 아닙니다.</p><PhoneCallHistory calls={data.calls}/></section>
  </div>;
}
