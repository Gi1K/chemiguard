import React, {useEffect, useState} from 'react';
import {Check, Pencil, Plus, X} from 'lucide-react';

export const PURPOSES={acid:'내산',alkali:'내염기',acid_alkali:'내산·내염기',other:'기타'};
export const COLORS={white:['흰색','#fff'],yellow:['노랑','#f3d04c'],orange:['주황','#dc874c'],green:['초록','#408f67'],blue:['파랑','#4481b5'],gray:['회색','#939b9e'],black:['검정','#293238'],other:['기타','#ddd']};

export function siteReferences(references,siteProducts=[]) {
  const allowed=new Set(siteProducts.filter(row=>row.enabled).map(row=>row.product_id));
  return references.filter(row=>row.reference_kind==='product_photo'&&(!siteProducts.length||allowed.has(row.product_id)));
}

export function SiteCatalog({references,onChange}) {
  const [rows,setRows]=useState([]),[draft,setDraft]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const products=Object.values(Object.fromEntries(references.filter(row=>row.reference_kind==='product_photo').map(row=>[row.product_id,row])));
  async function load(){const response=await fetch('/api/site-products');if(!response.ok)throw new Error('현장 등록 목록 조회 실패');const value=await response.json();setRows(value);onChange?.(value);}
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  const set=(key,value)=>setDraft(old=>({...old,[key]:value}));
  async function save(event){
    event.preventDefault();setBusy(true);setError('');
    try{
      const payload=Object.fromEntries(['registration_mode','purpose','protection_type','color','product_id','enabled','note'].map(key=>[key,draft[key]]));
      if(payload.registration_mode==='color'){payload.purpose=null;payload.protection_type=null;}
      const response=await fetch('/api/site-products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'등록 정보를 확인해 주세요.');
      await load();setDraft(null);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <section className="site-catalog">
    <div className="section-title"><h2>현장 대표 보호복</h2><button className="button" onClick={()=>{setError('');setDraft({registration_mode:'color',purpose:'',protection_type:'',color:'',product_id:'',enabled:true,note:''});}}><Plus size={15}/>등록</button></div>
    {error&&<p className="product-warning" role="alert">{error}</p>}
    {rows.length?<div className="site-assignments">{rows.map(row=><div className="site-assignment" key={row.id}>
      <i style={{background:COLORS[row.color]?.[1]}} aria-hidden="true"/>
      <img className="site-product-photo" src={products.find(product=>product.product_id===row.product_id)?.crop_url} alt={`${COLORS[row.color]?.[0]} 대표 제품 사진`}/>
      <span><strong>{row.registration_mode==='color'?`${COLORS[row.color]?.[0]} 대표`: `${PURPOSES[row.purpose]} · ${row.protection_type}`}</strong><small>{products.find(product=>product.product_id===row.product_id)?.product?.family || products.find(product=>product.product_id===row.product_id)?.product_name || row.product_id} · v{row.revision} · {row.enabled?'비교 활성':'비교 비활성'}</small>{row.registration_mode==='color'&&<small>용도·형식 미지정 · 제품 계열 비교</small>}</span>
      <button className="icon-button" title={`${COLORS[row.color]?.[0]} 등록 수정`} aria-label={`${COLORS[row.color]?.[0]} 등록 수정`} onClick={()=>{setError('');setDraft({...row,registration_mode:row.registration_mode||'purpose_type'});}}><Pencil size={15}/></button>
    </div>)}</div>:<p className="product-empty">현장 용도·형식·색상 미등록</p>}
    {draft&&<form className="site-form" onSubmit={save}>
      <div className="form-grid">
        <div className="field wide"><span>등록 기준</span><div className="segmented" role="group" aria-label="등록 기준">{[['color','색상별'],['purpose_type','용도·형식별']].map(([key,name])=><button type="button" key={key} disabled={Boolean(draft.id)} aria-pressed={draft.registration_mode===key} className={draft.registration_mode===key?'active':''} onClick={()=>set('registration_mode',key)}>{name}</button>)}</div></div>
        {draft.registration_mode==='purpose_type'&&<><label className="field"><span>현장 지정 용도</span><select required value={draft.purpose||''} disabled={Boolean(draft.id)} onChange={e=>set('purpose',e.target.value)}><option value="">선택</option>{Object.entries(PURPOSES).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
        <label className="field"><span>형식</span><select required value={draft.protection_type||''} disabled={Boolean(draft.id)} onChange={e=>set('protection_type',e.target.value)}><option value="">선택</option>{['Type 1','Type 2','Type 3','Type 4','Type 5','Type 6','기타'].map(value=><option key={value}>{value}</option>)}</select></label></>}
        <label className="field wide"><span>대표 제품</span><select required value={draft.product_id} onChange={e=>set('product_id',e.target.value)}><option value="">등록 사진의 제품 선택</option>{products.map(row=><option value={row.product_id} key={row.product_id}>{row.product_name}</option>)}</select></label>
        <fieldset className="site-colors wide" disabled={Boolean(draft.id)&&draft.registration_mode==='color'}><legend>현장 등록 색상</legend>{Object.entries(COLORS).map(([key,[name,color]])=><label key={key} title={name}><input type="radio" name="site-color" value={key} checked={draft.color===key} onChange={()=>set('color',key)} required/><span style={{background:color}}/><small>{name}</small></label>)}</fieldset>
        <label className="field wide"><span>등록 메모</span><input value={draft.note} maxLength={500} onChange={e=>set('note',e.target.value)}/></label>
        <label className="site-enabled wide"><input type="checkbox" checked={draft.enabled} onChange={e=>set('enabled',e.target.checked)}/>다음 분석의 비교 목록에 포함</label>
      </div>
      <div className="site-form-footer"><span>{draft.registration_mode==='color'?'색상별 대표 제품 1개 · 용도·형식 미지정':'용도·형식별 대표 제품 1개'} · 성능 인증 아님</span><button type="button" className="button" onClick={()=>setDraft(null)}><X size={15}/>취소</button><button className="button primary" disabled={busy}><Check size={15}/>{draft.id?'새 버전 저장':'등록'}</button></div>
    </form>}
  </section>;
}
