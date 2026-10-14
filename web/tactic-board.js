/* Tactic board editor on the review map's SVG layer. A user plan, never match evidence.
   Stage = {players:[{id,side,position:[x,y,z]}], items:[{type,pts:[[u,v]...],color,text}], note}; items use radar pixels. */
(()=>{
const NS='http://www.w3.org/2000/svg',E=id=>document.getElementById(id);
const UTIL={smoke:{r:144,icon:'smokegrenade',fill:'rgba(207,211,216,.28)',stroke:'#cfd3d8'},flash:{r:60,icon:'flashbang',fill:'rgba(255,246,176,.25)',stroke:'#fff6b0'},
  fire:{r:110,icon:'molotov',fill:'rgba(255,122,40,.25)',stroke:'#ff9a3d'},he:{r:90,icon:'hegrenade',fill:'rgba(255,90,70,.16)',stroke:'#ff6a4a'}};
const COLORS=['#ffb23f','#fc3d21','#62b6e6','#82d68f','#ece6d6'];
let roomId=null,standalone=null,st=null,cur=0,tool='move',color=COLORS[0],sel=null,undo=[],redo=[],drag=null,meta={},anim=null,iconsReady=false;
function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(parent)parent.append(e);return e}
function stage(){return st[cur]}
function snapshot(){undo.push(JSON.stringify({st,cur}));if(undo.length>60)undo.shift();redo=[]}
function restore(from,to){if(!from.length)return;to.push(JSON.stringify({st,cur}));const s=JSON.parse(from.pop());st=s.stages||s.st;cur=Math.min(s.cur,st.length-1);setBoard(st);sync();render()}
function xy(p){return [(p[0]-radar.pos_x)/radar.scale,(radar.pos_y-p[1])/radar.scale]}
function world(u,v,z){return [u*radar.scale+radar.pos_x,radar.pos_y-v*radar.scale,z??0]}
function setBoard(v){board=v}
/* Floors (e.g. Nuke): players keep a height on their floor, items carry a floor tag; the floor selector decides what is editable. */
function hasFloors(){return !!(radar?.lower_url&&radar.floor_split_z!=null)}
function curFloor(){return hasFloors()&&$('floor').value==='lower'?'lower':'upper'}
function floorZ(f){return hasFloors()?(f==='lower'?radar.floor_split_z-80:radar.floor_split_z+40):0}
function floorOfZ(z){return hasFloors()&&z!=null&&z<radar.floor_split_z?'lower':'upper'}
function itemFloor(it){return hasFloors()?(it.floor||'upper'):'upper'} // demo-review.js owns `board`; non-null switches the page into editor mode

/* Inline the game icons as <symbol>s so the export (SVG → PNG) keeps them. */
async function loadIcons(){if(iconsReady)return;const defs=svg('defs',{id:'tbDefs'});
  const marker=svg('marker',{id:'tbArrow',viewBox:'0 0 10 10',refX:'7',refY:'5',markerWidth:'4',markerHeight:'4',orient:'auto-start-reverse'},defs);svg('path',{d:'M0,0 L10,5 L0,10 z',fill:'context-stroke'},marker);
  for(const k of Object.values(UTIL).map(u=>u.icon)){try{const txt=await (await fetch('/icons/'+k+'.svg')).text();const doc=new DOMParser().parseFromString(txt,'image/svg+xml').documentElement;
    const sym=svg('symbol',{id:'ic-'+k,viewBox:doc.getAttribute('viewBox')||'0 0 32 32'},defs);for(const n of [...doc.childNodes])if(n.nodeType===1)sym.append(document.importNode(n,true));
    sym.querySelectorAll('*').forEach(n=>{n.removeAttribute('fill');n.removeAttribute('style')})}catch{}}
  E('map').prepend(defs);iconsReady=true}

function open(players,info){roomId=null;meta=info||{};st=[{players:players.map(p=>({id:p.id,side:p.side,position:[p.x??p.position[0],p.y??p.position[1],p.z??p.position[2]]})),items:[],note:''}];cur=0;undo=[];redo=[];sel=null;
  setBoard(st);E('editing').hidden=false;loadIcons().then(render);sync();window.render()}
function load(saved){roomId=saved.kind==='user_tactic_plan'?saved.id:null;if(saved.source){meta={source_round:saved.source.round,source_tick:saved.source.tick,source_match:saved.source.match}}st=saved.steps.map(s=>({players:s.players||[],items:(s.items||[]).concat((s.lines||[]).map(l=>({type:'arrow',pts:[[l[0],l[1]],[l[2],l[3]]],color:'#ece6d6'}))),note:s.note||'',dur:s.dur}));cur=0;undo=[];redo=[];
  if(!saved.source)meta={source_round:saved.steps[0]?.source_round,source_tick:saved.steps[0]?.source_tick};E('boardName').value=saved.name;setBoard(st);E('editing').hidden=false;loadIcons().then(render);sync();window.render()}
function close(){if(playback)stopPlayback();stopAnim();st=null;setBoard(null);E('editing').hidden=true;E('markers').replaceChildren();E('ink').replaceChildren();const back=standalone;standalone=null;if(back){document.body.classList.remove('board-only');window.showView?.('room');window.PlayerHub?.refreshRoom()}else window.render?.()}

/* ---------- rendering ---------- */
function render(){if(!st||!radar)return;const ink=E('ink'),mk=E('markers');ink.replaceChildren();mk.replaceChildren();const s=anim?anim.frame:stage();
  const k=view[2]/1024; // keep strokes readable at any zoom
  for(const [i,it] of s.items.entries()){const off=itemFloor(it)!==curFloor(),g=svg('g',{'data-item':i,class:'tb-item'+(sel?.kind==='item'&&sel.i===i?' sel':'')+(off?' off-floor':'')},ink);
    if(it.type==='arrow'||it.type==='pen'){const d=it.pts.map((p,j)=>(j?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
      svg('path',{d,fill:'none',stroke:'#0a0b0d','stroke-width':7*k,'stroke-linecap':'round','stroke-linejoin':'round',opacity:.5},g);
      svg('path',{d,fill:'none',stroke:it.color,'stroke-width':3.6*k,'stroke-linecap':'round','stroke-linejoin':'round','marker-end':it.type==='arrow'?'url(#tbArrow)':'','stroke-dasharray':it.dash?`${10*k} ${7*k}`:''},g)}
    else if(UTIL[it.type]){const u=UTIL[it.type],[x,y]=it.pts[0],r=u.r/radar.scale;svg('circle',{cx:x,cy:y,r,fill:u.fill,stroke:u.stroke,'stroke-width':1.6*k,'stroke-dasharray':`${5*k} ${4*k}`},g);
      svg('use',{href:'#ic-'+u.icon,x:x-9*k,y:y-9*k,width:18*k,height:18*k,fill:u.stroke},g)}
    else if(it.type==='text'){const t=svg('text',{x:it.pts[0][0],y:it.pts[0][1],fill:it.color,'font-size':15*k,'font-family':'Space Mono,monospace','font-weight':700,'paint-order':'stroke',stroke:'#0a0b0d','stroke-width':4*k},g);t.textContent=it.text}}
  for(const p of s.players){const off=floorOfZ(p.position[2])!==curFloor();const [x,y]=xy(p.position),col=p.side==='T'?'#f0b34a':'#62b6e6',g=svg('g',{'data-player':p.id,class:'tb-player'+(sel?.kind==='player'&&sel.id===p.id?' sel':'')+(off?' off-floor':'')},mk);
    svg('circle',{cx:x,cy:y,r:11*k,fill:col,stroke:sel?.kind==='player'&&sel.id===p.id?'#fff':'#0a0b0d','stroke-width':2.4*k},g);
    const lb=svg('text',{x,y:y+4*k,'text-anchor':'middle','font-size':10*k,'font-weight':700,'font-family':'Space Mono,monospace',fill:'#0a0b0d'},g);lb.textContent=p.id.replace(/^[A-Z]+/,'').replace(/·.*$/,'')||p.id;
    const name=window.playerNameOf?.(p.id);if(name&&name!==p.id){const nt=svg('text',{x,y:y+24*k,'text-anchor':'middle','font-size':10*k,'font-weight':600,'font-family':'Space Mono,monospace',fill:col,'paint-order':'stroke',stroke:'#0a0b0d','stroke-width':3*k},g);nt.textContent=name.slice(0,12)}}
  if(drag?.preview){const p=drag.preview;svg('path',{d:p.map((q,j)=>(j?'L':'M')+q[0]+' '+q[1]).join(' '),fill:'none',stroke:color,'stroke-width':3.6*k,'stroke-linecap':'round','marker-end':tool==='arrow'?'url(#tbArrow)':''},ink)}
  E('map').setAttribute('viewBox',view.join(' '));}

/* ---------- pointer ---------- */
function hit(e){if(e.target.closest?.('.off-floor'))return null;const p=e.target.closest?.('[data-player]');if(p)return {kind:'player',id:p.dataset.player};const it=e.target.closest?.('[data-item]');if(it)return {kind:'item',i:+it.dataset.item};return null}
function down(e,pt){if(!st||anim)return false;const h=hit(e);
  if(e.button===1||e.button===2||tool==='pan'){drag={pan:true,cx:e.clientX,cy:e.clientY,view:[...view]};return true}
  if(tool==='move'){sel=h;if(h){snapshot();drag={move:h,last:pt}}else drag={pan:true,cx:e.clientX,cy:e.clientY,view:[...view]};render();return true}
  if(tool==='erase'){if(h){snapshot();if(h.kind==='item')stage().items.splice(h.i,1);else stage().players=stage().players.filter(p=>p.id!==h.id);sel=null;render()}return true}
  if(tool==='arrow'||tool==='pen'){drag={draw:true,pts:[pt]};drag.preview=drag.pts;return true}
  if(UTIL[tool]){snapshot();stage().items.push({type:tool,pts:[pt],color,...(hasFloors()?{floor:curFloor()}:{})});render();return true}
  if(tool==='text'){const text=prompt(t('标注文字'),'');if(text){snapshot();stage().items.push({type:'text',pts:[pt],color,text:text.slice(0,80),...(hasFloors()?{floor:curFloor()}:{})});render()}return true}
  if(tool==='addT'||tool==='addCT'){const side=tool==='addT'?'T':'CT',n=stage().players.filter(p=>p.id.startsWith(side==='T'?'T':'C')).length+1;snapshot();
    stage().players.push({id:(side==='T'?'T':'CT')+n+'·'+Date.now().toString(36).slice(-3),side,position:world(pt[0],pt[1],floorZ(curFloor()))});render();return true}
  return true}
function move(e,pt){if(!drag)return false;
  if(drag.pan){const r=E('map').getBoundingClientRect(),k=view[2]/Math.min(r.width,r.height);view[0]=drag.view[0]-(e.clientX-drag.cx)*k;view[1]=drag.view[1]-(e.clientY-drag.cy)*k;render();return true}
  if(drag.move){const dx=pt[0]-drag.last[0],dy=pt[1]-drag.last[1];drag.last=pt;const s=stage();
    if(drag.move.kind==='player'){const p=s.players.find(p=>p.id===drag.move.id);if(p){const [x,y]=xy(p.position);p.position=world(x+dx,y+dy,hasFloors()&&floorOfZ(p.position[2])!==curFloor()?floorZ(curFloor()):p.position[2])}}
    else{const it=s.items[drag.move.i];it.pts=it.pts.map(q=>[q[0]+dx,q[1]+dy])}render();return true}
  if(drag.draw){if(tool==='arrow')drag.pts=[drag.pts[0],pt];else{const l=drag.pts.at(-1);if(Math.hypot(pt[0]-l[0],pt[1]-l[1])>3*view[2]/1024)drag.pts.push(pt)}drag.preview=drag.pts;render();return true}
  return true}
function up(){if(!drag)return false;const d=drag;drag=null;
  if(d.draw&&d.pts.length>=2&&Math.hypot(d.pts.at(-1)[0]-d.pts[0][0],d.pts.at(-1)[1]-d.pts[0][1])>4*view[2]/1024){snapshot();stage().items.push({type:tool,pts:d.pts.map(q=>[+q[0].toFixed(1),+q[1].toFixed(1)]),color,...(hasFloors()?{floor:curFloor()}:{})})}
  render();return true}
function key(e){if(!st||/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName))return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?restore(redo,undo):restore(undo,redo);return}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();restore(redo,undo);return}
  if((e.key==='Delete'||e.key==='Backspace')&&sel){snapshot();if(sel.kind==='item')stage().items.splice(sel.i,1);else stage().players=stage().players.filter(p=>p.id!==sel.id);sel=null;render();return}
  const map={v:'move',a:'arrow',p:'pen',t:'text',s:'smoke',f:'flash',m:'fire',h:'he',e:'erase'};if(!e.ctrlKey&&map[e.key])setTool(map[e.key])}
document.addEventListener('keydown',key);

/* ---------- stages and playback ---------- */
function sync(){if(!st)return;const root=E('tbStages');root.replaceChildren(...st.map((s,i)=>{const b=document.createElement('button');b.textContent=t('阶段 ')+(i+1);b.setAttribute('aria-pressed',String(i===cur));b.onclick=()=>{stopAnim();cur=i;sel=null;E('note').value=st[cur].note||'';sync();render()};return b}));
  E('note').value=stage().note||'';E('tbDur').value=durOf(stage());E('tbDelStage').disabled=st.length<2;E('addStage').disabled=st.length>=8;
  document.querySelectorAll('#tbTools [data-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===tool)));
  document.querySelectorAll('#tbColors button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.color===color)))}
function setTool(x){tool=x;sel=null;E('map').classList.toggle('tb-draw',x!=='move');sync();render()}
function stopAnim(){if(anim){cancelAnimationFrame(anim.raf);anim=null;E('tbPlay').textContent=t('▶ 演示');render()}}
function play(){if(anim){stopAnim();return}if(st.length<2)return;const DUR=1600;let from=0,start=performance.now();E('tbPlay').textContent=t('■ 停止');
  const step=now=>{const k=Math.min(1,(now-start)/DUR),a=st[from],b=st[from+1],e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
    const players=b.players.map(p=>{const q=a.players.find(x=>x.id===p.id);if(!q)return p;return {...p,position:p.position.map((v,i)=>q.position[i]+(v-q.position[i])*e)}});
    anim.frame={players,items:k<.35?a.items:b.items};cur=from;render();
    if(k>=1){from++;start=now;if(from>=st.length-1){cur=st.length-1;anim=null;E('tbPlay').textContent=t('▶ 演示');sync();render();return}}
    anim.raf=requestAnimationFrame(step)};anim={frame:st[0]};anim.raf=requestAnimationFrame(step)}

/* ---------- playable tactic: stages → a replay track for the same engine as the demo review ---------- */
const HZ=16,DEF_DUR=4,LIFE={smoke:18,fire:7,flash:0,he:0},KIND_EVENT={smoke:'smokegrenade_detonate',fire:'inferno_startburn',flash:'flashbang_detonate',he:'hegrenade_detonate'};
let playback=null;
function durOf(s){return Math.max(.5,Math.min(30,+s.dur||DEF_DUR))}
function polyLen(p){let L=0;for(let i=1;i<p.length;i++)L+=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]);return L}
function along(p,f){const L=polyLen(p)*f;let acc=0;for(let i=1;i<p.length;i++){const d=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]);if(acc+d>=L){const k=d?(L-acc)/d:0;return [p[i-1][0]+(p[i][0]-p[i-1][0])*k,p[i-1][1]+(p[i][1]-p[i-1][1])*k]}acc+=d}return p[p.length-1]}
const ease=k=>k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
function buildPlayback(){
  const starts=[];let T=0;for(const s of st){starts.push(T);T+=durOf(s)}const total=T,n=Math.floor(total*HZ)+1,times=Array.from({length:n},(_,i)=>+(i/HZ).toFixed(3));
  const ids=[...new Set(st.flatMap(s=>s.players.map(p=>p.id)))],players={},names={};
  for(const id of ids){
    const side=st.find(s=>s.players.some(p=>p.id===id)).players.find(p=>p.id===id).side,q={side,x:[],y:[],z:[],yaw:[],hp:[],ar:[],w:[],fl:[]};
    names[id]=window.playerNameOf?.(id)!==id&&window.playerNameOf?.(id)||id.replace(/·.*$/,'');
    // a movement path is an arrow/pen whose first point starts on the player in that stage
    const seg=st.map((s,k)=>{const p=s.players.find(x=>x.id===id),nx=st[k+1]?.players.find(x=>x.id===id);if(!p)return null;const a=xy(p.position);
      const path=s.items.find(it=>(it.type==='arrow'||it.type==='pen')&&Math.hypot(it.pts[0][0]-a[0],it.pts[0][1]-a[1])<22*view[2]/1024);
      const b=nx?xy(nx.position):null;let pts=null;if(path){pts=[a,...path.pts.slice(1)];if(b&&Math.hypot(b[0]-a[0],b[1]-a[1])>2)pts.push(b)}else if(b)pts=[a,b];return {a,pts,z:p.position[2]??floorZ(curFloor()),alive:true}});
    let lastYaw=null;
    for(const t of times){let k=starts.findIndex((s0,i)=>t>=s0&&t<s0+durOf(st[i]));if(k<0)k=st.length-1;const g=seg[k];
      if(!g){const prev=seg.slice(0,k).reverse().find(Boolean);if(prev){const w=world(...(prev.pts?prev.pts[prev.pts.length-1]:prev.a),prev.z);q.x.push(w[0]);q.y.push(w[1]);q.z.push(w[2]);q.yaw.push(lastYaw);q.hp.push(0)}else{q.x.push(null);q.y.push(null);q.z.push(null);q.yaw.push(null);q.hp.push(null)}}
      else{const f=g.pts&&polyLen(g.pts)>1?ease(Math.min(1,(t-starts[k])/durOf(st[k]))):0,pos=f?along(g.pts,f):g.a,ahead=g.pts?along(g.pts,Math.min(1,f+.04)):pos;
        if(Math.hypot(ahead[0]-pos[0],ahead[1]-pos[1])>.3)lastYaw=Math.atan2(-(ahead[1]-pos[1]),ahead[0]-pos[0])*180/Math.PI;
        const w=world(pos[0],pos[1],g.z);q.x.push(w[0]);q.y.push(w[1]);q.z.push(w[2]);q.yaw.push(lastYaw);q.hp.push(100)}
      q.ar.push(100);q.w.push(-1);q.fl.push(0)}
    players[id]=q}
  // utility: an item keeps its identity across copied stages (same type + spot); it pops when it first appears
  const events=[],grenades=[],seen=new Map();
  st.forEach((s,k)=>{for(const it of s.items){if(!KIND_EVENT[it.type])continue;const key=it.type+':'+it.pts[0].map(v=>Math.round(v)).join(',');
    if(!seen.has(key))seen.set(key,{it,first:k,last:k});else seen.get(key).last=k}});
  for(const {it,first,last} of seen.values()){const t0=starts[first]+.6,p=world(it.pts[0][0],it.pts[0][1],floorZ(itemFloor(it))),end=!LIFE[it.type]?t0:last===st.length-1?total+30:Math.max(t0+2,starts[last]+durOf(st[last]));  // still on the board at the end → stays visible
    events.push({k:KIND_EVENT[it.type],t:t0,p,e:key(it)});if(it.type==='smoke')events.push({k:'smokegrenade_expired',t:end,p,e:key(it)});if(it.type==='fire')events.push({k:'inferno_expire',t:end,p,e:key(it)});
    // illustrative throw from the nearest player at that moment (plan, not a computed lineup)
    const i0=Math.round((t0-.6)*HZ);let thrower=null,bd=1e9;for(const q of Object.values(players)){if(q.x[i0]==null||!(q.hp[i0]>0))continue;const d=Math.hypot(q.x[i0]-p[0],q.y[i0]-p[1]);if(d<bd){bd=d;thrower=q}}
    if(thrower&&bd>60){const a=[thrower.x[i0],thrower.y[i0]],traj=[];for(let j=0;j<=10;j++){const f=j/10;traj.push([+(t0-.6+f*.6).toFixed(3),a[0]+(p[0]-a[0])*f,a[1]+(p[1]-a[1])*f,p[2]])}grenades.push({kind:it.type,trajectory:traj})}}
  function key(it){return it.type+':'+it.pts[0].map(v=>Math.round(v)).join(',')}
  events.sort((a,b)=>a.t-b.t);
  return {round:{number:0,duration:total,frames:[],events:[],start_tick:0},replay:{times,players,weapons:[],events,grenades,names,hz:HZ},starts}}
function startPlayback(){if(!st||!radar)return;stopAnim();stage().note=E('note').value;
  const pb=buildPlayback();playback={saved:{round,replayData,seconds,clip,names:engine.names},starts:pb.starts};
  E('editing').hidden=true;setBoard(null);E('markers').replaceChildren();
  round=pb.round;replayData=pb.replay;engine.setRound(pb.round,pb.replay);engine.names=pb.replay.names;engine.selected=null;clip=null;seconds=0;
  $('timeline').max=pb.round.duration;$('roundStrip').replaceChildren();$('eventTicks').replaceChildren(...pb.starts.map((s0,i)=>{const b=document.createElement('button');b.className='tick plant';b.style.left=(s0/pb.round.duration*100)+'%';b.title=t('阶段 ')+(i+1);b.onclick=()=>{seconds=s0;dirty=true;updateUi(true)};return b}));
  $('replaySource').textContent=t('战术演示 · 计划示意，不是比赛数据');document.body.classList.add('tb-playback');E('tbBackToEdit').hidden=false;
  playing=true;window.render();drawPlaybackInk()}  // page renderer (switches to the canvas replay layer)
function drawPlaybackInk(){if(!playback)return;$('replayCanvas').hidden=false;const k=playback.starts.findLastIndex(s0=>seconds>=s0);const saveSel=sel;sel=null;
  const ink=E('ink');ink.replaceChildren();const s=st[Math.max(0,k)],z=view[2]/1024;
  for(const it of s.items){if(itemFloor(it)!==curFloor())continue;if(it.type==='text'){const tx=document.createElementNS(NS,'text');tx.setAttribute('x',it.pts[0][0]);tx.setAttribute('y',it.pts[0][1]);tx.setAttribute('fill',it.color);tx.setAttribute('font-size',15*z);tx.setAttribute('font-family','Space Mono,monospace');tx.setAttribute('paint-order','stroke');tx.setAttribute('stroke','#0a0b0d');tx.setAttribute('stroke-width',4*z);tx.textContent=it.text;ink.append(tx)}
    else if(it.type==='arrow'||it.type==='pen'){const pth=document.createElementNS(NS,'path');pth.setAttribute('d',it.pts.map((p,j)=>(j?'L':'M')+p[0]+' '+p[1]).join(' '));pth.setAttribute('fill','none');pth.setAttribute('stroke',it.color);pth.setAttribute('stroke-width',2.4*z);pth.setAttribute('opacity','.35');pth.setAttribute('stroke-dasharray',`${8*z} ${6*z}`);ink.append(pth)}}
  E('tbStageLabel').textContent=t('阶段 ')+(k+1)+' / '+st.length+(s.note?' · '+s.note:'');sel=saveSel;
  requestAnimationFrame(()=>{if(playback)drawPlaybackInk()})}
function stopPlayback(){if(!playback)return;const sv=playback.saved;playback=null;playing=false;document.body.classList.remove('tb-playback');E('tbBackToEdit').hidden=true;E('tbStageLabel').textContent='';
  round=sv.round;replayData=sv.replayData;seconds=sv.seconds;clip=sv.clip;engine.names=sv.names||{};if(round)engine.setRound(round,replayData);
  if(round&&data){renderRounds();renderEventTicks();$('timeline').max=round.duration}
  setBoard(st);E('editing').hidden=false;sync();window.render()}

/* ---------- export ---------- */
async function exportPng(){const size=1600,c=document.createElement('canvas');c.width=c.height=size;const ctx=c.getContext('2d'),[vx,vy,vw]=view,sc=size/vw;
  ctx.fillStyle='#090a0c';ctx.fillRect(0,0,size,size);
  const rim=new Image();rim.src=E('radar').getAttribute('href');await rim.decode().catch(()=>{});ctx.filter='grayscale(1) sepia(.15) brightness(.55)';ctx.drawImage(rim,-vx*sc,-vy*sc,1024*sc,1024*sc);ctx.filter='none';
  const clone=E('map').cloneNode(true);clone.querySelector('#radar')?.remove();clone.setAttribute('width',size);clone.setAttribute('height',size);clone.setAttribute('xmlns',NS);
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml'}));const im=new Image();im.src=url;await im.decode();ctx.drawImage(im,0,0,size,size);URL.revokeObjectURL(url);
  ctx.font='600 22px "Space Mono",monospace';ctx.fillStyle='#ece6d6';ctx.fillText((E('boardName').value||'Tactic board')+' · '+t('阶段 ')+(cur+1),24,40);
  if(stage().note){ctx.font='18px "IBM Plex Sans",sans-serif';ctx.fillStyle='#c9c3b4';ctx.fillText(stage().note.slice(0,120),24,70)}
  const a=document.createElement('a');a.download=(E('boardName').value||'tactic-board').replace(/[\\/:*?"<>|]/g,'_')+'-'+(cur+1)+'.png';a.href=c.toDataURL('image/png');a.click()}

function payload(){return st.map(s=>({source_round:meta.source_round??null,source_tick:meta.source_tick??null,players:s.players.map(p=>({id:p.id,side:p.side,position:p.position.map(v=>+(+v).toFixed(1))})),items:s.items,lines:[],note:s.note||'',dur:durOf(s)}))}

/* ---------- toolbar wiring ---------- */
function wire(){
  const tools=[['move','⬚',t('移动 / 选择 (V)')],['arrow','➚',t('箭头 (A)')],['pen','✎',t('画笔 (P)')],['text','T',t('文字 (T)')],['smoke','',t('烟雾 (S)')],['flash','',t('闪光 (F)')],['fire','',t('燃烧 (M)')],['he','',t('手雷 (H)')],['addT','+T',t('添加 T 队员')],['addCT','+CT',t('添加 CT 队员')],['erase','⌫',t('橡皮 (E)')]];
  E('tbTools').replaceChildren(...tools.map(([k,txt,title])=>{const b=document.createElement('button');b.dataset.tool=k;b.title=title;if(UTIL[k])b.append(CSIcon.el(UTIL[k].icon,'tb-ic'));else b.textContent=txt;b.onclick=()=>setTool(k);return b}));
  E('tbColors').replaceChildren(...COLORS.map(c=>{const b=document.createElement('button');b.dataset.color=c;b.style.background=c;b.title=c;b.onclick=()=>{color=c;if(sel?.kind==='item'){snapshot();stage().items[sel.i].color=c}sync();render()};return b}));
  E('tbUndo').onclick=()=>restore(undo,redo);E('tbRedo').onclick=()=>restore(redo,undo);
  E('addStage').onclick=()=>{if(st.length>=8)return;snapshot();const next=structuredClone(stage()),used=new Set();
    // a route drawn from a player is "played": in the next stage the player starts at its end and the route is consumed
    for(const p of next.players){const a=xy(p.position),i=next.items.findIndex((it,j)=>!used.has(j)&&(it.type==='arrow'||it.type==='pen')&&itemFloor(it)===floorOfZ(p.position[2])&&Math.hypot(it.pts[0][0]-a[0],it.pts[0][1]-a[1])<22*view[2]/1024);
      if(i>=0){used.add(i);const e=next.items[i].pts.at(-1);p.position=world(e[0],e[1],p.position[2])}}
    next.items=next.items.filter((_,j)=>!used.has(j));st.splice(cur+1,0,next);cur++;setBoard(st);sync();render()};
  E('tbDelStage').onclick=()=>{if(st.length<2)return;snapshot();st.splice(cur,1);cur=Math.max(0,cur-1);sync();render()};
  E('tbClearStage').onclick=()=>{snapshot();stage().items=[];render()};
  E('tbPlay').onclick=startPlayback;E('tbBackToEdit').onclick=stopPlayback;E('tbDur').onchange=()=>{snapshot();stage().dur=Math.max(.5,Math.min(30,+E('tbDur').value||4));sync()};E('tbExport').onclick=()=>exportPng().catch(e=>alert(e.message));
  E('note').onchange=()=>{snapshot();stage().note=E('note').value};
  E('replay').onclick=close;
  E('save').onclick=async()=>{stage().note=E('note').value;try{const src=standalone?null:(match?{match,round:meta.source_round??null,tick:meta.source_tick??null}:null);const r=await api('/api/room/tactic',{...(roomId?{id:roomId}:{}),name:E('boardName').value||t('我的战术方案'),map:radar.map,steps:payload(),...(roomId?{}:{source:src})});roomId=r.id;E('tbStatus').textContent=t('已保存到战术室');window.loadBoards?.()}catch(e){E('tbStatus').textContent=e.message}};
  E('boards').onchange=async()=>{const id=E('boards').value;if(!id)return;const b=await api('/api/room/tactic?id='+id);load(b)};
  E('mode').onclick=()=>{if(!round||!radar)return;playing=false;open(engine.state(seconds).filter(p=>p.alive),{source_round:round.number,source_tick:Math.round(round.start_tick+seconds*data.tick_rate)})};
  E('tbBlank').onclick=()=>{snapshot();stage().players=[];render()};
}
window.TacticBoard={render,down,move,up,open,load,close,active:()=>!!st,setStandalone:v=>{standalone=v}};
wire();
})();
