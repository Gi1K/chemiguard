import assert from 'node:assert/strict';
import test from 'node:test';
import {videoStatus} from '../src/videoStatus.js';

const candidate = {source_time_s:2, primary_backend:'decisions', state:'CANDIDATE', membership:'candidate',
  candidate:{designation_basis:'site_standard_color_and_form'}};
const worn = {source_time_s:2, processing_state:'RUNNING', wearing:'VISIBLE_WORN', confirmed:true,
  active_violations:[], product_alerts:{}, product_check:candidate};
const input = (tracks=[], scene={processing_state:'RUNNING', detections:[]}) => ({sourceId:'source', connected:true,
  run:{id:'run', source_id:'source', generation:1, status:'RUNNING'},
  presented:{run_id:'run', generation:1, source_time_s:3, tracks, scene}});

test('registered appearance and a valid wearing observation are both required', () => {
  const state=videoStatus(input([worn]));
  assert.equal(state.designated.value, '1 / 1명');
  assert.equal(state.designated.tone, 'good');
  assert.match(state.designated.detail, /보이는 범위/);
  for (const override of [{wearing:'UNKNOWN'}, {product_check:{}},
    {product_check:{...candidate, primary_backend:'siglip'}},
    {product_check:{...candidate, candidate:{designation_basis:'appearance'}}}]) {
    assert.equal(videoStatus(input([{...worn,...override}])).designated.tone, 'caution');
  }
});
test('first wearing observation immediately counts without pretending it has consensus', () => {
  for (const wearing of ['WORN','VISIBLE_WORN']) {
    const track={...worn, wearing, confirmed:false};
    const state=videoStatus(input([track]));
    assert.equal(state.designated.value, '1 / 1명');
    assert.equal(state.designated.tone, 'good');
    assert.equal(state.missing.value, '미관측');
    assert.equal(track.confirmed, false);
    assert.equal(videoStatus(input([{...track,active_violations:['hood']}])).designated.value, '0 / 1명');
    assert.equal(videoStatus(input([{...track,active_violations:['hood']}])).missing.value, '재확인');
  }
});
test('first missing observation is red but does not manufacture an alarm', () => {
  const first=videoStatus(input([{...worn, wearing:'NOT_WORN', confirmed:false}]));
  assert.equal(first.missing.value, '1명 미착용');
  assert.equal(first.missing.detail, '첫 관찰 · 경보 전');
  assert.equal(first.missing.tone, 'danger');
  assert.equal(first.designated.value, '0 / 1명');
  const second=videoStatus(input([{...worn, wearing:'NOT_WORN', active_violations:['hood']} ]));
  assert.equal(second.missing.detail, '미해제 경보 1명');
});
test('unknown observations and unresolved violations cannot look clear', () => {
  assert.equal(videoStatus(input([{...worn, wearing:'UNKNOWN'}])).missing.value, '확인 중');
  for (const wearing of ['UNKNOWN', 'VISIBLE_WORN']) {
    const state=videoStatus(input([{...worn,wearing,active_violations:['hood']} ]));
    assert.equal(state.missing.value, '재확인');
    assert.equal(state.missing.tone, 'danger');
    assert.equal(state.designated.value, '0 / 1명');
  }
});
test('mixed people and product mismatch remain visible separately from PPE', () => {
  const state=videoStatus(input([worn, {...worn, wearing:'NOT_WORN'},
    {...worn, product_check:{...candidate,state:'MISMATCH'}}]));
  assert.equal(state.designated.value, '1 / 3명');
  assert.equal(state.designated.detail, '미해당 1명');
  assert.equal(state.designated.tone, 'danger');
  assert.equal(state.missing.value, '1명 미착용');
  assert.equal(videoStatus(input([{...worn, product_alerts:{color:'mismatch'}}])).designated.tone, 'danger');
});
test('missing people are not a positive wearing observation', () => {
  const state=videoStatus(input());
  assert.equal(state.designated.value, '대상 없음');
  assert.equal(state.missing.tone, 'muted');
  assert.equal(state.leak.value, '미관측');
  const failed=input();
  failed.run.people_state='ERROR';
  assert.equal(videoStatus(failed).designated.value, '감지 오류');
  assert.equal(videoStatus(failed).missing.value, '감지 오류');
});
test('leak detections and unavailable scene processing are distinct', () => {
  assert.equal(videoStatus(input([], {processing_state:'RUNNING',detections:[{}]})).leak.value, '누출');
  for (const processing_state of ['STALE','ERROR','DISABLED','WAITING']) {
    assert.equal(videoStatus(input([], {processing_state,detections:[{}]})).leak.tone, 'muted');
  }
  assert.equal(videoStatus(input([], {processing_state:'RUNNING',error:'failed',detections:[]})).leak.value, '관찰 오류');
});
test('stale, future and failed PPE or product evidence is never designated wearing', () => {
  for (const override of [{source_time_s:-3}, {source_time_s:4}, {source_time_s:null},
    {processing_state:'ERROR'}, {processing_state:'STALE'},
    {product_check:{...candidate,source_time_s:-3}}, {product_check:{...candidate,source_time_s:4}},
    {product_check:{...candidate,state:'STALE'}}]) {
    assert.notEqual(videoStatus(input([{...worn,...override}])).designated.tone, 'good');
  }
});
test('the strip cannot use another source, run, generation or disconnected snapshot', () => {
  const current=input([worn]);
  for (const override of [{connected:false}, {sourceId:'other'}, {presented:null},
    {presented:{...current.presented,run_id:'other'}}, {presented:{...current.presented,generation:2}},
    ...['LOADING','PAUSED','STOPPED','ERROR','INTERRUPTED'].map(status=>({run:{...current.run,status}}))]) {
    for (const state of Object.values(videoStatus({...current,...override}))) assert.equal(state.tone, 'muted');
  }
  assert.equal(videoStatus({...current,run:{...current.run,status:'FINISHED'}}).designated.value, '1 / 1명');
  assert.equal(videoStatus({...current,run:{...current.run,status:'FINISHED'},presented:null}).designated.value, '분석 완료');
});
