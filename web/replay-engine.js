/* Canvas replay engine for one round: interpolated player states + utility/combat effects.
   Data: 16 Hz replay track when available (replay-v1), otherwise the 4 Hz observation frames.
   Effect radii are illustrative map markers, not smoke voxels or real burn areas. */
(()=>{
const SMOKE_R=144,FIRE_R=110,FLASH_R=260,HE_R=220,SHOT_LEN=1100,SHOT_LIFE=.16,HIT_LIFE=.45,BOMB_TIME=40;
const COLORS={T:'#f0b34a',CT:'#62b6e6',dead:'#6d6a64',smoke:'#cfd3d8',flash:'#fffbe6',he:'#ff7a3d',fire:'#ff6a1f',decoy:'#9aa'};
const NADE={smoke:'#d8dde2',flash:'#fff6b0',he:'#ff6a4a',fire:'#ff9a3d',decoy:'#aaa'};
function lerp(a,b,k){return a+(b-a)*k}
function lerpYaw(a,b,k){let d=((b-a+540)%360)-180;return a+d*k}
function hash(n){let x=Math.sin(n*12.9898)*43758.5453;return x-Math.floor(x)}

/* Normalise both sources into {times, players:{id:{side,x,y,z,yaw,hp,ar,w,fl}}, weapons, events} */
function fromFrames(round){
  const times=round.frames.map(f=>f.seconds),players={},weapons=[];
  const wi=w=>{if(!w)return -1;let i=weapons.indexOf(w);if(i<0){weapons.push(w);i=weapons.length-1}return i};
  round.frames.forEach((f,i)=>{for(const p of f.players){const q=players[p.id]??={side:p.side,x:[],y:[],z:[],yaw:[],hp:[],ar:[],w:[],fl:[],inv:[]};
    q.x[i]=p.position[0];q.y[i]=p.position[1];q.z[i]=p.position[2];q.yaw[i]=p.yaw;q.hp[i]=p.alive?(p.hp??100):0;q.ar[i]=p.armor??0;q.w[i]=wi(p.weapon);q.fl[i]=0}});
  for(const q of Object.values(players))for(const k of ['x','y','z','yaw','hp','ar','w','fl'])for(let i=0;i<times.length;i++)if(q[k][i]===undefined)q[k][i]=null;
  const map={smokegrenade_detonate:'smokegrenade_detonate',smokegrenade_expired:'smokegrenade_expired',flashbang_detonate:'flashbang_detonate',hegrenade_detonate:'hegrenade_detonate',inferno_startburn:'inferno_startburn',inferno_expire:'inferno_expire',player_death:'player_death',bomb_planted:'bomb_planted',bomb_defused:'bomb_defused',bomb_exploded:'bomb_exploded'};
  const events=round.events.filter(e=>map[e.type]).map(e=>({k:e.type,t:e.seconds,a:e.actor,by:e.attacker,p:e.position,e:e.entity,w:e.weapon}));
  return {times,players,weapons,events,hz:4};
}

class Engine{
  constructor(canvas){this.names={};this.c=canvas;this.ctx=canvas.getContext('2d');this.data=null;this.radar=null;this.images={};this.view=[0,0,1024,1024];this.selected=null;this.hover=null;this.trail=3;this.clip=null;this.floor='upper'}
  icon(weapon){const key=window.CSIcon?.key(weapon);if(!key)return null;this.icons??={};let im=this.icons[key];if(!im){im=new Image();im.src='/icons/'+key+'.svg';this.icons[key]=im}return im.complete&&im.naturalWidth?im:null}
  setRadar(meta){this.radar=meta;this.images={};if(!meta)return;for(const [k,u] of [['upper',meta.upper_url],['lower',meta.lower_url]])if(u){const im=new Image();im.src=u;this.images[k]=im}}
  setRound(round,replay){
    const d=replay?{...replay,events:replay.events.slice()}:fromFrames(round);
    // Death/bomb/utility events from the observation file fill gaps (the 16 Hz track keeps its own copies).
    if(replay){const have=new Set(d.events.map(e=>e.k));for(const e of round.events)if(['bomb_planted','bomb_defused','bomb_exploded'].includes(e.type)&&!have.has(e.type))d.events.push({k:e.type,t:e.seconds,a:e.actor,p:e.position})}
    d.events.sort((a,b)=>a.t-b.t);
    d.smokes=[];d.fires=[];
    for(const e of d.events){
      if(e.k==='smokegrenade_detonate'){const end=d.events.find(x=>x.k==='smokegrenade_expired'&&x.t>e.t&&(x.e===e.e||(x.p&&e.p&&Math.hypot(x.p[0]-e.p[0],x.p[1]-e.p[1])<40)));d.smokes.push({...e,end:end?end.t:e.t+20})}
      if(e.k==='inferno_startburn'){const end=d.events.find(x=>x.k==='inferno_expire'&&x.t>e.t&&(x.e===e.e||(x.p&&e.p&&Math.hypot(x.p[0]-e.p[0],x.p[1]-e.p[1])<200)));d.fires.push({...e,end:end?end.t:e.t+7})}
    }
    d.plant=d.events.find(e=>e.k==='bomb_planted')||null;d.defuse=d.events.find(e=>e.k==='bomb_defused')||null;d.boom=d.events.find(e=>e.k==='bomb_exploded')||null;
    d.grenades=(replay?.grenades||[]).filter(g=>g.trajectory&&g.trajectory.length>1);
    d.duration=round.duration;this.data=d;if(replay?.names)this.names=replay.names;
  }
  index(t){const T=this.data.times;let lo=0,hi=T.length-1;if(t<=T[0])return [0,0,0];if(t>=T[hi])return [hi,hi,0];
    while(hi-lo>1){const m=(lo+hi)>>1;if(T[m]<=t)lo=m;else hi=m}return [lo,hi,(t-T[lo])/Math.max(1e-6,T[hi]-T[lo])]}
  /* Interpolated state of every player at time t. */
  state(t){
    const out=[];if(!this.data)return out;const [i,j,k]=this.index(t);
    for(const [id,q] of Object.entries(this.data.players)){
      let a=i,b=j,kk=k;if(q.x[a]==null&&q.x[b]!=null)a=b;if(q.x[b]==null)b=a;if(q.x[a]==null)continue;
      const alive=(q.hp[a]||0)>0,canLerp=alive&&(q.hp[b]||0)>0&&b!==a;
      const x=canLerp?lerp(q.x[a],q.x[b],kk):q.x[a],y=canLerp?lerp(q.y[a],q.y[b],kk):q.y[a],z=canLerp?lerp(q.z[a],q.z[b],kk):q.z[a];
      const yaw=q.yaw[a]==null?null:canLerp&&q.yaw[b]!=null?lerpYaw(q.yaw[a],q.yaw[b],kk):q.yaw[a];
      out.push({id,side:q.side,x,y,z,yaw,alive,hp:q.hp[a]||0,armor:q.ar[a]||0,weapon:q.w[a]>=0?this.data.weapons[q.w[a]]:null,flash:q.fl?.[a]||0,kit:!!q.kit,helmet:!!q.hm});
    }
    return out;
  }
  px(x,y){const r=this.radar;return [(x-r.pos_x)/r.scale,(r.pos_y-y)/r.scale]}
  onFloor(z){const r=this.radar;if(!r?.lower_url||z==null)return true;return this.floor==='lower'?z<r.floor_split_z:z>=r.floor_split_z}
  geom(){const d=devicePixelRatio||1,W=this.c.clientWidth,H=this.c.clientHeight;if(this.c.width!==Math.round(W*d)||this.c.height!==Math.round(H*d)){this.c.width=Math.round(W*d);this.c.height=Math.round(H*d)}
    const s=Math.min(W,H)/this.view[2];return {d,W,H,s,ox:(W-this.view[2]*s)/2-this.view[0]*s,oy:(H-this.view[3]*s)/2-this.view[1]*s}}
  toRadar(sx,sy){const g=this.geom();return [(sx-g.ox)/g.s,(sy-g.oy)/g.s]}
  draw(t){
    const ctx=this.ctx,g=this.geom();ctx.setTransform(g.d,0,0,g.d,0,0);ctx.clearRect(0,0,g.W,g.H);
    if(!this.radar||!this.data)return;
    ctx.setTransform(g.d*g.s,0,0,g.d*g.s,g.d*g.ox,g.d*g.oy);const k=1/g.s,S=this.radar.scale;
    const im=this.images[this.floor]||this.images.upper;
    if(im?.complete&&im.naturalWidth){ctx.filter='grayscale(1) sepia(.15) brightness(.55) contrast(.95)';ctx.drawImage(im,0,0,1024,1024);ctx.filter='none'}
    const players=this.state(t);this.lastState=players;const pos=Object.fromEntries(players.map(p=>[p.id,p])),dim=id=>this.clip&&this.clip.players?.length&&!this.clip.players.includes(id);
    // fires
    for(const f of this.data.fires){if(t<f.t||t>f.end||!f.p||!this.onFloor(f.p[2]))continue;const [u,v]=this.px(f.p[0],f.p[1]),age=t-f.t,life=f.end-f.t,a=Math.min(1,age/.4)*Math.min(1,(f.end-t)/.8),R=FIRE_R/S*Math.min(1,.4+age/1.2);
      for(let n=0;n<14;n++){const ang=hash(n+f.t)*6.283,rr=R*Math.sqrt(hash(n*7+f.t)),fl=.6+.4*Math.sin(t*9+n*1.7);const x=u+Math.cos(ang)*rr,y=v+Math.sin(ang)*rr;
        const gr=ctx.createRadialGradient(x,y,0,x,y,R*.45);gr.addColorStop(0,`rgba(255,${150+60*fl|0},60,${.55*a*fl})`);gr.addColorStop(1,'rgba(255,60,20,0)');ctx.fillStyle=gr;ctx.beginPath();ctx.arc(x,y,R*.45,0,6.283);ctx.fill()}}
    // smokes
    for(const s of this.data.smokes){if(t<s.t||t>s.end||!s.p||!this.onFloor(s.p[2]))continue;const [u,v]=this.px(s.p[0],s.p[1]),age=t-s.t,a=Math.min(1,age/.7)*Math.min(1,(s.end-t)/1.5),R=SMOKE_R/S*(.55+.45*Math.min(1,age/1.2));
      for(let n=0;n<7;n++){const ang=hash(n+s.t*3)*6.283,off=R*.35*hash(n*5+s.t),x=u+Math.cos(ang+t*.05)*off,y=v+Math.sin(ang+t*.05)*off,rr=R*(.62+.25*hash(n*3+s.t));
        const gr=ctx.createRadialGradient(x,y,rr*.2,x,y,rr);gr.addColorStop(0,`rgba(196,201,207,${.36*a})`);gr.addColorStop(.7,`rgba(180,186,193,${.22*a})`);gr.addColorStop(1,'rgba(180,186,193,0)');ctx.fillStyle=gr;ctx.beginPath();ctx.arc(x,y,rr,0,6.283);ctx.fill()}
      ctx.strokeStyle=`rgba(236,230,214,${.35*a})`;ctx.lineWidth=1*k;ctx.setLineDash([3*k,3*k]);ctx.beginPath();ctx.arc(u,v,R,0,6.283);ctx.stroke();ctx.setLineDash([])}
    // trails
    if(this.trail>0)for(const [id,q] of Object.entries(this.data.players)){const [i0]=this.index(Math.max(0,t-this.trail)),[i1]=this.index(t);ctx.beginPath();let st=false;
      for(let i=i0;i<=i1;i++){if(q.x[i]==null||!(q.hp[i]>0)||!this.onFloor(q.z[i])){st=false;continue}const [u,v]=this.px(q.x[i],q.y[i]);if(!st){ctx.moveTo(u,v);st=true}else ctx.lineTo(u,v)}
      ctx.strokeStyle=COLORS[q.side];ctx.globalAlpha=dim(id)?.06:id===this.selected?.6:.22;ctx.lineWidth=(id===this.selected?2.2:1.4)*k;ctx.stroke();ctx.globalAlpha=1}
    // grenades in flight (parser projectile tracks)
    for(const gnd of this.data.grenades){const tr=gnd.trajectory,t0=tr[0][0],t1=tr[tr.length-1][0];if(t<t0||t>t1)continue;
      let i=0;while(i<tr.length-2&&tr[i+1][0]<t)i++;const a=tr[i],b=tr[i+1],kk=Math.max(0,Math.min(1,(t-a[0])/Math.max(1e-6,b[0]-a[0])));const x=lerp(a[1],b[1],kk),y=lerp(a[2],b[2],kk),z=lerp(a[3],b[3],kk);
      // A smoke/decoy at rest is no longer "in flight": hide it once it has not moved for ~0.3 s.
      const back=tr[Math.max(0,i-4)];if(t-back[0]>.2&&Math.hypot(x-back[1],y-back[2])<4)continue;
      if(!this.onFloor(z))continue;ctx.beginPath();let st=false;for(const q of tr){if(q[0]>t)break;if(q[0]<t-.7)continue;const [u,v]=this.px(q[1],q[2]);if(!st){ctx.moveTo(u,v);st=true}else ctx.lineTo(u,v)}
      const [u,v]=this.px(x,y);ctx.lineTo(u,v);ctx.strokeStyle=NADE[gnd.kind]||'#ddd';ctx.globalAlpha=.75;ctx.lineWidth=1.3*k;ctx.setLineDash([4*k,3*k]);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;
      ctx.fillStyle=NADE[gnd.kind]||'#ddd';ctx.strokeStyle='#111';ctx.lineWidth=1.2*k;ctx.beginPath();ctx.arc(u,v,3.2*k,0,6.283);ctx.fill();ctx.stroke()}
    // bursts: flash / HE
    for(const e of this.data.events){const age=t-e.t;if(age<0)break;if(age>.6||!e.p||!this.onFloor(e.p[2]))continue;const [u,v]=this.px(e.p[0],e.p[1]);
      if(e.k==='flashbang_detonate'&&age<.45){const r=FLASH_R/S*(.2+age/.45),a=1-age/.45;const gr=ctx.createRadialGradient(u,v,0,u,v,r);gr.addColorStop(0,`rgba(255,252,235,${.85*a})`);gr.addColorStop(1,'rgba(255,252,235,0)');ctx.fillStyle=gr;ctx.beginPath();ctx.arc(u,v,r,0,6.283);ctx.fill()}
      if(e.k==='hegrenade_detonate'&&age<.6){const r=HE_R/S*(.15+age/.6),a=1-age/.6;ctx.strokeStyle=`rgba(255,120,60,${a})`;ctx.lineWidth=3*k*a+.5*k;ctx.beginPath();ctx.arc(u,v,r,0,6.283);ctx.stroke();ctx.fillStyle=`rgba(255,170,90,${.35*a})`;ctx.beginPath();ctx.arc(u,v,r*.55,0,6.283);ctx.fill()}}
    // shots (tracer along the view yaw at fire time) and hits
    for(const e of this.data.events){const age=t-e.t;if(age<0)break;
      if(e.k==='weapon_fire'&&age<=SHOT_LIFE&&e.p&&this.onFloor(e.p[2])){const [u,v]=this.px(e.p[0],e.p[1]),yaw=(e.yaw??pos[e.a]?.yaw??0)*Math.PI/180,L=SHOT_LEN/S,a=1-age/SHOT_LIFE,side=this.data.players[e.a]?.side;
        const gr=ctx.createLinearGradient(u,v,u+Math.cos(yaw)*L,v-Math.sin(yaw)*L);gr.addColorStop(0,`rgba(255,240,190,${.95*a})`);gr.addColorStop(1,side==='CT'?'rgba(98,182,230,0)':'rgba(240,179,74,0)');
        ctx.strokeStyle=gr;ctx.lineWidth=2.2*k;ctx.beginPath();ctx.moveTo(u,v);ctx.lineTo(u+Math.cos(yaw)*L,v-Math.sin(yaw)*L);ctx.stroke();
        ctx.fillStyle=`rgba(255,236,170,${a})`;ctx.beginPath();ctx.arc(u+Math.cos(yaw)*8*k,v-Math.sin(yaw)*8*k,3.4*k,0,6.283);ctx.fill()}
      if(e.k==='player_hurt'&&age<=HIT_LIFE){const vic=pos[e.a];if(!vic||!this.onFloor(vic.z))continue;const [u,v]=this.px(vic.x,vic.y),a=1-age/HIT_LIFE;
        if(e.from&&age<.15){const [fu,fv]=this.px(e.from[0],e.from[1]);ctx.strokeStyle=`rgba(255,80,60,${.6*(1-age/.15)})`;ctx.lineWidth=1*k;ctx.beginPath();ctx.moveTo(fu,fv);ctx.lineTo(u,v);ctx.stroke()}
        ctx.strokeStyle=`rgba(252,61,33,${a})`;ctx.lineWidth=2*k;ctx.beginPath();ctx.arc(u,v,(9+age*18)*k,0,6.283);ctx.stroke();
        ctx.font=`700 ${11*k}px "Space Mono",monospace`;ctx.fillStyle=`rgba(255,120,100,${a})`;ctx.fillText('-'+e.d,u+9*k,v-10*k-age*22*k)}}
    // bomb
    const pl=this.data.plant;if(pl&&t>=pl.t&&pl.p&&this.onFloor(pl.p[2])){const [u,v]=this.px(pl.p[0],pl.p[1]),left=BOMB_TIME-(t-pl.t),done=(this.data.defuse&&t>=this.data.defuse.t)||(this.data.boom&&t>=this.data.boom.t);
      const blink=done?1:(Math.sin((t-pl.t)*Math.PI*2*(1+3*(1-Math.max(0,left)/BOMB_TIME)))>0?1:.35);
      if(this.data.boom&&t>=this.data.boom.t&&t-this.data.boom.t<1.2){const a=1-(t-this.data.boom.t)/1.2;ctx.fillStyle=`rgba(255,120,40,${.35*a})`;ctx.beginPath();ctx.arc(u,v,(500/S)*(1-a*.6),0,6.283);ctx.fill()}
      ctx.fillStyle=this.data.defuse&&t>=this.data.defuse.t?'#62b6e6':`rgba(252,61,33,${blink})`;ctx.fillRect(u-5*k,v-4*k,10*k,8*k);ctx.strokeStyle='#111';ctx.lineWidth=1*k;ctx.strokeRect(u-5*k,v-4*k,10*k,8*k)}
    // players
    for(const p of players){if(!this.onFloor(p.z))continue;const [u,v]=this.px(p.x,p.y),col=COLORS[p.side],sel=p.id===this.selected,hov=p.id===this.hover;ctx.globalAlpha=dim(p.id)?.28:1;
      if(!p.alive){ctx.strokeStyle=COLORS.dead;ctx.lineWidth=2*k;ctx.beginPath();ctx.moveTo(u-4*k,v-4*k);ctx.lineTo(u+4*k,v+4*k);ctx.moveTo(u+4*k,v-4*k);ctx.lineTo(u-4*k,v+4*k);ctx.stroke();ctx.globalAlpha=1;continue}
      if(p.yaw!=null){const a=p.yaw*Math.PI/180,L=(sel?46:30)*k;ctx.fillStyle=col;ctx.globalAlpha*=sel?.28:.16;ctx.beginPath();ctx.moveTo(u,v);ctx.arc(u,v,L,-a-.5,-a+.5);ctx.closePath();ctx.fill();ctx.globalAlpha=dim(p.id)?.28:1}
      if(p.flash>.05){const fa=Math.min(1,p.flash/2.5);ctx.fillStyle=`rgba(255,255,240,${.75*fa})`;ctx.beginPath();ctx.arc(u,v,11*k,0,6.283);ctx.fill()}
      ctx.fillStyle=col;ctx.strokeStyle=sel?'#fff':'#0a0b0d';ctx.lineWidth=(sel?2.2:1.6)*k;ctx.beginPath();ctx.arc(u,v,(sel||hov?6.4:5.4)*k,0,6.283);ctx.fill();ctx.stroke();
      // hp arc
      ctx.strokeStyle=p.hp>50?'#82d68f':p.hp>20?'#ffb23f':'#fc3d21';ctx.lineWidth=1.6*k;ctx.beginPath();ctx.arc(u,v,8.6*k,-Math.PI/2,-Math.PI/2+6.283*p.hp/100);ctx.stroke();
      ctx.font=`600 ${9.5*k}px "Space Mono",monospace`;const label=(this.names[p.id]||p.id).slice(0,14);const w=ctx.measureText(label).width;ctx.fillStyle='rgba(8,9,11,.78)';ctx.fillRect(u-w/2-3*k,v-22*k,w+6*k,12*k);ctx.fillStyle=sel?'#fff':col;ctx.fillText(label,u-w/2,v-13*k);
      // weapon in hand, drawn above the name like the in-game spectator HUD (white game icon)
      const im=this.icon(p.weapon);if(im){const h=8*k,iw=h*im.naturalWidth/Math.max(1,im.naturalHeight);ctx.globalAlpha*=.92;ctx.drawImage(im,u-iw/2,v-33*k,iw,h)}ctx.globalAlpha=1}
  }
  pick(sx,sy){const g=this.geom();let best=null,bd=14;for(const p of this.lastState||[]){if(!this.onFloor(p.z))continue;const [u,v]=this.px(p.x,p.y),d=Math.hypot(u*g.s+g.ox-sx,v*g.s+g.oy-sy);if(d<bd){bd=d;best=p}}return best}
}
window.ReplayEngine=Engine;
})();
