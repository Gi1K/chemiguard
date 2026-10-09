export const WEARING_LABELS = {
  WORN: '필수 부위 착용 관찰', VISIBLE_WORN: '보이는 범위 착용',
  NOT_WORN: '미착용', UNKNOWN: '확인 불가',
};

export function observationLabel(track) {
  if(Object.keys(track.product_alerts||{}).length) return '등록 보호복 불일치 의심';
  if(track.wearing==='NOT_WORN') return '미착용';
  if(track.active_violations?.length) return '미해제 위반 재확인';
  return WEARING_LABELS[track.wearing]||'확인 불가';
}

export function overlayLabel(track) {
  if(!track.active_violations?.length&&!Object.keys(track.product_alerts||{}).length&&['WORN','VISIBLE_WORN'].includes(track.wearing)) return '착용';
  return observationLabel(track);
}
