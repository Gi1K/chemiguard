import assert from 'node:assert/strict';
import test from 'node:test';
import {observationLabel, overlayLabel} from '../src/wearingStatus.js';

test('partial wearing and full observation have distinct labels',()=>{
  assert.equal(observationLabel({wearing:'VISIBLE_WORN'}),'보이는 범위 착용');
  assert.equal(observationLabel({wearing:'WORN'}),'필수 부위 착용 관찰');
});
test('specific violation and unresolved alarm stay explicit',()=>{
  assert.equal(observationLabel({wearing:'NOT_WORN',parts:{hood:'uncovered',closure:'not_visible'}}),'후드 미착용 의심');
  assert.equal(observationLabel({wearing:'VISIBLE_WORN',active_violations:['필수 여밈 열림']}),'미해제 위반 재확인');
});
test('video label is concise without hiding an unresolved alarm',()=>{
  assert.equal(overlayLabel({wearing:'VISIBLE_WORN'}),'착용');
  assert.equal(overlayLabel({wearing:'WORN'}),'착용');
  assert.equal(overlayLabel({wearing:'VISIBLE_WORN',active_violations:['필수 여밈 열림']}),'미해제 위반 재확인');
  assert.equal(overlayLabel({wearing:'UNKNOWN'}),'확인 불가');
});
