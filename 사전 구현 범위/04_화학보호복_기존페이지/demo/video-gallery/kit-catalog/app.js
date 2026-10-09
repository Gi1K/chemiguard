"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const colours = {yellow:{label:"노랑",hex:"#f3cb3e"},gray:{label:"회색",hex:"#92989e"},white:{label:"흰색",hex:"#f4f4ef"},green:{label:"초록",hex:"#3d9164"},black:{label:"검정",hex:"#252a30"},black_green:{label:"검정 / 녹색",hex:"#305641"},blue:{label:"파랑",hex:"#4379aa"},transparent:{label:"투명",hex:"#d0e1e7"},silver:{label:"은색",hex:"#b7bdc3"},yellow_black:{label:"노랑 / 검정",hex:"#d6b83b"},yellow_green:{label:"노랑 / 녹색",hex:"#d6b83b"},orange:{label:"주황",hex:"#e58129"},red:{label:"빨강",hex:"#b73638"},unknown:{label:"색상 확인 전",hex:"#bec3c7"}};
const parts = [
  {id:"coverall",category:"chemical_protective_coverall",label:"보호복"},
  {id:"gloves",category:"chemical_gloves",label:"화학장갑"},
  {id:"respirator",category:"respirator",label:"호흡보호구"},
  {id:"eye_protection",category:"eye_protection",label:"눈 보호구"},
  {id:"face_shield",category:"face_shield",label:"안면보호구"},
  {id:"boots",category:"chemical_boots",label:"화학장화"}
];
const draftKeys=["ppe_kit_review_draft_v4","ppe_kit_review_draft_v3","ppe_kit_review_draft_v2","ppe_kit_review_draft_v1"];
let data, ready=false, busy=false, chatSession=null, exportUrl;
let userMessages=[], recommendationEvidence=null, recommendedKits=[], savedKits=[], respiratoryAddons=[], activeKitId=null, activeKitReview=null;
const savedKitsKey="ppe_worksite_kits_v1";
const product = id => data.products.find(p=>p.product_id===id);
const isRespiratoryAccessory = p => p?.category==="respirator"&&["cartridge","filter","holder","accessory","retainer","adapter"].includes(p.item_role);
const colour = p => p?.appearance?.color?.id||"unknown";
const sources = ids => (ids||[]).map(id=>data.product_sources.find(s=>s.id===id)).filter(Boolean);
const searchKey = value => String(value??"").normalize("NFKC").toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,"");
function matchesProductSearch(p,query) {
  const fields=[p.display_name,p.manufacturer,p.identity.model,p.identity.manufacturer_reference,...(p.identity.seller_aliases||[]),parts.find(part=>part.category===p.category)?.label];
  const keys=fields.map(searchKey),words=fields.join(" ").normalize("NFKC").toLocaleLowerCase().split(/[^\p{L}\p{N}]+/u);
  return query.trim().split(/\s+/u).map(searchKey).filter(Boolean).every(token=>/^[a-z]$/.test(token)?words.includes(token):keys.some(key=>key.includes(token)));
}
function link(url,title) {
  try { const u=new URL(url); return u.protocol==="https:" ? `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(title)} ↗</a>` : esc(title); } catch { return esc(title); }
}
function swatch(id) { const c=colours[id]; return c?`<span class="colour-label"><i class="swatch" style="--swatch-colour:${c.hex}" aria-hidden="true"></i>${c.label}</span>`:"색상 확인 전"; }
function photoNote(p) {
  const image=p.images?.find(i=>i.preview_path);
  return image?(image.exact_style_match?"모델 연결 사진 · 판매 옵션 별도 확인":"제품군 대표사진 · 정확 옵션 확인 필요"):"사진 자료 없음";
}
function imageMarkup(p) {
  const i=p.images?.find(x=>x.preview_path);
  return i?`<img class="product-image" src="${esc(i.preview_path)}" alt="${esc(p.display_name)} ${esc(photoNote(p))}" title="${esc(i.image_identity_note||photoNote(p))}" loading="lazy">`:`<div class="image-empty">사진 자료 없음</div>`;
}
function types(p) {
  if(p?.category!=="chemical_protective_coverall") return [];
  const result=[];
  for(const c of p.certifications||[]) for(const t of c.claimed_types||[]) {
    for(const m of String(t).matchAll(/\btype\s*([1-6])(?:[abc]|-b)?\b|([1-6])(?:[abc])?\s*형식/gi)) result.push(Number(m[1]||m[2]));
  }
  return [...new Set(result)].sort();
}
function certText(c) {
  const names={KR_KCs:"국내 KCs",KCs:"국내 KCs",EU_CE:"유럽 CE","EN/CE":"유럽 규격·제조사 표시",DNV_SOLAS:"선박용 DNV / SOLAS · 국내 KCs와 별도",KR_NIER_PPE_CONFORMITY:"유해화학물질 보호구 적합성 문서",NIER:"유해화학물질 보호구 적합성 문서",KR_KCs_SELF_DECLARATION:"자율안전확인 신고",KR_self_declaration:"자율안전확인 신고",KR_self_declaration_reference:"자율안전확인 참조"};
  let s="개별 증빙 확인 전";
  if(c.status==="individual_registry_header_model_match") s="페이지 머리 모델의 공식 기록 확인 · 표 참조번호/판매품 연결 확인 전";
  else if(c.individual_records?.length) s="공식 모델 기록 확인 · 판매 실물 연결 확인 전";
  else if(c.status==="certificate_document_model_match") s="정확 모델의 CE 문서 확인 · 국내 인증과 별도";
  else if(c.status==="manufacturer_hosted_exact_document_read") s="정확 모델의 제조사 게시 DNV 문서 확인 · 현재 상태와 국내 인증은 별도";
  else if(["manufacturer_claim","manufacturer_declared","manufacturer_and_supplier_claim_current_record_not_verified"].includes(c.status)) s="제조사 표시 · 개별 인증 확인 전";
  else if(["supplier_certificate_copy","supplier_certificate_copy_reviewed_current_status_not_verified"].includes(c.status)) s="공급자 인증 사본 확인 · 공식 최신 상태와 판매 실물 연결 확인 전";
  else if(c.status==="manufacturer_certificate_copy") s="제조사 인증 사본 확인 · 공식 최신 상태와 판매 실물 연결 확인 전";
  else if(c.status==="manufacturer_catalog_claim") s="제조사 목록 표시 · 개별 인증 확인 전";
  else if(c.status==="supplier_performance_claim_individual_certificate_not_verified") s="공급자 성능 표시 · 개별 인증 확인 전";
  else if(c.status==="historical_document_model_configuration_match_with_literal_conflict") s="과거 구성 문서 확인 · 문언 불일치와 현재 상태 확인 필요";
  else if(c.status==="manufacturer_certification_claim_and_seller_number_only") s="제조사 인증 표시·판매자 번호 · 개별 증명서와 현재 상태 확인 전";
  else if(c.status==="manufacturer_hosted_declaration_document_model_match") s="제조사 게시 개별 신고증명서 확인 · 현재 상태와 판매 실물 연결 확인 전";
  const records=c.individual_records?.map(r=>`<li>${esc(r.certificate_number)} · ${esc(r.type||"형식 확인 전")} · ${esc(r.registry_validity_label)} · ${esc(r.manufacturer_site)}${r.cancellation_date?` · 취소 ${esc(r.cancellation_date)}`:""}</li>`).join("")||"";
  const docs=sources(c.source_ids).filter(s=>s.url&&(/\.pdf(?:$|\?)/i.test(s.url)||s.kind==="manufacturer_hosted_certification_document"));
  const links=[c.registry_query_url?link(c.registry_query_url,"공식 조회"):"",...docs.map(s=>link(s.url,"증빙 문서"))].filter(Boolean).join(" · ");
  const references=(c.reference_documents||[]).map(d=>`<br><span class="muted">${d.model_match_status==="exact"?"정확 모델 문서":"유사 모델 문서 · 동등성 확인 전"}${d.document_valid_until?` · 문서상 만료 ${esc(d.document_valid_until)} · 현재 취소/변경 여부 별도 확인`:""}</span>`).join("");
  return `<dt>${esc(names[c.system]||c.system)}</dt><dd>${esc(s)}${c.claimed_types?.length?`<br><span class="muted">표시: ${esc(c.claimed_types.join(" / "))}</span>`:""}${c.certificate_number?`<br>번호: ${esc(c.certificate_number)}`:""}${c.document_valid_until?`<br>문서상 만료 ${esc(c.document_valid_until)} · 취소 여부 별도 확인`:""}${references}${records?`<ul>${records}</ul>`:""}${links?`<br>${links}`:""}</dd>`;
}
function performanceMarkup(p) {
  const g=p.chemical_suitability||{},rows=g.performance_evidence||[];
  const resultText=r=>typeof r.result==="string"?r.result:[r.result?.permeation_level!=null?`투과 성능수준 ${r.result.permeation_level}`:"",r.result?.degradation_percent!=null?`열화 ${r.result.degradation_percent}%`:"",r.result?.reported_breakthrough_time?`보고된 시험 돌파시간 ${r.result.reported_breakthrough_time}`:""].filter(Boolean).join(" · ");
  const facts=rows.map(r=>{const concentration=r.concentration||(r.concentration_percent!=null?`${r.concentration_percent}%`:"농도 미기재"),source=sources([r.source_id])[0];return `<li><strong>${esc(r.chemical_name)} ${esc(concentration)}</strong><br>${esc(resultText(r))}<br><span class="muted">${esc(r.test_standard||r.test_method||"시험방법 미기재")} · ${r.temperature_c!=null?`${esc(r.temperature_c)}℃`:"시험온도 미기재"}${r.sample_scope?` · ${esc(r.sample_scope)}`:""}</span>${r.note?`<p>${esc(r.note)}</p>`:""}${source?`<br>${link(source.url,"원본 근거")}`:""}</li>`;}).join("");
  const notes=[...(p.manufacturer_target_substances?.length?[`제조사 표시 대상: ${p.manufacturer_target_substances.join(" · ")}. 실제 노출 조건과 완성 구성은 별도 검토합니다.`]:[]),...(g.notes||[]),...(p.compatibility?.notes||[])];
  if(!facts&&!notes.length) return "";
  return `<details class="certificate-details"><summary>물질·부품 적용 근거</summary>${facts?`<ul class="performance-list">${facts}</ul><p class="small muted">시험 조건의 결과이며 현장 안전 사용시간이나 실제 혼합물 적합성 승인이 아닙니다.</p>`:""}${notes.map(n=>`<p class="small muted">${esc(n)}</p>`).join("")}</details>`;
}
function stockLabel(s) { return ({unknown:"재고 미확정",seller_reported_zero:"판매자 표시: 재고 0",seller_reported_sold_out:"판매자 표시: 품절"})[s]||"실재고 미확정"; }
function purchases(p) {
  if(p.domestic_purchase?.length) return p.domestic_purchase.map(s=>`<p class="small">${link(s.url,s.seller)}<br><span class="muted">${s.stock_evidence_level==="inquiry_only"?"국내 견적 문의":s.exact_style_match?"모델 수준 연결 확인":"정확 스타일 연결 확인 전"} · ${esc(stockLabel(s.stock_status))}</span></p>`).join("");
  const s=sources(p.source_ids).find(s=>["manufacturer_product_page","manufacturer_product"].includes(s.kind));
  return `<p class="small">${s?link(s.url,"해외 제조사 자료"):"구매처 자료 확인 전"}<br><span class="muted">국내 판매·수입처 미확인</span></p>`;
}
function showTab(name) {
  document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.tab===name)));
  ["products","sets","chat","kit"].forEach(id=>$(id+"Panel").hidden=id!==name);
  $("storeHero").hidden=name!=="products";
}
function renderHero() {
  $("heroGallery").innerHTML=["TYCHEM_4000_CHZ5_WHITE","3M_4570_GRAY"].map((id,index)=>{const p=product(id);return p?`<div class="hero-photo"><span class="hero-number">PRODUCT 0${index+1}</span>${imageMarkup(p)}<p>${esc(p.manufacturer)}<br>${esc(p.identity.model)} · ${colours[colour(p)]?.label||"색상 확인 전"}</p></div>`:"";}).join("");
}
function renderTypeGuide() {
  const g=data.classification_guide;
  if(!g) { $("typeGuide").textContent="형식별 기준 자료를 확인 중입니다.";return; }
  const table=(headers,rows)=>`<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  $("typeGuide").innerHTML=`<p>${esc(g.summary)}</p>${table(["보호복 형식","보호복 기준","호흡·안면","장갑·장화"],g.clothing_types.map(t=>[`${t.type}형식`,t.description,t.respiratory_face,t.gloves_boots]))}<h3>함께 쓰는 보호구는 품목별로 확인합니다</h3>${table(["품목","확인할 기준"],g.component_criteria.map(c=>[c.label,c.description]))}<p class="small muted">${esc(g.limit)}</p><div class="sources">${sources(g.source_ids).map(s=>link(s.url,s.title)).join(" · ")}</div>`;
}
function idsOfKit(k) {return k.product_ids||Object.values(k.component_product_ids||{}).flat().filter(Boolean);}
function kitUseType(k) {
  const value=Number(k.selected_use_type??k.use_type??k.kit_review?.use_type??null);
  return Number.isInteger(value)&&value>=1&&value<=6?value:null;
}
function kitWorkGroup(k) {
  const value=k.selected_work_group??k.work_group??k.kit_review?.work_group??null;
  return typeof value==="string"&&value.trim()?value.trim().replace(/\s+/g," ").slice(0,80):null;
}
function colourOverlap(k,coverall,excludeKit=null) {
  const useType=kitUseType(k),workGroup=kitWorkGroup(k),coverallColour=coverall?colour(coverall):null,displayTypes=types(coverall),sameColour=[...savedKits,...recommendedKits].filter(other=>{
    if(other===k||other===excludeKit||(k.kit_id&&other.kit_id&&other.kit_id===k.kit_id)||!coverallColour||coverallColour==="unknown") return false;
    const otherColour=other.selected_coverall_colour??colour(idsOfKit(other).map(product).find(p=>p?.category==="chemical_protective_coverall"));
    return otherColour===coverallColour;
  });
  return {conflicts:sameColour.filter(other=>useType!==null&&kitUseType(other)!==null&&(kitUseType(other)!==useType||(workGroup!==null&&kitWorkGroup(other)!==null&&kitWorkGroup(other)!==workGroup))),unconfirmed:sameColour.filter(other=>useType===null||kitUseType(other)===null||(kitUseType(other)===useType&&(workGroup===null||kitWorkGroup(other)===null))),typeMismatch:useType!==null&&displayTypes.length>0&&!displayTypes.includes(useType)};
}
function colourOverlapText(overlap) {
  const notes=[];
  if(overlap.conflicts.length) notes.push(`색상 충돌 · 대안 확인 필요. 다른 ${[...new Set(overlap.conflicts.map(k=>`${kitUseType(k)}형식${kitWorkGroup(k)?` / ${kitWorkGroup(k)}`:""}`))].join(" · ")} 조합과 보호복 색상이 겹칩니다. 물질별 성능 근거가 있는 다른 색상 제품을 확인해야 합니다.`);
  else if(overlap.unconfirmed.length) notes.push("같은 색상의 다른 조합에서 사용 형식 또는 작업 구분이 미확인입니다. 형식과 작업 목적을 확인한 후 색상 구분을 검토하세요.");
  if(overlap.typeMismatch) notes.push("선택 형식과 제품 표시 불일치. 실제 인증 문서와 사용할 구성의 형식을 확인하세요.");
  return notes.join(" ");
}
function kitMarkup(k,kind,index) {
  const products=idsOfKit(k).map(product).filter(Boolean),coverall=products.find(p=>p.category==="chemical_protective_coverall"),saved=kind==="saved";
  const reason=k.selection_reason||k.kit_review?.selection_reason||"저장한 검토용 초안입니다.",comparison=k.comparison_note||k.kit_review?.comparison_note||"",missing=k.missing_information||k.kit_review?.missing_information||[];
  const useType=kitUseType(k),workGroup=kitWorkGroup(k),overlapNote=coverall?colourOverlapText(colourOverlap(k,coverall)):"";
  const details=`<p class="small kit-selection-reason">${esc(reason)}</p><p class="small muted">${esc(k.colour_note||k.kit_review?.colour_note||"색상은 실제 선택한 제품 외형입니다.")}</p>`;
  return `<article class="work-kit-card ${saved?"saved-kit-card":"kit-option-card"}">${saved?'<p class="section-kicker">SAVED DRAFT · 검토용 초안</p>':`<div class="kit-option-label"><span class="kit-option-number">선택지 ${String(index+1).padStart(2,"0")}</span><span class="badge neutral">검토용</span></div>`}<h3>${esc(k.name||k.company_set_name||"검토 조합")}</h3><p class="kit-use-type"><span class="badge neutral">${useType?`사용 ${useType}형식`:"사용 형식 확인 전"}</span>${coverall&&types(coverall).length?`<span class="small muted">제품 표시: ${types(coverall).map(t=>`${t}형식`).join(" / ")}</span>`:""}</p><p class="kit-work-group">작업 구분: ${esc(workGroup||"확인 전")}</p><p class="small muted">${esc(k.work_context||k.work_description||"")}</p>${comparison?`<p class="kit-comparison-note">${esc(comparison)}</p>`:""}<div class="kit-product-strip">${products.map(p=>`<div>${imageMarkup(p)}<p><span class="muted">${esc(isRespiratoryAccessory(p)?"호흡 부품":parts.find(part=>part.category===p.category)?.label||"구성품")}</span><br>${esc(p.display_name)}</p></div>`).join("")}</div>${coverall?`<p>보호복 ${swatch(colour(coverall))}</p>`:""}${overlapNote?`<p class="small kit-colour-overlap">${esc(overlapNote)}</p>`:""}${saved?`<details><summary>선정 근거와 색상</summary>${details}</details>`:`<div class="kit-choice-evidence"><h4>선정 근거</h4>${details}</div>`}${missing.length?`<div class="kit-missing-information"><h4>남은 확인 ${missing.length}개</h4><ul>${missing.map(q=>`<li>${esc(q)}</li>`).join("")}</ul></div>`:""}<button type="button" class="primary" ${saved?`data-load-kit="${index}"`:`data-apply-kit="${index}"`}>${saved?"이 초안 불러오기":"이 조합 선택하기"}</button></article>`;
}
function kitOptionsMarkup(kits) {
  return `<div class="kit-options-heading"><h3>조합 선택지 <span class="small muted">${kits.length}개</span></h3><p class="small muted">구성품과 남은 조건을 비교해 내 조합에 넣으세요. 선택하면 검토용 초안으로 이어집니다.</p></div><div class="kit-grid">${kits.map((k,i)=>kitMarkup(k,"recommended",i)).join("")}</div>`;
}
function renderWorksiteKits() {
  $("worksiteKits").innerHTML=(recommendedKits.length?kitOptionsMarkup(recommendedKits):"")+(savedKits.length?`<h3>저장한 사업장 초안</h3><div class="kit-grid">${savedKits.map((k,i)=>kitMarkup(k,"saved",i)).join("")}</div>`:"")||'<div class="message">사용 물질과 작업을 입력하면 검토할 조합 선택지를 자동으로 보여드립니다. 구성품을 비교해 내 조합에 넣고 초안으로 저장할 수 있습니다.</div>';
  $("chatExistingColours").textContent=savedKits.length?"저장한 조합: "+savedKits.map(k=>`${k.company_set_name||"조합"} · ${kitUseType(k)?`${kitUseType(k)}형식`:"사용 형식 확인 전"} · ${kitWorkGroup(k)||"작업 구분 확인 전"} · ${colours[k.selected_coverall_colour]?.label||"색상 미확인"}`).join(" / "):"사업장에서 함께 쓰는 다른 형식과 별도 작업은 실제 보호복 색상을 구분합니다. 적합한 색상 대안이 없으면 남은 확인으로 알려드립니다.";
}
function renderProducts() {
  const query=$("searchInput").value.trim().toLocaleLowerCase();
  const list=data.products.filter(p=>($("categoryFilter").value==="all"||p.category===$("categoryFilter").value)&&($("typeFilter").value==="all"||types(p).includes(Number($("typeFilter").value)))&&($("colourFilter").value==="all"||p.appearance.color.id===$("colourFilter").value)&&(!$("domesticOnly").checked||p.domestic_purchase?.length)&&(!query||matchesProductSearch(p,query)));
  $("productCount").textContent=`${list.length}개 후보`;
  $("products").innerHTML=list.map(p=>{return `<article class="product-card"><div class="product-visual">${imageMarkup(p)}</div><div class="product-meta"><p class="section-kicker">${esc(p.manufacturer)}</p><h3 class="product-title">${esc(p.display_name)}</h3><p class="small muted">${esc(photoNote(p))}</p><p class="product-category">${esc(parts.find(part=>part.category===p.category)?.label||p.category)}${types(p).length?` · 제품 표시 ${types(p).map(t=>`${t}형식`).join(" / ")}`:""}</p>${swatch(p.appearance.color.id)}<div class="purchase-links">${purchases(p)}</div><button type="button" class="choose-product" data-product="${esc(p.product_id)}">내 조합에 넣기</button>${performanceMarkup(p)}<details class="certificate-details"><summary>인증·모델 근거 보기</summary><p class="small muted">${esc(p.identity.model)} · ${esc(p.identity.manufacturer_reference||"사이즈 SKU 확인 전")}<br>${esc(photoNote(p))}${p.item_standard_summary?`<br>${esc(p.item_standard_summary)}`:""}</p><dl>${(p.certifications||[]).map(certText).join("")}</dl><div class="sources">${sources(p.source_ids).filter(s=>["manufacturer_product_page","manufacturer_product"].includes(s.kind)).map(s=>link(s.url,"제조사 자료")).join(" · ")}</div><p class="uncertainty">${(p.uncertainties||[]).map(esc).join(" · ")}</p></details></div></article>`;}).join("")||'<p class="message info">해당 조건의 제품 자료가 없습니다. 필터를 바꿔 주세요.</p>';
}
function selectedProductIds() {return [...new Set([...parts.map(part=>$(part.id).value),...respiratoryAddons].filter(Boolean))];}
function invalidateRecommendation() {recommendationEvidence=null;activeKitReview=null;}
function applyProductIds(ids) {
  parts.forEach(part=>$(part.id).value="");respiratoryAddons=[];
  ids.map(product).filter(Boolean).forEach(p=>{
    if(isRespiratoryAccessory(p)) respiratoryAddons.push(p.product_id);
    else {const part=parts.find(part=>part.category===p.category);if(part&&!$(part.id).value) $(part.id).value=p.product_id;}
  });
}
function applyRecommendedKit(indexOrKit) {
  const k=typeof indexOrKit==="object"?indexOrKit:recommendedKits[indexOrKit];if(!k) return;
  applyProductIds(idsOfKit(k));$("companyType").value=k.name||"검토 조합";$("workZone").value=k.work_context||"";$("useType").value=kitUseType(k)||"";$("workGroup").value=kitWorkGroup(k)||"";
  $("exposureNote").value=(k.missing_information||[]).join("\n");activeKitReview=k;activeKitId=null;
  recommendationEvidence=k.recommendation_evidence||null;$("draftExport").hidden=true;renderKit();showTab("kit");
  $("savedStatus").textContent="추천 제품과 호흡 부품을 함께 넣었습니다. 조합 근거와 남은 조건을 검토하세요.";
}
function chooseProduct(id) {
  const p=product(id),part=parts.find(part=>part.category===p?.category);if(!part) return;
  if(isRespiratoryAccessory(p)) {if(!respiratoryAddons.includes(id)) respiratoryAddons.push(id);}else $(part.id).value=id;
  if(userMessages.length&&!$("workZone").value.trim()) $("workZone").value=userMessages.join("\n");
  invalidateRecommendation();$("draftExport").hidden=true;renderKit();showTab("kit");
  $("savedStatus").textContent="검토용 조합에 넣었습니다. 다른 제조사의 제품도 함께 선정할 수 있습니다.";
}
function renderKit() {
  const coverall=product($("coverall").value),ids=selectedProductIds(),useType=kitUseType({use_type:$("useType").value}),workGroup=kitWorkGroup({work_group:$("workGroup").value});
  const overlap=colourOverlap({kit_id:activeKitId,use_type:useType,work_group:workGroup},coverall,activeKitReview);
  $("colourBadge").className="badge neutral";$("colourBadge").textContent=!coverall?"제품 선택 전":overlap.conflicts.length?"색상 충돌 · 대안 확인 필요":overlap.typeMismatch?"선택 형식과 제품 표시 불일치":overlap.unconfirmed.length?"형식·작업 구분 확인 전":!useType?"사용 형식 확인 전":!workGroup?"작업 구분 확인 전":colours[colour(coverall)]?.label||"색상 확인 전";
  $("criteriaNote").textContent=activeKitReview?activeKitReview.selection_reason:"물질과 작업에 맞는 제품을 먼저 검토합니다. 사업장에서 함께 쓰는 다른 형식과 별도 작업은 실제 보호복 색상을 구분합니다.";
  const overlapNote=colourOverlapText(overlap);if(overlapNote) $("criteriaNote").textContent+=" "+overlapNote;
  const componentNotes=coverall?.set_components||{};
  $("kitPreview").innerHTML=parts.map(part=>{const p=product($(part.id).value);return `<div class="component">${p?imageMarkup(p):'<div class="empty-component">미선정</div>'}<h4>${part.label}</h4><p>${esc(p?.display_name||"후보를 선택하세요")}</p>${componentNotes[part.id]?`<p class="small muted">${esc(componentNotes[part.id].reason)}</p>`:""}</div>`;}).join("");
  $("respiratoryParts").innerHTML=respiratoryAddons.map(id=>`<span class="accessory-chip">${esc(product(id)?.identity.model||id)}<button type="button" data-remove-accessory="${esc(id)}" aria-label="${esc(product(id)?.identity.model||id)} 삭제">×</button></span>`).join("")||'<p class="small muted">정화통·필터는 필요한 구성과 호환성을 확인한 뒤 추가합니다.</p>';
  $("cartCount").textContent=String(ids.length);
  $("reviewNote").textContent=ids.length?"제품별 물질 성능과 호흡 부품·소매·장화 연결, 판매 실물의 인증을 함께 검토하세요. 저장은 검토용 초안입니다.":"사용 물질로 추천받거나 제품 후보를 선택해 조합을 구성하세요.";
  $("saveDraft").disabled=!ids.length;$("exportDraft").disabled=!ids.length;$("openOperations").disabled=!ids.length;
}
function payload() {
  const ids=selectedProductIds(),selected=ids.map(product).filter(Boolean),coverall=product($("coverall").value);
  return {schema_version:"review_draft_v4",kit_id:activeKitId||crypto.randomUUID(),created_at:new Date().toISOString(),source_review_date:data.review_date,approved:false,draft_only:true,runtime_registration:false,synthesis_created:false,work_description:$("workZone").value.trim(),company_set_name:$("companyType").value.trim()||"사업장 보호구 조합",selected_use_type:kitUseType({use_type:$("useType").value}),selected_work_group:kitWorkGroup({work_group:$("workGroup").value}),selected_coverall_colour:coverall?colour(coverall):null,colour_policy:"material_first_site_type_work_group_colours",notes:$("exposureNote").value.trim(),components:Object.fromEntries(parts.map(part=>[part.id,$(part.id).value||null])),component_product_ids:Object.fromEntries(parts.map(part=>[part.id,selected.filter(p=>p.category===part.category).map(p=>p.product_id)])),respiratory_parts:respiratoryAddons,product_ids:ids,kit_review:activeKitReview,recommendation_evidence:recommendationEvidence,product_certification_snapshot:Object.fromEntries(selected.map(p=>[p.product_id,p.certifications])),component_system_notes:coverall?.set_components||null,purchase_links:Object.fromEntries(selected.map(p=>[p.product_id,p.domestic_purchase]))};
}
function loadKit(d) {
  $("workZone").value=d.work_description||d.work_zone||"";$("companyType").value=d.company_set_name||d.company_type||"";$("exposureNote").value=d.notes||d.exposure_note||"";$("useType").value=kitUseType(d)||"";$("workGroup").value=kitWorkGroup(d)||"";
  if(d.product_ids) applyProductIds(d.product_ids);else {parts.forEach(part=>$(part.id).value=d.components?.[part.id]||(part.id==="coverall"?d.coverall_product_id:"")||"");respiratoryAddons=d.respiratory_parts||[];}
  activeKitId=d.kit_id||null;activeKitReview=d.kit_review||null;recommendationEvidence=d.recommendation_evidence||null;$("draftExport").hidden=true;renderKit();showTab("kit");
  $("savedStatus").textContent="저장한 작업 조합 초안을 불러왔습니다. 사업장의 사용 형식·작업 구분과 보호복 색상을 확인하세요.";
}
function setBusy(value) {
  busy=value;$("chatSend").disabled=busy||!ready;$("chatSend").textContent=busy?"검토 중…":"보내기 ↑";
  $("chatInput").disabled=busy;$("newChat").disabled=busy;$("chatForm").setAttribute("aria-busy",String(busy));
}
async function checkBackend() {
  try {
    const r=await fetch("/api/ppe/status",{cache:"no-store"});if(!r.ok) throw new Error();
    const s=await r.json();ready=s.ready===true;$("chatStatus").className=`badge ${ready?"good":"pending"}`;$("chatStatus").textContent=ready?"챗봇 연결됨":"챗봇 연결 대기";$("chatProgress").textContent=ready?"물질과 작업을 자유롭게 입력하세요.":(s.message||"Codex 연결을 확인하고 있어요.");
  } catch {ready=false;$("chatStatus").textContent="챗봇 연결 대기";$("chatProgress").textContent="챗봇 서버에 아직 연결되지 않았습니다. 새 대화를 눌러 다시 확인하세요.";}
  setBusy(busy);
}
function addMessage(role,text) {
  const el=document.createElement("article");el.className=`chat-message ${role}`;el.innerHTML=`<strong>${role==="user"?"나":"PPE 도우미"}</strong><p class="message-text">${esc(text)}</p>`;
  $("chatMessages").append(el);$("chatWelcome").hidden=true;return el;
}
function renderAnswer(el,response) {
  el.querySelector(".message-text").textContent=response.reply||"답변 내용이 없습니다.";
  if(response.questions?.length) el.insertAdjacentHTML("beforeend",`<div class="followup-questions"><strong>추가로 알려주세요</strong><ul>${response.questions.map(q=>`<li>${esc(q)}</li>`).join("")}</ul></div>`);
  const evidence={backend:response.backend,model:response.model||null,reply:response.reply,questions:response.questions||[],candidates:response.candidates||[],kits:response.kits||[],sources:response.sources||[],live_lookup:response.live_lookup||null,generated_at:new Date().toISOString()};
  const currentKits=(response.kits||[]).map(k=>({...k,recommendation_evidence:evidence}));recommendedKits=currentKits;renderWorksiteKits();
  if(currentKits.length) {
    el.insertAdjacentHTML("beforeend",`<div class="recommended-kits">${kitOptionsMarkup(currentKits)}</div>`);
    el.querySelectorAll("[data-apply-kit]").forEach(b=>b.addEventListener("click",()=>applyRecommendedKit(currentKits[Number(b.dataset.applyKit)])));
  } else {
    const candidates=(response.candidates||[]).map(c=>({c,p:product(c.product_id)})).filter(x=>x.p);
    if(candidates.length) el.insertAdjacentHTML("beforeend",`<div class="recommended-products">${candidates.map(({c,p})=>`<div class="recommended-product">${imageMarkup(p)}<div><h3>${esc(p.display_name)}</h3>${c.selection_status==="excluded"?'<span class="badge pending">선정 제외 · 비교 자료</span>':""}<p>${esc(c.reason)}</p><div class="purchase-links">${purchases(p)}</div>${c.selection_status==="review_candidate"?`<button type="button" class="choose-product" data-product="${esc(p.product_id)}">내 조합에 넣기</button>`:""}</div></div>`).join("")}</div>`);
    el.querySelectorAll("[data-product]").forEach(b=>b.addEventListener("click",()=>chooseProduct(b.dataset.product)));
  }
  if(response.live_lookup){const l=response.live_lookup;el.insertAdjacentHTML("beforeend",`<p class="small muted">${l.status==="fetched"?`제조사 원문 조회 · ${l.source_count}개 제품 · ${esc(new Date(l.retrieved_at).toLocaleString("ko-KR"))}`:l.status==="error"?"제조사 조회에 실패했습니다. 이번 답변의 실시간 물질 근거는 미확인입니다.":"이번 답변은 추가 원문 조회 없이 작성되었습니다."}</p>${l.sources?.length?`<details class="chat-sources"><summary>물질 조회 결과</summary>${l.sources.map(s=>`<p>${link(s.url,s.title)}<br><span class="small muted">${s.status==="matched"?`해당 CAS 행 ${s.match_count}건`:s.status==="not_found"?"해당 CAS 행 없음":"조회 실패"}${s.revision?` · 자료 개정 ${esc(s.revision)}`:""}</span>${s.queries?.length?`<br><span class="small">${s.queries.map(q=>`CAS ${esc(q.cas)}: ${q.status==="matched"?"시험 행 있음":q.status==="not_found"?"시험 행 없음":"조회 실패"}`).join(" · ")}</span>`:""}</p>`).join("")}</details>`:""}`);}
  if(response.sources?.length) el.insertAdjacentHTML("beforeend",`<details class="chat-sources"><summary>답변 근거 ${response.sources.length}개</summary>${response.sources.map(s=>`<p>${link(s.url,s.title)}<br><span class="small muted">${s.kind==="live_manufacturer_source"?"이번 원문 조회":"등록 자료"}</span>${s.evidence?`<br><span class="small">${esc(s.evidence)}</span>`:""}</p>`).join("")}</details>`);
}
async function submitChat(event) {
  event.preventDefault();const message=$("chatInput").value.trim();if(!message||busy||!ready) return;
  userMessages.push(message);addMessage("user",message);$("chatInput").value="";const answer=addMessage("assistant","입력한 작업과 자료를 확인하고 있어요.");setBusy(true);$("chatProgress").textContent="제품과 법령 자료를 참고해 답변을 준비하고 있어요.";
  try {
    const r=await fetch("/api/ppe/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:chatSession,auto_kit_options:true,message:message+"\n조합 요청 조건: "+JSON.stringify({auto_kit_options:true,distinguish_colours:$("distinguishColours").checked,existing_kits:savedKits.map(k=>{const coverall=idsOfKit(k).map(product).find(p=>p?.category==="chemical_protective_coverall");return {name:k.company_set_name,use_type:kitUseType(k),work_group:kitWorkGroup(k),coverall_colour:k.selected_coverall_colour,product_ids:coverall?[coverall.product_id]:[],product_display_types:types(coverall)};})})})});const response=await r.json();if(!r.ok) throw new Error(response.error||"챗봇 답변을 받지 못했습니다.");
    chatSession=response.session_id;renderAnswer(answer,response);$("chatProgress").textContent="조합 선택지의 구성품과 남은 조건을 비교해 선택하거나, 필요한 정보를 이어서 입력하세요.";
  } catch(e) {answer.classList.add("chat-error");answer.querySelector(".message-text").textContent=e.message||"연결 오류가 발생했습니다. 다시 시도하세요.";$("chatProgress").textContent="답변을 완료하지 못했습니다. 입력을 다시 보내거나 새 대화를 시작하세요.";}
  finally {setBusy(false);$("chatInput").focus();}
}
function getSavedDraft() {for(const key of draftKeys) {const value=localStorage.getItem(key);if(value) return JSON.parse(value);}return null;}
async function init() {
  const r=await fetch("catalog-data.json",{cache:"no-store"});if(!r.ok) throw new Error("제품 자료를 불러오지 못했습니다.");data=await r.json();
  parts.forEach(part=>{$(part.id).insertAdjacentHTML("beforeend",data.products.filter(p=>p.category===part.category&&!isRespiratoryAccessory(p)).map(p=>`<option value="${esc(p.product_id)}">${esc(p.display_name)}</option>`).join(""));$("categoryFilter").insertAdjacentHTML("beforeend",`<option value="${part.category}">${part.label}</option>`);});
  $("respiratorAccessory").insertAdjacentHTML("beforeend",data.products.filter(isRespiratoryAccessory).map(p=>`<option value="${esc(p.product_id)}">${esc(p.display_name)}</option>`).join(""));
  $("colourFilter").insertAdjacentHTML("beforeend",[...new Set(data.products.map(colour))].map(id=>`<option value="${esc(id)}">${esc(colours[id]?.label||id)}</option>`).join(""));
  const domestic=data.products.filter(p=>p.domestic_purchase?.length).length;
  $("catalogScope").textContent=`국내 구매 경로 ${domestic}종 / 전체 ${data.products.length}종의 제품 자료를 비교합니다.`;$("reviewDate").textContent=data.review_date;
  try {savedKits=JSON.parse(localStorage.getItem(savedKitsKey)||"[]");if(!Array.isArray(savedKits)) savedKits=[];}catch{savedKits=[];}
  renderHero();renderTypeGuide();renderWorksiteKits();
  document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));
  document.querySelectorAll("[data-open]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.open)));
  ["categoryFilter","typeFilter","colourFilter","domesticOnly"].forEach(id=>$(id).addEventListener("change",renderProducts));
  $("searchInput").addEventListener("input",()=>{showTab("products");renderProducts();});
  $("resetFilters").addEventListener("click",()=>{["categoryFilter","typeFilter","colourFilter"].forEach(id=>$(id).value="all");$("domesticOnly").checked=true;$("searchInput").value="";renderProducts();});
  $("products").addEventListener("click",e=>{const b=e.target.closest("[data-product]");if(b) chooseProduct(b.dataset.product);});
  $("worksiteKits").addEventListener("click",e=>{const b=e.target.closest("[data-apply-kit],[data-load-kit]");if(b?.hasAttribute("data-apply-kit")) applyRecommendedKit(Number(b.dataset.applyKit));else if(b) loadKit(savedKits[Number(b.dataset.loadKit)]);});
  $("kitPanel").addEventListener("input",e=>{if(["workZone","exposureNote","useType","workGroup",...parts.map(part=>part.id)].includes(e.target.id)) invalidateRecommendation();$("savedStatus").textContent="";$("draftExport").hidden=true;renderKit();});
  parts.forEach(part=>$(part.id).addEventListener("change",()=>{recommendationEvidence=null;activeKitReview=null;renderKit();}));
  $("addRespiratorAccessory").addEventListener("click",()=>{const id=$("respiratorAccessory").value;if(id&&!respiratoryAddons.includes(id)){respiratoryAddons.push(id);invalidateRecommendation();}$("draftExport").hidden=true;renderKit();});
  $("respiratoryParts").addEventListener("click",e=>{const b=e.target.closest("[data-remove-accessory]");if(b){respiratoryAddons=respiratoryAddons.filter(id=>id!==b.dataset.removeAccessory);invalidateRecommendation();$("draftExport").hidden=true;renderKit();}});
  $("chatForm").addEventListener("submit",submitChat);
  document.querySelectorAll("[data-example]").forEach(b=>b.addEventListener("click",()=>{$("chatInput").value=b.dataset.example;$("chatInput").focus();}));
  $("newChat").addEventListener("click",()=>{chatSession=null;userMessages=[];recommendedKits=[];renderWorksiteKits();$("chatMessages").replaceChildren();$("chatWelcome").hidden=false;$("chatInput").value="";checkBackend();});
  try {$("loadDraft").disabled=!getSavedDraft();}catch{}
  $("saveDraft").addEventListener("click",()=>{try{const d=payload();activeKitId=d.kit_id;localStorage.setItem(draftKeys[0],JSON.stringify(d));savedKits=savedKits.filter(k=>k.kit_id!==d.kit_id);savedKits.push(d);localStorage.setItem(savedKitsKey,JSON.stringify(savedKits));$("loadDraft").disabled=false;renderWorksiteKits();renderKit();$("savedStatus").textContent="작업 조합과 실제 제품 색상, 호흡 부품을 사업장 초안으로 저장했습니다.";}catch{$("savedStatus").textContent="브라우저 저장을 사용할 수 없습니다. JSON 보기를 이용하세요.";}});
  $("loadDraft").addEventListener("click",()=>{try{const d=getSavedDraft();if(!["review_draft_v1","review_draft_v2","review_draft_v3","review_draft_v4"].includes(d?.schema_version)) throw new Error();loadKit(d);}catch{$("savedStatus").textContent="저장 초안을 불러오지 못했습니다.";}});
  $("exportDraft").addEventListener("click",()=>{const d=payload();activeKitId=d.kit_id;const json=JSON.stringify(d,null,2);$("draftJson").value=json;$("draftExport").hidden=false;if(exportUrl) URL.revokeObjectURL(exportUrl);exportUrl=URL.createObjectURL(new Blob([json],{type:"application/json"}));$("draftDownload").href=exportUrl;});
  $("openOperations").addEventListener("click",()=>{try{localStorage.setItem("chemiguard_pending_draft_v1",JSON.stringify(payload()));window.location.assign("/operations/");}catch{$("savedStatus").textContent="시연 기준으로 초안을 전달하지 못했습니다. 브라우저 저장 권한을 확인해 주세요.";}});
  renderProducts();renderKit();showTab("products");await checkBackend();
}
init().catch(e=>{$("loadError").hidden=false;$("loadError").textContent=e.message;});
