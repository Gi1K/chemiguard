export const WEARING_LABELS = {
  WORN: '필수 부위 착용 관찰', VISIBLE_WORN: '보이는 범위 착용',
  NOT_WORN: '미착용 의심', UNKNOWN: '확인 불가',
};

const PART_NAMES = {torso:'몸통',left_arm:'왼팔',right_arm:'오른팔',left_leg:'왼다리',right_leg:'오른다리',hood:'후드',closure:'여밈',respirator:'전면형 방독면'};

export function observationLabel(track) {
  if(track.active_violations?.length) return '미해제 위반 재확인';
  if(track.wearing==='NOT_WORN') {
    const missing=Object.entries(track.parts||{}).filter(([,state])=>state==='uncovered'||state==='open');
    if(missing.length===1) return `${PART_NAMES[missing[0][0]]||'부위'} ${missing[0][1]==='open'?'열림':'미착용'} 의심`;
  }
  return WEARING_LABELS[track.wearing]||'확인 불가';
}

export function overlayLabel(track) {
  if(!track.active_violations?.length&&['WORN','VISIBLE_WORN'].includes(track.wearing)) return '착용';
  return observationLabel(track);
}
