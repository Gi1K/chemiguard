const item = (value, detail, tone='muted') => ({value, detail, tone});
const hasAlerts = alerts => Object.keys(alerts || {}).length > 0;
const fresh = (time, frameTime) => Number.isFinite(time) && time <= frameTime && frameTime-time <= 5;

export function videoStatus({sourceId, run, connected, presented}) {
  const current = run && run.source_id === sourceId;
  const aligned = current && presented?.run_id === run.id && presented.generation === run.generation;
  let unavailable;
  if (!connected) unavailable = '연결 끊김';
  else if (!current) unavailable = '분석 대기';
  else if (run.status === 'LOADING') unavailable = '준비 중';
  else if (run.status === 'PAUSED') unavailable = '일시정지';
  else if (!['RUNNING', 'FINISHED'].includes(run.status)) unavailable = {ERROR:'분석 오류', INTERRUPTED:'연결 중단'}[run.status] || '분석 중지';
  else if (!aligned) unavailable = run.status === 'FINISHED' ? '분석 완료' : '관찰 대기';
  if (unavailable) return {
    designated:item(unavailable, '현재 관찰 없음'),
    missing:item(unavailable, '현재 관찰 없음'),
    leak:item(unavailable, '현재 관찰 없음'),
  };

  const tracks = presented.tracks || [];
  let designated=0, partial=0, missing=0, unresolved=0, alarms=0, unknown=0, mismatch=0;
  for (const track of tracks) {
    const valid = track.processing_state === 'RUNNING' && fresh(track.source_time_s, presented.source_time_s);
    const wearing = valid ? track.wearing : 'UNKNOWN';
    const active = track.active_violations?.length > 0;
    if (active) alarms++;
    if (wearing === 'NOT_WORN') missing++;
    else if (active) unresolved++;
    else if (!['WORN', 'VISIBLE_WORN'].includes(wearing)) unknown++;

    const product = track.product_check || {};
    const productFresh = fresh(product.source_time_s, presented.source_time_s);
    const productAlarm = hasAlerts(track.product_alerts) || hasAlerts(product.active_alerts);
    if (productAlarm || productFresh && product.state === 'MISMATCH') mismatch++;
    // A registered appearance alone cannot establish that the PPE is being worn.
    if (['WORN','VISIBLE_WORN'].includes(wearing) && !active && !productAlarm
        && productFresh && product.primary_backend === 'decisions' && product.state === 'CANDIDATE'
        && product.membership === 'candidate' && product.candidate?.designation_basis === 'site_standard_color_and_form') {
      designated++;
      if (wearing === 'VISIBLE_WORN') partial++;
    }
  }
  const total = tracks.length;
  const designatedState = !total ? item('대상 없음', '현재 추적 0명')
    : item(`${designated} / ${total}명`, mismatch ? `미해당 ${mismatch}명` : partial ? `보이는 범위 ${partial}명 포함`
      : designated === total ? '등록 색상·형식 일치' : `착용·제품 확인 필요 ${total-designated}명`,
      mismatch ? 'danger' : designated === total ? 'good' : 'caution');
  const missingState = !total ? item('대상 없음', '현재 추적 0명')
    : missing ? item(`${missing}명 미착용`, alarms ? `미해제 경보 ${alarms}명` : '첫 관찰 · 경보 전', 'danger')
    : unresolved ? item('재확인', `미해제 경보 ${unresolved}명`, 'danger')
    : unknown ? item('확인 중', `판독 대기 ${unknown}명`, 'caution')
    : item('미관측', `착용 관찰 ${total}명`, 'good');
  const scene = presented.scene;
  const leakState = scene?.processing_state !== 'RUNNING' || scene.error
    ? item(scene?.error || scene?.processing_state === 'ERROR' ? '관찰 오류'
      : {STALE:'관측 만료', DISABLED:'감시 꺼짐'}[scene?.processing_state] || '관찰 대기', '현재 판정 불가')
    : scene.detections?.length || scene.suspected
      ? item('누출', `${scene.detections?.length || 0}개 영역 · 영상 징후`, 'danger')
      : item('미관측', '현재 영상 기준', 'good');
  const detectorError = run.people_state === 'ERROR';
  return {designated:detectorError ? item('감지 오류', '현재 인원 판정 불가') : designatedState,
    missing:detectorError ? item('감지 오류', '현재 인원 판정 불가') : missingState, leak:leakState};
}
