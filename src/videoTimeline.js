function overlaps(a,b) {
  const intersection=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
  const union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection;
  return union>0?intersection/union:0;
}

export function overlayAt(frames, position, generation) {
  const samples=frames.filter(frame=>frame.generation===generation);
  let index=-1;
  for(let i=0;i<samples.length;i++) if(samples[i].source_time_s<=position) index=i;
  if(index<0) return null;
  const left=samples[index],right=samples[index+1];
  if(position-left.source_time_s>0.3) return null;
  const gap=right?right.source_time_s-left.source_time_s:0;
  const fraction=gap>0&&gap<=0.4&&left.scene_epoch===right.scene_epoch?(position-left.source_time_s)/gap:0;
  const tracks=left.tracks.map(track=>{
    const next=right?.tracks.find(item=>item.track_token===track.track_token);
    return next&&fraction>0&&overlaps(track.bbox,next.bbox)>=0.2?
      {...track,bbox:track.bbox.map((value,i)=>value+(next.bbox[i]-value)*fraction)}:track;
  });
  return {...left,tracks};
}
