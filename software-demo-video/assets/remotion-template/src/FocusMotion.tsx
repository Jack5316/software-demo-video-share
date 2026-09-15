import React from 'react';
import {useCurrentFrame,useVideoConfig} from 'remotion';
export type FocusKey={t:number;scale:number;x:number;y:number};
export type ClickCue={t:number;x:number;y:number;label?:string};
export function focusAt(keys:FocusKey[],time:number):FocusKey {
  if(!keys.length)return {t:time,scale:1,x:.5,y:.5};
  if(time<=keys[0].t)return keys[0];
  for(let i=1;i<keys.length;i++)if(time<keys[i].t){const a=keys[i-1],b=keys[i];const u=(time-a.t)/(b.t-a.t);const k=u*u*u*(u*(u*6-15)+10);return {t:time,scale:a.scale+(b.scale-a.scale)*k,x:a.x+(b.x-a.x)*k,y:a.y+(b.y-a.y)*k};}
  return keys[keys.length-1];
}
export const FocusMotion:React.FC<{camera?:FocusKey[];clicks?:ClickCue[];children:React.ReactNode}>=({camera=[],clicks=[],children})=>{
 const frame=useCurrentFrame();const {fps,width,height}=useVideoConfig();const h=height-120;const time=frame/fps;const c=focusAt(camera,time);
 const margin=(width-h*width/height)/2*Math.min(1,Math.max(0,(c.scale-1)/.15));
 const tx=Math.max(width-(width-margin)*c.scale,Math.min(-margin*c.scale,width/2-c.x*width*c.scale));
 const ty=Math.max(h-h*c.scale,Math.min(0,h/2-c.y*h*c.scale));
 return <div style={{position:'absolute',inset:0,height:h,overflow:'hidden'}}><div style={{position:'absolute',width,height:h,transformOrigin:'0 0',transform:`translate(${tx}px, ${ty}px) scale(${c.scale})`}}>
  {children}
  {clicks.map((click,i)=>{const age=time-click.t;if(age<0||age>.72)return null;const u=age/.72;const size=24+48*u;return <div key={i} style={{position:'absolute',left:click.x*width,top:click.y*h,transform:'translate(-50%,-50%)',width:size,height:size,borderRadius:'50%',border:'3px solid #e8a528',background:`rgba(255,203,75,${.25*(1-u)})`,boxShadow:'0 0 0 2px rgba(255,255,255,.85)',opacity:1-u,pointerEvents:'none'}}/>})}
 </div></div>
}
