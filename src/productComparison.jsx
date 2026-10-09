import React, {useEffect, useState} from 'react';
import {AlertTriangle, ExternalLink, ScanSearch, Shirt} from 'lucide-react';
import './productComparison.css';
import {COLORS,siteReferences} from './siteCatalog';

const score = value => Number.isFinite(value) ? value.toFixed(3) : '-';
const stamp = value => `${Number(value || 0).toFixed(2)}s`;

export function ProductCheck({check={},alerts=check.active_alerts||{}}) {
  const alarm=Object.keys(alerts).length>0;
  const color=COLORS[check.observed_color]?.[0]||({no_coverall:'보호복 미관찰',not_visible:'안 보임',uncertain:'판독 불가'}[check.observed_color])||'관찰 대기';
  const standard=check.candidate?.designation_basis==='site_standard_color_and_form';
  const title=alarm?'등록 보호복 불일치 의심':check.state==='MISMATCH'?'미해당 · 불일치 재확인 중':check.state==='STALE'?'제품 관측 만료':check.state==='NOT_WORN'?'미착용 관찰 · 제품 판정 제외':check.state==='CANDIDATE'?(standard?'현장 표준 분류':'등록 계열 후보'):'제품 판단 불가';
  if(!check.version&&!alarm&&check.state!=='STALE') return null;
  return <div className={`product-check ${alarm?'product-alarm':''}`} role={alarm?'alert':undefined}>
    <strong>{alarm&&<AlertTriangle size={16}/>} {title}{alarm&&<span>긴급</span>}</strong>
    {check.primary_backend==='decisions'&&<p>Luna Decisions{check.candidate?` · ${check.candidate.name}${standard?' 등록 표준':' 계열 후보'}`:''}{check.decision_latency_ms>0?` · ${(check.decision_latency_ms/1000).toFixed(2)}s`:''}</p>}
    <p>{check.state==='STALE'?'최신 관측 없음':`관찰 색상 ${color} · 등록 ${(check.registered_colors||[]).map(value=>COLORS[value]?.[0]||value).join(' / ')||'없음'}`}</p>
    {check.source_time_s!=null&&<p>제품 관측 {stamp(check.source_time_s)}</p>}
    <p>{alarm?Object.values(alerts).join(' · '):check.reason}</p>
  </div>;
}

function ProductFacts({product,siteStandard=false}) {
  if (!product) return <p className="product-warning">제품 자료 미등록 · 성능 미확인</p>;
  return <>
    <dl className="product-facts">
      <dt>{siteStandard?'등록 표준 제품':'참고 모델'}</dt><dd>{product.manufacturer} · {product.name}<small>{product.model_code} · {siteStandard?'현장 등록 정보 · 실물 모델 확인 아님':'착용 모델 미확정'}</small></dd>
      <dt>보호복 유형</dt><dd>Type {product.types.join(' / ')}</dd>
      {product.chemical_tests.map(test=><React.Fragment key={test.category}>
        <dt>{test.category==='산'?'내산 관련 시험':'내염기 관련 시험'}</dt>
        <dd>{test.chemical} {test.concentration}<small>침투 {test.penetration} · 반발 {test.repellency} · {test.method}</small></dd>
      </React.Fragment>)}
      <dt>작업 적합성</dt><dd className="product-warning">{product.suitability_reason}</dd>
    </dl>
    <p className="product-limit">{product.limitation}</p>
    <a className="product-source" href={product.source_url} target="_blank" rel="noreferrer">{product.source_title}<ExternalLink size={13}/><span>{product.verified_on}</span></a>
  </>;
}

function Comparison({person,primaryBackend}) {
  const [selection,setSelection]=useState('');
  const matching=person.identity || {};
  const candidates=matching.candidates || [];
  const candidate=candidates.find(row=>row.product_id===selection) || candidates[0];
  const check=person.product_check||(primaryBackend==='decisions'?{primary_backend:'decisions',version:'pending',state:'WAITING',reason:'유효한 제품 관찰 없음'}:{});
  const primary=check.primary_backend==='decisions';
  return <article className="product-comparison">
    <header><h3>사람 #{person.track_id}{person.saved_comparison&&<small>저장된 관측 · 실시간 아님</small>}</h3><span className="product-warning">{primary?'Luna Decisions · 제품 미확정':matching.ambiguous?'계열 구분 보류':'외형 후보 · 모델 미확정'}</span></header>
    <ProductCheck check={check} alerts={person.product_alerts}/>
    {primary&&<>
      <div className="product-visuals">
        {check.query_url&&<figure><img src={check.query_url} alt={`사람 ${person.track_id} Decisions 비교 몸통`}/><figcaption>관측 {stamp(check.source_time_s)}</figcaption></figure>}
        {check.candidate&&<figure><img src={check.candidate.reference_url} alt={`${check.candidate.name} 등록 사진`}/><figcaption>등록 참고</figcaption></figure>}
      </div>
      {check.candidate&&<ProductFacts product={check.candidate.product} siteStandard={check.candidate.designation_basis==='site_standard_color_and_form'}/>}
    </>}
    <details className="supporting-comparison" open={primary?undefined:true}>
      <summary>{primary?'SigLIP2 보조 유사도':'SigLIP2 외형 비교'}</summary>
    {!candidate?<p className="product-empty">{matching.reason || '몸통 사진 비교 대기'}</p>:<>
      <div className="product-visuals">
        <figure><img src={matching.query_url} alt={`사람 ${person.track_id} 비교 입력 몸통`}/><figcaption>관측 {stamp(matching.source_time_s)}</figcaption></figure>
        <figure><img src={candidate.reference_url} alt={`${candidate.name} 등록 몸통 사진`}/><figcaption>등록 제품 사진</figcaption></figure>
        <div className="product-candidate">
          <label htmlFor={`product-${person.track_token}`}>보조 외형 후보</label>
          <select id={`product-${person.track_token}`} value={candidate.product_id} onChange={e=>setSelection(e.target.value)}>
            {candidates.map((row,index)=><option key={row.product_id} value={row.product_id}>{index+1}. {row.name}</option>)}
          </select>
          <strong>{score(candidate.score)}<small>코사인 유사도</small></strong>
          <p>상위 최대 2장 평균 · 등록 {candidate.reference_count}장</p>
        </div>
      </div>
      <ol className="product-ranking">{candidates.map(row=><li key={row.product_id}><span>{row.name}</span><b>{score(row.score)}</b></li>)}</ol>
      <div className="product-score-note">1·2위 차이 {score(matching.gap)} · 확률/정확도 아님 · 비교 {matching.product_count}종</div>
      {matching.outside_candidate&&<p className="product-score-note">등록 외 대조 · {matching.outside_candidate.name} {score(matching.outside_candidate.score)} · 등록 1위 대비 {score(matching.outside_gap)}</p>}
      <div className="product-site-use">{candidate.site_assignments?.length?candidate.site_assignments.map(row=><p key={row.id}><i style={{background:COLORS[row.color]?.[1]}}/>{row.registration_mode==='color'?`${COLORS[row.color]?.[0]} 대표 · 용도·형식 미지정`:`현장 지정 · ${row.purpose_label} · ${row.protection_type} · ${COLORS[row.color]?.[0]}`}</p>):<p>현장 용도 미등록 · 참고 제품 사진 비교</p>}</div>
      {!primary&&<ProductFacts product={candidate.product}/>}
    </>}
    </details>
  </article>;
}

export function ProductComparisons({tracks,references,siteProducts=[],run}) {
  const [history,setHistory]=useState(null),[error,setError]=useState('');
  const savedMode=run&&['PAUSED','FINISHED','STOPPED','ERROR','INTERRUPTED'].includes(run.status);
  useEffect(()=>{
    let disposed=false;
    setHistory(null);setError('');
    if(savedMode) fetch(`/api/runs/${run.id}/identity`).then(async response=>{
      if(!response.ok) throw new Error('저장된 비교 조회 실패');
      const rows=await response.json();
      if(!disposed) setHistory({runId:run.id,rows});
    }).catch(e=>{if(!disposed)setError(e.message);});
    return()=>{disposed=true;};
  },[run?.id,run?.status,savedMode]);
  const comparisons=savedMode?(history?.runId===run.id?history.rows:[]):tracks;
  const eligible=siteReferences(references,run?.site_products??siteProducts).filter(row=>!run?.policy||row.revision<=run.policy.reference_revision);
  const products=Object.values(Object.fromEntries(eligible.map(row=>[row.product_id,row])));
  const comparedCount=comparisons.find(person=>person.identity?.product_count!=null)?.identity.product_count??products.length;
  return <section className="product-section">
    <div className="section-title"><h2><ScanSearch size={18}/>착용 제품 외형 비교</h2><span className="subtle">{run?.product_primary_backend==='decisions'||!run?'Luna Decisions · SigLIP2 보조':'SigLIP2'} · {savedMode?'저장 비교':'비교 대상'} {comparedCount}종</span></div>
    {error&&<p className="product-warning">{error}</p>}
    {comparisons.length?<div className="product-comparisons">{comparisons.map(person=><Comparison key={person.track_token} person={person} primaryBackend={run?.product_primary_backend}/>)}</div>:
      <div className="product-library">{products.length?products.map(row=><details key={row.product_id}><summary><img src={row.crop_url} alt={row.product_name}/><span>{row.product_name}<small>등록 제품 정보</small></span></summary><ProductFacts product={row.product}/></details>):<p className="product-empty"><Shirt size={18}/>비교할 제품 사진 미등록</p>}</div>}
  </section>;
}
