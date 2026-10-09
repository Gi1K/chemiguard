import React from 'react';
import {AlertTriangle, Droplets, ShieldCheck} from 'lucide-react';
import {videoStatus} from './videoStatus.js';
import './videoStatus.css';

const indicators = [
  {key:'designated', label:'지정 보호구 착용', Icon:ShieldCheck, title:'등록 색상·형식과 착용 관찰 기준. 실물 모델·화학 적합성 인증이 아닙니다.'},
  {key:'missing', label:'미착용', Icon:AlertTriangle, title:'첫 관찰부터 미착용 표시. 같은 부위 2회 연속 미착용 시 경보.'},
  {key:'leak', label:'누출', Icon:Droplets, title:'영상에서 보이는 누출 징후. 물질·농도 또는 실제 누출 확정이 아닙니다.'},
];

export function VideoStatus(props) {
  const status = videoStatus(props);
  return <section className="video-status" aria-label="현재 영상 관찰 현황" role="status" aria-live="polite" aria-atomic="true">
    {indicators.map(({key,label,Icon,title}) => <div key={key} className={`video-status-item status-${status[key].tone}`} data-status={key} title={title}>
      <div className="video-status-label"><Icon size={17}/><span>{label}</span></div>
      <strong>{status[key].value}</strong>
      <small>{status[key].detail}</small>
    </div>)}
  </section>;
}
