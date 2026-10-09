import test from 'node:test';
import assert from 'node:assert/strict';
import {overlayAt} from '../src/videoTimeline.js';

const sample=(time,scene,tracks)=>({source_time_s:time,generation:1,scene_epoch:scene,tracks});
const person=(token,x)=>({track_token:token,bbox:[x,0,x+100,200]});

test('interpolate only the same target in the same shot',()=>{
  const frames=[sample(1,0,[person('one',0)]),sample(1.2,0,[person('one',20)])];
  assert.ok(Math.abs(overlayAt(frames,1.1,1).tracks[0].bbox[0]-10)<0.001);
  frames[1].tracks=[person('other',20)];
  assert.equal(overlayAt(frames,1.1,1).tracks[0].bbox[0],0);
});
test('blank boundary removes the previous shot exactly at the transition',()=>{
  const frames=[sample(1,0,[person('one',0)]),sample(1.1,1,[]),sample(1.2,1,[person('new',200)])];
  assert.equal(overlayAt(frames,1.09,1).tracks.length,1);
  assert.equal(overlayAt(frames,1.1,1).tracks.length,0);
  assert.equal(overlayAt(frames,1.19,1).tracks.length,0);
  assert.equal(overlayAt(frames,1.2,1).tracks[0].track_token,'new');
});
test('never display future, expired or other-generation boxes',()=>{
  const frames=[sample(1,0,[person('one',0)])];
  assert.equal(overlayAt(frames,0.9,1),null);
  assert.equal(overlayAt(frames,1.31,1),null);
  assert.equal(overlayAt(frames,1,2),null);
});

test('bridge bounded tracking jitter only when both measured endpoints exist',()=>{
  const first={...person('one',0),wearing:'UNKNOWN'};
  const next={...person('one',40),wearing:'WORN'};
  const frames=[sample(1,0,[first,person('gone',150)]),sample(1.8,0,[next])];
  frames[0].scene={processing_state:'RUNNING',detections:[{bbox:[0,0,10,10]}]};
  const aligned=overlayAt(frames,1.4,1);
  assert.equal(aligned.tracks.length,1);
  assert.ok(Math.abs(aligned.tracks[0].bbox[0]-20)<0.001);
  assert.equal(aligned.tracks[0].wearing,'UNKNOWN');
  assert.equal(aligned.scene.processing_state,'STALE');
  assert.deepEqual(aligned.scene.detections,[]);
});

test('never bridge absence, token changes, shot changes, jumps or long outages',()=>{
  for(const right of [sample(1.6,0,[]),sample(1.6,0,[person('new',10)]),
    sample(1.6,1,[person('one',10)]),sample(1.6,0,[person('one',300)]),
    sample(1.9,0,[person('one',10)]),{...sample(1.6,0,[person('one',10)]),generation:2}]) {
    assert.equal(overlayAt([sample(1,0,[person('one',0)]),right],1.4,1),null);
  }
});
