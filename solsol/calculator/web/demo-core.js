'use strict';
const DemoCore=(()=>{
const pct=x=>(100*x).toFixed(2)+'%',num=x=>Number(x).toLocaleString('ko-KR'),ok=p=>p.D>=.95&&p.I>=.9;
function evaluate(m,p){
 if(typeof p.q!=='string'||!/^[0-3]{100}$/.test(p.q))throw Error('설치 스위치 자료가 올바르지 않습니다');
 const nr=new Uint16Array(m.demand.length),ne=new Uint16Array(m.demand.length),devices=[];
 [...p.q].forEach((q,i)=>{for(let t=0;t<2;t++)if(+q&(t?2:1)){const cover=[];m.demand.forEach(([x,y],j)=>{if((m.sites[i][0]-x)**2+(m.sites[i][1]-y)**2<=(t?2250000:9000000)){cover.push(j);(t?ne:nr)[j]++}});devices.push({site:i,type:t,cover})}});
 let d=0,ii=0;for(let j=0;j<nr.length;j++){if(nr[j])d++;if(nr[j]&&ne[j])ii++}
 for(const v of devices){v.loss=[0,0];for(const j of v.cover){if(v.type===0&&nr[j]===1){v.loss[0]++;if(ne[j])v.loss[1]++}if(v.type===1&&ne[j]===1&&nr[j])v.loss[1]++}v.redundant=!v.loss.some(Boolean)}
 const cost=devices.reduce((n,v)=>n+(v.type?2:6),0),F=[1-d/nr.length,1-ii/nr.length,cost/800];
 if(cost!==p.cost||Math.abs(p.D-d/nr.length)>1e-10||Math.abs(p.I-ii/nr.length)>1e-10||F.some((v,i)=>Math.abs(v-p.F[i])>1e-10))throw Error('지도와 원시 목적값이 일치하지 않습니다');
 return{nr,ne,d,i:ii,cost,F,devices,zero:devices.filter(v=>!v.cover.length).length,redundant:devices.filter(v=>v.redundant).length};
}
function mapSvg(m,p,prefix,opts={}){
 const a=evaluate(m,p),lo=opts.zoom==='core'?3000:0,hi=opts.zoom==='core'?17000:20000,scale=800/(hi-lo),x=v=>60+(v-lo)*scale,y=v=>840-(v-lo)*scale;
 let s=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 900" role="img" aria-label="${prefix} 배치 지도" data-mask="${p.q}" data-cost="${p.cost}" data-d="${p.D}" data-i="${p.I}"><defs><clipPath id="clip-${prefix}"><rect x="60" y="40" width="800" height="800"/></clipPath></defs><rect x="60" y="40" width="800" height="800" fill="#fcfdfe" stroke="#819cad" stroke-width="2"/>`;
 for(let k=Math.ceil(lo/2000)*2000;k<=hi;k+=2000)s+=`<line class="grid" x1="${x(k)}" x2="${x(k)}" y1="40" y2="840"/><line class="grid" x1="60" x2="860" y1="${y(k)}" y2="${y(k)}"/><text x="${x(k)}" y="867" text-anchor="middle" font-size="22">${k/1000}</text><text x="47" y="${y(k)+7}" text-anchor="end" font-size="22">${k/1000}</text>`;
 s+=`<g clip-path="url(#clip-${prefix})"><circle class="defense" cx="${x(10000)}" cy="${y(10000)}" r="${6000*scale}" fill="#e4edf2" fill-opacity=".5" stroke="#263f52" stroke-width="4" stroke-dasharray="14 9"/>`;
 if(opts.candidates)m.sites.forEach(([xx,yy],i)=>s+=`<path data-site="${i}" class="candidate" d="M${x(xx)-4},${y(yy)}h8m-4,-4v8" stroke="#657d8e" stroke-width="1.4"><title>후보${i+1} · ${xx/1000}, ${yy/1000} km</title></path>`);
 for(const v of a.devices){const [xx,yy]=m.sites[v.site],t=v.type;if(opts.cover==='both'||opts.cover===(t?'eoir':'radar'))s+=`<circle class="coverage" data-site="${v.site}" data-type="${t}" data-metres-x="${xx}" data-metres-y="${yy}" data-radius="${t?1500:3000}" cx="${x(xx)}" cy="${y(yy)}" r="${(t?1500:3000)*scale}" fill="${t?'#e69528':'#168fc5'}" fill-opacity=".035" stroke="${t?'#a84b00':'#006da3'}" stroke-width="3" ${t?'stroke-dasharray="10 7"':''}/>`}
 if(opts.demand)m.demand.forEach(([xx,yy],j)=>{const u=x(xx),v=y(yy);s+=a.nr[j]&&a.ne[j]?`<circle cx="${u}" cy="${v}" r="3.5" fill="#08714e"/>`:a.nr[j]?`<path d="M${u},${v-4}l4,8h-8Z" fill="#006da3"/>`:`<path d="M${u-3},${v-3}l6,6m0,-6l-6,6" stroke="#bc351f" stroke-width="2"/>`});
 for(const v of a.devices){const [xx,yy]=m.sites[v.site],t=v.type,both=+p.q[v.site]===3,dx=both?(t?12:-12):0,u=x(xx)+dx,w=y(yy)-(both?9:0);s+=`<g class="sensor" data-site="${v.site}" data-type="${t}" role="button" tabindex="0" aria-label="候補${v.site+1} ${t?'EOIR':'Radar'}"><title>후보${v.site+1} · ${t?'EO/IR':'Radar'} · ${xx/1000},${yy/1000}km</title>`.replace('候補','후보');if(both)s+=`<line x1="${x(xx)}" y1="${y(yy)}" x2="${u}" y2="${w}" stroke="#294253" stroke-width="1.5"/>`;s+=t?`<rect x="${u-11}" y="${w-11}" width="22" height="22" fill="white" stroke="#a84b00" stroke-width="3"/>`:`<circle cx="${u}" cy="${w}" r="12" fill="white" stroke="#006da3" stroke-width="3"/>`;s+=`<text class="device-mark" x="${u}" y="${w+6}" text-anchor="middle" fill="${t?'#a84b00':'#006da3'}" font-size="18" font-weight="700">${t?'E':'R'}</text></g>`}
 s+=`</g><text x="60" y="26" font-size="22">${lo?'평가영역 확대 · 3~17 km':'전체 지도 · 20 × 20 km'} · 북 ↑</text><text x="860" y="893" text-anchor="end" font-size="20">가로·세로 거리 (km)</text><line x1="85" x2="${85+2000*scale}" y1="810" y2="810" stroke="#18384b" stroke-width="7"/><text x="85" y="794" font-size="21">2 km</text></svg>`;return s;
}
function project3d(points,angle){
 const az=angle*Math.PI/180,el=.5;const d0=Math.max(0,Math.floor(Math.min(.95,...points.map(v=>v.p.D))*20)/20-.05),i0=Math.max(0,Math.floor(Math.min(.9,...points.map(v=>v.p.I))*20)/20-.05),c0=Math.max(0,Math.floor(Math.min(...points.map(v=>v.p.cost))/20)*20-20),c1=Math.ceil(Math.max(...points.map(v=>v.p.cost))/20)*20+20;
 const proj=(x,y,z)=>[(x-.5)*Math.cos(az)-(y-.5)*Math.sin(az),((x-.5)*Math.sin(az)+(y-.5)*Math.cos(az))*Math.sin(el)-(z-.5)*Math.cos(el)];
 const cube=[];for(let x=0;x<2;x++)for(let y=0;y<2;y++)for(let z=0;z<2;z++)cube.push([x,y,z]);const pp=cube.map(v=>proj(...v)),xr=[Math.min(...pp.map(p=>p[0])),Math.max(...pp.map(p=>p[0]))],yr=[Math.min(...pp.map(p=>p[1])),Math.max(...pp.map(p=>p[1]))],scale=Math.min(680/(xr[1]-xr[0]),320/(yr[1]-yr[0]));
 const at=(x,y,z)=>{const p=proj(x,y,z);return[450+(p[0]-(xr[0]+xr[1])/2)*scale,220+(p[1]-(yr[0]+yr[1])/2)*scale]};
 return{cube,at,d0,i0,c0,c1,points:points.map(v=>({...v,xy:at((v.p.D-d0)/(1-d0),(v.p.I-i0)/(1-i0),(v.p.cost-c0)/(c1-c0))}))};
}
return{pct,num,ok,evaluate,mapSvg,project3d};
})();
if(typeof module!=='undefined')module.exports=DemoCore;
