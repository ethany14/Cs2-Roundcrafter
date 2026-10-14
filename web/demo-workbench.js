/* Multi-round workbench. One AnalysisQuery and one round selection are shared by all four modes.
   Filtering, playback, heatmaps and grenade statistics are local server computations: zero model calls.
   Only "分析当前选择" starts an Eregion task, after explicit consent. */
(()=>{
const E=id=>document.getElementById(id);
const STORE='cs2-workbench-v1';
const KIND_COLOR={smoke:'#c9ced6',flash:'#f4ec8a',he:'#ef6a5a',fire:'#ff9a3d'},KIND_NAME={smoke:t('烟雾'),flash:t('闪光'),he:t('手雷'),fire:t('燃烧')};
const MODES=['single','multi','heat','nade'];
const DEFAULT={map:'de_dust2',side:'T',outcome:'any',plant:'any',plant_site:'any',aliveAt:'alignment',aliveTime:0,ownMin:'',ownMax:'',enemyMin:'',enemyMax:'',
  equipAt:'opening',equipTime:0,weapon:'',rifles:'',econField:'freeze_end_equip_value',econMin:'',econMax:'',zoneMode:'',zoneTime:0,place:'',zoneFloor:'any',rect:null,
  alignment:'round_start',w0:0,w1:115,matches:[],players:[]};
let S={mode:'multi',source:'pro',compare:false,declared:false,f:{...DEFAULT},unchecked:[],hidden:[],hiddenPlayers:[],floor:'upper',trail:4,showUtil:true,showEnemy:false,showTraj:true,
  heat:{metric:'dwell',cell:8,smooth:2,palette:'thermal'},nade:{space:160,time:5,kinds:['smoke','flash','he','fire'],sort:'time',player:''},agentJob:''};
let catalog=null,radarMeta=null,images={},resA=null,resB=null,tracksA=[],tracksB=[],heatA=null,heatB=null,nadeA=null,cmpNade=null,selCluster=null,selNade=null,
  tNow=0,playing=false,boxMode=false,boxDrag=null,box=null,view=null,pan=null,queryVer=0,loadVer=0,loadCtl=null,heatVer=0,nadeVer=0,agentTimer=null,lastFrame=performance.now(),fpsSamples=[];
window.wbPerf={loads:[],fps:()=>fpsSamples.length?Math.round(fpsSamples.reduce((a,b)=>a+b,0)/fpsSamples.length):null};

function save(){try{localStorage.setItem(STORE,JSON.stringify(S))}catch{}}
function restore(){try{const v=JSON.parse(localStorage.getItem(STORE)||'null');if(v&&typeof v==='object'){if(!v.source){v.compare=v.group==='compare';const g=v.group==='compare'?v.groupA:v.group;v.source=String(g||'pro').startsWith('pro')?'pro':(g||'pro')}S={...S,...v,f:{...DEFAULT,...(v.f||{})},heat:{...S.heat,...(v.heat||{})},nade:{...S.nade,...(v.nade||{})}}}}catch{}}
async function post(path,body,signal){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body),signal});const d=await r.json();if(!r.ok)throw Error(t(d.error)||t('请求失败'));return d}
async function get(path){const r=await fetch(path);const d=await r.json();if(!r.ok)throw Error(t(d.error)||t('请求失败'));return d}
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e[k]=v;else if(v!==undefined&&v!==null&&v!==false)e.setAttribute(k,v===true?'':v)}for(const c of kids.flat())if(c!=null)e.append(c);return e}
function btn(text,fn,cls){const b=el('button',{class:cls||''},text);b.onclick=async e=>{e.stopPropagation();try{await fn(e)}catch(x){note(x.message)}};return b}
function note(text){E('wbLoad').textContent=text}
function roundColor(i){return `hsl(${(i*137.508)%360} 72% 62%)`}
const num=v=>v===''||v==null?null:Number(v);
// Display names per match (local only); IDs like P3 remain the keys and what the Agent sees.
function nm(mid,pid){return pid&&(catalog?.matches||[]).find(m=>m.id===mid)?.names?.[pid]||pid}

/* ---------------- query building ---------------- */
function groupsFor(which){
  // One data source (A) plus an optional pro reference (B). B never contains A's own matches.
  const pro=S.declared?['pro_verified','pro_declared']:['pro_verified'];
  if(which==='b')return pro;
  return S.source==='pro'?pro:[S.source];
}
function buildQuery(which='a',selection=resA?.selection){
  const f=S.f,q={map:f.map,side:f.side,group:groupsFor(which),outcome:f.outcome,plant:f.plant,plant_site:f.plant_site,alignment:f.alignment,window:[Number(f.w0),Number(f.w1)]};
  if(which==='a'){q.matches=f.matches;q.players=f.players}
  else{const own=new Set((selection||[]).map(s=>s.match));q.matches=(catalog?.matches||[]).filter(m=>m.map===f.map&&q.group.includes(m.group)&&!own.has(m.id)).map(m=>m.id);if(!q.matches.length)q.matches=['0'.repeat(32)]}
  if([f.ownMin,f.ownMax,f.enemyMin,f.enemyMax].some(v=>v!==''&&v!=null))q.alive={at:f.aliveAt,time:Number(f.aliveTime),own_min:num(f.ownMin),own_max:num(f.ownMax),enemy_min:num(f.enemyMin),enemy_max:num(f.enemyMax)};
  if(f.weapon||f.rifles!=='')q.equipment={at:f.equipAt,time:Number(f.equipTime),weapon:f.weapon||null,rifles_min:num(f.rifles)};
  if(f.econMin!==''||f.econMax!=='')q.economy={field:f.econField,min:num(f.econMin),max:num(f.econMax)};
  if(f.zoneMode&&(f.rect||f.place))q.zone={mode:f.zoneMode,time:Number(f.zoneTime),floor:f.zoneFloor,...(f.rect?{rect:f.rect}:{place:f.place})};
  return q;
}
const compare=()=>!!S.compare;
const SOURCE_NAME={player:t('我的比赛'),pro:t('职业比赛'),unknown:t('未分类')};

/* ---------------- filter controls ---------------- */
const bind=[['wbMap','map'],['wbSide','side'],['wbOutcome','outcome'],['wbPlant','plant'],['wbPlantSite','plant_site'],['wbAliveAt','aliveAt'],['wbAliveTime','aliveTime'],['wbOwnMin','ownMin'],['wbOwnMax','ownMax'],['wbEnemyMin','enemyMin'],['wbEnemyMax','enemyMax'],
  ['wbEquipAt','equipAt'],['wbEquipTime','equipTime'],['wbWeapon','weapon'],['wbRifles','rifles'],['wbEconField','econField'],['wbEconMin','econMin'],['wbEconMax','econMax'],['wbZoneMode','zoneMode'],['wbZoneTime','zoneTime'],['wbPlace','place'],['wbZoneFloor','zoneFloor'],['wbAlign','alignment'],['wbW0','w0'],['wbW1','w1']];
function syncControls(){
  for(const [id,k] of bind)E(id).value=S.f[k]??'';
  E('wbAliveTime').hidden=S.f.aliveAt!=='time';E('wbEquipTime').hidden=S.f.equipAt!=='time';E('wbZoneTime').hidden=S.f.zoneMode!=='at';
  E('wbZoneRect').textContent=S.f.rect?t('框选范围：X {0}…{1}，Y {2}…{3}（世界坐标，优先于地点名）',[S.f.rect[0].toFixed(0),S.f.rect[2].toFixed(0),S.f.rect[1].toFixed(0),S.f.rect[3].toFixed(0)]):'';
  E('wbDeclared').checked=S.declared;E('wbSource').value=S.source;E('wbCompareToggle').setAttribute('aria-pressed',String(compare()));
  document.querySelectorAll('#wbTop [data-mode]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.mode===S.mode)));
  E('wbFloor').value=S.floor;E('wbTrail').value=String(S.trail);E('wbShowUtil').checked=S.showUtil;E('wbShowEnemy').checked=S.showEnemy;E('wbShowTraj').checked=S.showTraj;
}
let refreshTimer=null;
function scheduleRefresh(){clearTimeout(refreshTimer);refreshTimer=setTimeout(()=>refresh().catch(e=>note(e.message)),220)}
for(const [id,k] of bind){const c=E(id);c.addEventListener(c.tagName==='SELECT'?'change':'input',()=>{S.f[k]=c.value;if(k==='map'){S.f.matches=[];S.f.players=[];S.f.rect=null;box=null;S.unchecked=[];loadCatalog().then(()=>{fit();scheduleRefresh()})}else{syncControls();scheduleRefresh()}})}
E('wbDeclared').onchange=()=>{S.declared=E('wbDeclared').checked;scheduleRefresh()};
E('wbSource').onchange=()=>{S.source=E('wbSource').value;S.f.matches=[];S.f.players=[];S.unchecked=[];syncControls();renderMatches();scheduleRefresh()};
E('wbCompareToggle').onclick=()=>{S.compare=!S.compare;syncControls();scheduleRefresh()};
document.querySelectorAll('#wbTop [data-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.mode,true));
E('wbReset').onclick=()=>{const map=S.f.map;S.f={...DEFAULT,map};S.unchecked=[];S.hidden=[];S.hiddenPlayers=[];box=null;syncControls();renderMatches();scheduleRefresh()};
E('wbAll').onclick=()=>{S.unchecked=[];scheduleRefresh()};
E('wbNone').onclick=()=>{S.unchecked=[...new Set([...(resA?.selection||[]).map(s=>s.key),...S.unchecked])];scheduleRefresh()};

function matchesInScope(){const groups=groupsFor('a');return (catalog?.matches||[]).filter(m=>m.map===S.f.map&&groups.includes(m.group))}
function renderMatches(){
  const rows=matchesInScope(),root=E('wbMatches');root.replaceChildren();
  if(!rows.length){root.append(el('p',{class:'wb-note'},t('此分组在当前地图没有已解析比赛。')+(S.source==='player'?t('普通玩家 demo 尚未上传；可在“比赛库”上传，类型选择“普通玩家”。'):'')));renderPlayers();return}
  root.title=t('不勾选＝该分组全部比赛');
  for(const m of rows){const c=el('input',{type:'checkbox'});c.checked=S.f.matches.includes(m.id);c.onchange=()=>{S.f.matches=c.checked?[...S.f.matches,m.id]:S.f.matches.filter(x=>x!==m.id);S.unchecked=[];renderPlayers();scheduleRefresh()};
    root.append(el('label',{title:t(m.group_label)},c,m.name.replace(/\.dem$/,'')+' · '+m.rounds.length+t(' 回合')+(m.duplicates.length?t(' · 重复副本 ')+m.duplicates.length+t(' 份已去重'):'')))}
  renderPlayers();renderSupplement();
}
function renderPlayers(){
  const root=E('wbPlayers');root.replaceChildren();const ms=matchesInScope().filter(m=>!S.f.matches.length||S.f.matches.includes(m.id));
  if(ms.length>4){root.append(el('p',{class:'wb-note'},t('先在“比赛”里勾选不超过 4 场，再选择具体玩家。')));return}
  for(const m of ms){root.append(el('div',{class:'wb-group-label'},m.name.replace(/\.dem$/,'')));
    for(const p of catalog.players[m.id]||[]){const key=m.id+':'+p,c=el('input',{type:'checkbox'});c.checked=S.f.players.includes(key);c.onchange=()=>{S.f.players=c.checked?[...S.f.players,key]:S.f.players.filter(x=>x!==key);scheduleRefresh()};root.append(el('label',{},c,nm(m.id,p)))}}
}
async function loadCatalog(){
  catalog=await get('/api/workbench/catalog?map='+S.f.map);
  E('wbPlace').replaceChildren(el('option',{value:''},t('地点名…')),...catalog.places.map(p=>el('option',{value:p},p)));E('wbPlace').value=S.f.place||'';
  try{radarMeta=await get('/api/lab/radar/'+S.f.map)}catch{radarMeta=null}
  images={};if(radarMeta){for(const [k,u] of [['upper',radarMeta.upper_url],['lower',radarMeta.lower_url]])if(u){const im=new Image();im.src=u;im.onload=draw;images[k]=im}}
  E('wbFloor').disabled=!radarMeta?.lower_url;if(!radarMeta?.lower_url)S.floor='upper';
  renderMatches();renderSupplement();syncControls();
}
function renderSupplement(){
  const root=E('wbSupplement');root.replaceChildren();const scoped=matchesInScope(),missing=scoped.filter(m=>!m.capabilities.economy);
  if(!scoped.length)return;
  if(!missing.length){root.append(el('p',{class:'wb-note'},t('补充解析 v1 已就绪：精确经济、开镜状态、道具实体轨迹可用。setpos/setang 不生成。')));return}
  root.append(el('p',{class:'wb-note'},missing.length+t(' 场比赛缺少补充解析（经济/开镜/道具轨迹）。本机解析约 20–60 秒/场，不调用模型。')),btn(t('生成补充解析'),async()=>{const j=await post('/api/workbench/supplement/start',{all:true});pollSupplement(j.id)}));
}
async function pollSupplement(id){const s=await get('/api/workbench/supplement/status?id='+id);E('wbSupplement').replaceChildren(el('p',{class:'wb-note'},t('补充解析 {0} · {1}/{2}',[s.status==='running'?t('进行中'):s.status,s.done.length,s.matches.length])),...(s.status==='running'?[btn(t('取消'),()=>post('/api/workbench/supplement/cancel',{id}))]:[]));if(s.status==='running')setTimeout(()=>pollSupplement(id),1500);else{await loadCatalog();scheduleRefresh()}}

/* ---------------- query + selection ---------------- */
async function refresh(){
  const v=++queryVer;save();
  if(!catalog)await loadCatalog();
  // Assign A and B together: a mode load running in between must never see the new A with a missing B.
  const ra=await post('/api/workbench/query',{query:buildQuery('a'),unchecked:S.unchecked});if(v!==queryVer)return;
  let rb=null;if(compare()){rb=await post('/api/workbench/query',{query:buildQuery('b',ra.selection),unchecked:[]});if(v!==queryVer)return}
  resA=ra;resB=rb;
  renderChips();renderRounds();renderEcon();
  if(S.mode!=='single')await modeRefresh();
}
function renderChips(){
  const root=E('wbChips');root.replaceChildren();const f=S.f,mapName=f.map==='de_nuke'?'Nuke':'Dust2';
  const fixed=[mapName+' · '+(f.side==='T'?'T':'CT')+' · '+{round_start:t('按回合开始'),first_entry:t('按首次进点'),plant:t('按下包')}[f.alignment]+' '+f.w0+'–'+f.w1+'s'];
  for(const x of fixed)root.append(el('span',{class:'wb-chip fixed'},x));
  for(const c of resA?.conditions||[])root.append(el('span',{class:'wb-chip'},condText(c),btn('×',()=>removeCondition(c.key))));
  E('wbFilterCount').textContent=(resA?.conditions||[]).length||'';
  const c=resA?.counts;E('wbCount').textContent=c?t('{0} 回合 · {1} 场',[c.rounds,c.matches])+(resB?t(' ⇄ 职业 {0} 回合',[resB.counts.rounds]):''):'';E('wbCount').title=c?t('{0} 场 · {1} 回合 · 排除 {2}',[c.matches,c.rounds,c.excluded]):'';
}
function condText(c){
  // Server labels embed values in Chinese; in English rebuild the same semantics from the normalized query.
  if(I18N.lang!=='en')return c.label;const q=resA?.query||{},a=q.alive,e=q.equipment,ec=q.economy,z=q.zone;
  const range=(lo,hi)=>`${lo??0}–${hi??5}`;
  switch(c.key){
    case 'outcome':return q.outcome==='win'?'Own side won':'Own side lost';
    case 'plant':return q.plant==='planted'?'Bomb planted':'No plant';
    case 'plant_site':return `Actual plant site ${q.plant_site} (planter's area)`;
    case 'alive':{const when=a.at==='round_start'?'round start':a.at==='alignment'?'alignment point':`${a.time}s after alignment`;
      return `Alive at ${when}: `+[a.own_min!=null||a.own_max!=null?'own '+range(a.own_min,a.own_max):null,a.enemy_min!=null||a.enemy_max!=null?'enemy '+range(a.enemy_min,a.enemy_max):null].filter(Boolean).join(', ')}
    case 'equipment':return (e.at==='opening'?'Opening (2s after freeze end)':`${e.time}s after alignment`)+' gear: '+[e.weapon?'has '+e.weapon:null,e.rifles_min!=null?'rifles ≥'+e.rifles_min:null].filter(Boolean).join(', ');
    case 'economy':return (ec.field==='start_balance'?'Team money at round start':'Team equipment value at freeze end')+` ${ec.min??0}–${ec.max??'∞'} (needs supplement)`;
    case 'zone':{const where=z.place||'boxed area',fl=z.floor==='upper'?' · upper':z.floor==='lower'?' · lower':'';return z.mode==='passed'?`Passes ${where}${fl} within the window`:`In ${where}${fl} at ${z.time}s after alignment`}
    case 'rounds':return 'Specified rounds';
    case 'players':return `${(q.players||[]).length} specified players (per-match IDs)`;
  }
  return t(c.label);
}
function removeCondition(key){const f=S.f;
  if(key==='outcome')f.outcome='any';if(key==='plant')f.plant='any';if(key==='plant_site')f.plant_site='any';
  if(key==='alive'){f.ownMin=f.ownMax=f.enemyMin=f.enemyMax=''}if(key==='equipment'){f.weapon='';f.rifles=''}if(key==='economy'){f.econMin=f.econMax=''}
  if(key==='zone'){f.zoneMode='';f.rect=null;f.place=''}if(key==='players')f.players=[];if(key==='rounds')S.unchecked=[];
  syncControls();renderMatches();scheduleRefresh()}
function renderRounds(){
  const root=E('wbRounds');root.replaceChildren();const all=[...(resA?.selection||[]).map(s=>({...s,checked:true})),...(resA?.unchecked||[]).map(k=>({key:k,match:k.split(':')[0],round:+k.split(':')[1],checked:false}))];
  const names=Object.fromEntries((catalog?.matches||[]).map(m=>[m.id,m.name.replace(/\.dem$/,'')]));
  E('wbRoundCount').textContent=resA?`${resA.counts.rounds}/${resA.counts.scope_rounds}`:'';
  all.forEach((s,i)=>{const c=el('input',{type:'checkbox'});c.checked=s.checked;c.onchange=()=>{S.unchecked=c.checked?S.unchecked.filter(k=>k!==s.key):[...S.unchecked,s.key];scheduleRefresh()};
    const label=el('span',{title:t('点击打开单回合')},`${names[s.match]||s.match.slice(0,6)} R${s.round}`+(s.checked?` · ${s.winner===S.f.side?t('胜'):t('负')}${s.plant_site?t(' · 下包')+s.plant_site:''}`:t(' · 已取消')));
    label.onclick=()=>openSingle(s.match,s.round,s.checked?s.window[0]:0,s.checked?Math.min(s.window[1],s.window[0]+20):20,[]);
    root.append(el('div',{class:'wb-round'+(s.checked?'':' dim')},c,el('i',{style:`background:${roundColor(i)}`}),label))});
  const ex=E('wbExcluded');ex.replaceChildren();
  for(const x of resA?.excluded||[])ex.append(el('p',{},t('排除 {0}：{1}',[x.count,t(x.label)])));
  if(resA&&!resA.counts.scope_matches&&S.source==='player'){const box=E('wbEmpty');box.hidden=false;
    box.replaceChildren(el('b',{},t('还没有你的比赛')),el('p',{},t('关联 Steam 后，在 CS2 下载的 demo 会自动导入；也可以直接上传 demo。')),
      el('div',{class:'toolbar'},btn(t('去关联 Steam'),()=>window.showView('profile')),btn(t('上传 demo'),()=>window.showView('matches')),btn(t('先看职业比赛'),()=>{S.source='pro';syncControls();renderMatches();scheduleRefresh()},'mc-primary')));return}
  if(resA&&!resA.counts.rounds){const box=E('wbEmpty');box.hidden=false;box.replaceChildren(el('b',{},t('没有符合条件的回合')),el('p',{},t('在 ')+resA.counts.scope_rounds+t(' 个范围内回合中：')+(resA.excluded.map(x=>t(x.label)+' '+x.count).join(t('；'))||t('当前分组没有比赛'))),...(resA.conditions.map(c=>btn(t('移除：')+condText(c),()=>removeCondition(c.key)))))}else E('wbEmpty').hidden=true;
}
function renderEcon(){
  const caps=resA?.capabilities,ok=caps?.economy;for(const id of ['wbEconField','wbEconMin','wbEconMax'])E(id).disabled=!ok&&!(S.f.econMin||S.f.econMax);
  E('wbEconNote').textContent=ok?t('字段来自 demo：冻结结束 tick 的 current_equip_value / start_balance（非估算）。'):t('不可用：')+(t(caps?.missing?.[0])||t('需要补充解析'));
}

/* ---------------- mode switching ---------------- */
function showView(v,opts={}){
  // Three top-level views; the analysis view remembers its last mode, review maps to the single-round player.
  if(v==='review'&&S.mode!=='single')return setMode('single',!opts.noAuto);
  if(v==='analysis'&&S.mode==='single')return setMode(S.lastMode||'multi');
  document.body.dataset.view=v;document.querySelectorAll('.mc-nav [data-view]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.view===v)));
  if(['matches','room','profile'].includes(v))window.history.replaceState(null,'','/demos?view='+v);
  document.dispatchEvent(new CustomEvent('viewchange',{detail:v}));
}
window.showView=showView;
document.querySelectorAll('.mc-nav [data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view));
function setFilters(open){S.filtersOpen=open;save();document.body.classList.toggle('filters-closed',!open);E('wbFilterToggle').setAttribute('aria-pressed',String(open));requestAnimationFrame(resize)}
E('wbFilterToggle').onclick=()=>setFilters(!S.filtersOpen);
function sideTab(agent){E('wbTabStats').setAttribute('aria-selected',String(!agent));E('wbTabAgent').setAttribute('aria-selected',String(agent));E('wbStatsPane').hidden=agent;E('wbAgent').hidden=!agent}
E('wbTabStats').onclick=()=>sideTab(false);E('wbTabAgent').onclick=()=>sideTab(true);
function setMode(m,fromUser=false){
  if(!MODES.includes(m))return;S.mode=m;if(m!=='single')S.lastMode=m;save();syncControls();
  const single=m==='single';document.body.dataset.view=single?'review':'analysis';
  document.querySelectorAll('.mc-nav [data-view]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.view===document.body.dataset.view)));
  E('wbMulti').hidden=m!=='multi';E('wbHeat').hidden=m!=='heat';E('wbNade').hidden=m!=='nade';
  E('wbShowTraj').parentElement.hidden=m!=='nade';E('wbTrail').parentElement.hidden=m!=='multi';E('wbShowEnemy').parentElement.hidden=m!=='multi';
  for(const id of ['wbPlay','wbSpeed','wbTime','wbTimeLabel'])E(id).hidden=m==='heat';
  if(single){playing=false;if(fromUser&&(typeof round==='undefined'||!round)&&resA?.selection?.length){const s=resA.selection[0];openSingle(s.match,s.round,s.window[0],s.window[0]+15,[])}return}
  window.history.replaceState(null,'','/demos?wbmode='+m);
  requestAnimationFrame(()=>{resize();modeRefresh().catch(e=>note(e.message))});
}
async function modeRefresh(){
  renderAgent();
  E('wbPaneB').hidden=!(compare()&&S.mode!=='multi');
  E('wbLabelA').textContent=SOURCE_NAME[S.source]+' · '+(resA?.counts.rounds||0)+t(' 回合');
  E('wbLabelB').textContent=t('职业参考 · ')+(resB?.counts.rounds||0)+t(' 回合');
  resize();setTimeline();
  if(S.mode==='multi')await loadTracks();
  if(S.mode==='heat')await loadHeat();
  if(S.mode==='nade')await loadNades();
}

/* ---------------- map canvas ---------------- */
const panes=[{c:E('wbCanvasA'),which:'a'},{c:E('wbCanvasB'),which:'b'}];
function fit(){if(!radarMeta?.content_bounds){view=[0,0,1024];return}const [l,tp,r,b]=radarMeta.content_bounds.map(x=>x*1024);const size=Math.max(r-l,b-tp)*1.04;view=[(l+r-size)/2,(tp+b-size)/2,size];draw()}
function resize(){for(const p of panes){const r=p.c.getBoundingClientRect(),d=devicePixelRatio||1;if(r.width&&(p.c.width!==Math.round(r.width*d)||p.c.height!==Math.round(r.height*d))){p.c.width=Math.round(r.width*d);p.c.height=Math.round(r.height*d)}}draw()}
new ResizeObserver(()=>resize()).observe(E('wbPaneA'));
function geom(c){const d=devicePixelRatio||1,W=c.width/d,H=c.height/d,s=Math.min(W,H)/view[2];return {d,W,H,s,ox:(W-view[2]*s)/2-view[0]*s,oy:(H-view[2]*s)/2-view[1]*s}}
function px(p){return [(p[0]-radarMeta.pos_x)/radarMeta.scale,(radarMeta.pos_y-p[1])/radarMeta.scale]}
function worldOf(u,v){return [u*radarMeta.scale+radarMeta.pos_x,radarMeta.pos_y-v*radarMeta.scale]}
function floorOf(z){return !radarMeta?.lower_url||z==null?'upper':z<radarMeta.floor_split_z?'lower':'upper'}
function screenToRadar(c,x,y){const g=geom(c);return [(x-g.ox)/g.s,(y-g.oy)/g.s]}
function draw(){
  if(!view||S.mode==='single')return;
  for(const p of panes){if(p.which==='b'&&E('wbPaneB').hidden)continue;const c=p.c,ctx=c.getContext('2d'),g=geom(c);
    ctx.setTransform(g.d,0,0,g.d,0,0);ctx.fillStyle='#0f1012';ctx.fillRect(0,0,g.W,g.H);
    ctx.setTransform(g.d*g.s,0,0,g.d*g.s,g.d*g.ox,g.d*g.oy);
    const im=images[S.floor]||images.upper;if(im?.complete&&im.naturalWidth){ctx.filter='grayscale(1) sepia(.18) brightness(.52) contrast(.95)';ctx.drawImage(im,0,0,1024,1024);ctx.filter='none'}
    const k=1/g.s;
    if(S.mode==='multi')drawMulti(ctx,k,p.which);if(S.mode==='heat')drawHeat(ctx,k,p.which);if(S.mode==='nade')drawNades(ctx,k,p.which);
    const b=boxDrag?.rect||box;if(b){const [u0,v0]=px([b[0],b[1]]),[u1,v1]=px([b[2],b[3]]);ctx.strokeStyle='#ffd77a';ctx.lineWidth=2*k;ctx.setLineDash([6*k,4*k]);ctx.strokeRect(Math.min(u0,u1),Math.min(v0,v1),Math.abs(u1-u0),Math.abs(v1-v0));ctx.setLineDash([])}
  }
}
function dot(ctx,u,v,r,fill,stroke,k){ctx.beginPath();ctx.arc(u,v,r*k,0,Math.PI*2);if(fill){ctx.fillStyle=fill;ctx.fill()}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.5*k;ctx.stroke()}}

/* pointer: pan by default, box with Shift or the 框选 toggle; hover tooltips; click opens evidence */
for(const p of panes){
  const c=p.c;
  c.addEventListener('wheel',e=>{e.preventDefault();const r=c.getBoundingClientRect(),[u,v]=screenToRadar(c,e.clientX-r.left,e.clientY-r.top),f=e.deltaY>0?1.15:.87,size=Math.min(1600,Math.max(120,view[2]*f)),k=size/view[2];view=[u-(u-view[0])*k,v-(v-view[1])*k,size];draw()},{passive:false});
  c.onpointerdown=e=>{if(!radarMeta)return;const r=c.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;c.setPointerCapture(e.pointerId);
    if(boxMode||e.shiftKey){const [u,v]=screenToRadar(c,x,y);boxDrag={u,v,rect:null,pane:p}}else pan={x,y,view:[...view],moved:false,pane:p}};
  c.onpointermove=e=>{const r=c.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
    if(boxDrag){const [u,v]=screenToRadar(c,x,y),[a0,b0]=worldOf(boxDrag.u,boxDrag.v),[a1,b1]=worldOf(u,v);boxDrag.rect=[Math.min(a0,a1),Math.min(b0,b1),Math.max(a0,a1),Math.max(b0,b1)];draw();return}
    if(pan){const g=geom(c);const dx=(x-pan.x)/g.s,dy=(y-pan.y)/g.s;if(Math.abs(x-pan.x)+Math.abs(y-pan.y)>3)pan.moved=true;view=[pan.view[0]-dx,pan.view[1]-dy,view[2]];draw();return}
    hover(p,x,y)};
  c.onpointerup=e=>{const r=c.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
    if(boxDrag){const rect=boxDrag.rect;boxDrag=null;if(rect&&rect[2]-rect[0]>8&&rect[3]-rect[1]>8){box=rect;onBox().catch(x=>note(x.message))}draw();return}
    if(pan){const moved=pan.moved;pan=null;if(!moved)clickAt(p,x,y)}};
  c.onpointerleave=()=>{E('wbTip').hidden=true};
}
E('wbBox').onclick=()=>{boxMode=!boxMode;E('wbBox').setAttribute('aria-pressed',String(boxMode));panes.forEach(p=>p.c.classList.toggle('boxing',boxMode))};
E('wbClearBox').onclick=()=>{box=null;selCluster=null;E('wbBoxHits').replaceChildren();if(S.f.rect){S.f.rect=null;if(!S.f.place)S.f.zoneMode='';syncControls();scheduleRefresh()}else{renderNadeList();draw()}};
E('wbFit').onclick=fit;
E('wbFloor').onchange=()=>{S.floor=E('wbFloor').value;save();if(S.mode==='heat')loadHeat().catch(e=>note(e.message));else{renderNadeList();draw()}};
E('wbTrail').onchange=()=>{S.trail=+E('wbTrail').value;save();draw()};
E('wbShowUtil').onchange=()=>{S.showUtil=E('wbShowUtil').checked;save();draw()};
E('wbShowEnemy').onchange=()=>{S.showEnemy=E('wbShowEnemy').checked;save();loadTracks().catch(e=>note(e.message))};
E('wbShowTraj').onchange=()=>{S.showTraj=E('wbShowTraj').checked;save();draw()};
function tip(p,x,y,text){const tNow=E('wbTip'),r=p.c.getBoundingClientRect(),host=E('wbPaneA').parentElement.getBoundingClientRect();tNow.hidden=!text;if(!text)return;tNow.textContent=text;tNow.style.left=Math.min(host.width-290,r.left-host.left+x+14)+'px';tNow.style.top=(r.top-host.top+y+12)+'px'}

/* ---------------- multi-round playback ---------------- */
function sampleAt(samples,tt){
  // samples: [t_rel,x,y,z,alive]; linear interpolation only between two live samples ≤1 s apart; never extrapolate.
  if(!samples.length||tt<samples[0][0]-.13||tt>samples[samples.length-1][0]+.13)return null;
  let lo=0,hi=samples.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(samples[m][0]<=tt)lo=m;else hi=m-1}
  const a=samples[lo],b=samples[lo+1];
  if(b&&a[4]&&b[4]&&b[0]-a[0]<=1&&tt>=a[0]){const k=(tt-a[0])/(b[0]-a[0]);return [tt,a[1]+(b[1]-a[1])*k,a[2]+(b[2]-a[2])*k,a[3]+(b[3]-a[3])*k,1,a[0]]}
  return tt>=a[0]&&(tt-a[0]<=1||!a[4])?[...a,a[0]]:null;  // dead players stay as a cross; live gaps >1 s are not bridged
}
let multiDots=[];
function drawMulti(ctx,k,which){
  if(which==='b')return;multiDots=[];const hidden=new Set(S.hidden),hp=new Set(S.hiddenPlayers);
  tracksA.forEach((r,i)=>{if(hidden.has(r.key))return;const col=roundColor(r.index??i);
    for(const p of r.players){if(hp.has(r.key+':'+p.id)||(!p.own&&!S.showEnemy))continue;const s=sampleAt(p.samples,tNow);
      if(S.trail>0){ctx.beginPath();let started=false;for(const q of p.samples){if(q[0]>tNow)break;if(q[0]<tNow-S.trail||!q[4]||floorOf(q[3])!==S.floor){started=false;continue}const [u,v]=px([q[1],q[2]]);if(!started){ctx.moveTo(u,v);started=true}else ctx.lineTo(u,v)}ctx.strokeStyle=col;ctx.globalAlpha=p.own?.55:.25;ctx.lineWidth=2*k;ctx.stroke();ctx.globalAlpha=1}
      if(!s||floorOf(s[3])!==S.floor)continue;const [u,v]=px([s[1],s[2]]);
      if(s[4]){dot(ctx,u,v,p.own?4.5:3.5,p.own?col:'#0f1012',p.own?'#0b0c0e':col,k)}else{ctx.strokeStyle='#7d838c';ctx.lineWidth=1.5*k;ctx.beginPath();ctx.moveTo(u-3*k,v-3*k);ctx.lineTo(u+3*k,v+3*k);ctx.moveTo(u+3*k,v-3*k);ctx.lineTo(u-3*k,v+3*k);ctx.stroke()}
      multiDots.push({u,v,r,p,raw:r.anchor+tNow,alive:s[4]})}
    if(S.showUtil)for(const e of r.events){if(!e.position||!(e.type in KINDS_EV)||e.t>tNow||e.t<tNow-3||e.floor!==S.floor)continue;const [u,v]=px(e.position);dot(ctx,u,v,7,null,KIND_COLOR[KINDS_EV[e.type]],k)}
  });
  const sel=multiHover;if(sel){ctx.font=`${12*k}px system-ui`;ctx.fillStyle='#fff';ctx.fillText(`${sel.r.name.replace(/\.dem$/,'')} R${sel.r.round} ${nm(sel.r.match,sel.p.id)}`,sel.u+7*k,sel.v-7*k)}
}
const KINDS_EV={smokegrenade_detonate:'smoke',flashbang_detonate:'flash',hegrenade_detonate:'he',inferno_startburn:'fire'};
let multiHover=null;
function nearestDot(p,x,y,list,key='u'){const g=geom(p.c);let best=null,bd=10;for(const d of list){const sx=d.u*g.s+g.ox,sy=d.v*g.s+g.oy,dd=Math.hypot(sx-x,sy-y);if(dd<bd){bd=dd;best=d}}return best}
function hover(p,x,y){
  if(S.mode==='multi'&&p.which==='a'){const d=nearestDot(p,x,y,multiDots);multiHover=d;tip(p,x,y,d?t('{0} · R{1} · {2}（比赛内编号）\n对齐后 {3}s · 原始 {4}s{5}\n点击回到单回合此刻',[d.r.name.replace(/\.dem$/,''),d.r.round,nm(d.r.match,d.p.id),tNow.toFixed(2),d.raw.toFixed(2),d.alive?'':t(' · 已阵亡')]):'');draw()}
  if(S.mode==='nade'){const d=nearestDot(p,x,y,nadeDots[p.which]||[]);tip(p,x,y,d?t('{0} · {1} R{2} · {3}\n对齐后 {4}s · 原始 {5}s{6}',[KIND_NAME[d.i.kind],d.i.name.replace(/\.dem$/,''),d.i.round,nm(d.i.match,d.i.player)||t('未知'),d.i.t.toFixed(1),d.i.raw.toFixed(1),d.i.trajectory?t('\n含解析器实体轨迹'):t('\n无真实轨迹：仅作用点')]):'')}
  if(S.mode==='heat'){const h=p.which==='b'?heatB:heatA;if(!h)return;const [u,v]=screenToRadar(p.c,x,y),cx=Math.floor(u/h.cell),cy=Math.floor(v/h.cell),val=h.smoothed?.[cy*h.grid+cx]??0;tip(p,x,y,val>0?t('{0} {1}%（平滑后）\n点击查看贡献回合',[S.heat.metric==='reach'?t('到达率'):t('停留占比'),(val*100).toFixed(2)]):'')}
}
function clickAt(p,x,y){
  if(S.mode==='multi'){const d=nearestDot(p,x,y,multiDots);if(d)openSingle(d.r.match,d.r.round,Math.max(0,d.raw-1),d.raw+6,[d.p.id])}
  if(S.mode==='nade'){const d=nearestDot(p,x,y,nadeDots[p.which]||[]);if(d){selNade=d.i.id;if(E('wbNadeSec'))E('wbNadeSec').open=true;renderNadeList();draw();document.querySelector(`[data-nade="${CSS.escape(d.i.id)}"]`)?.scrollIntoView({block:'nearest'})}}
  if(S.mode==='heat'){const h=p.which==='b'?heatB:heatA;if(!h)return;const [u,v]=screenToRadar(p.c,x,y);heatCell(p.which,Math.floor(u/h.cell),Math.floor(v/h.cell)).catch(e=>note(e.message))}
}
async function loadTracks(){
  if(loadCtl)loadCtl.abort();const v=++loadVer,ctl=new AbortController();loadCtl=ctl;tracksA=[];playing=false;
  const sel=resA?.selection||[];setTimeline();if(sel.length)E('wbEmpty').hidden=true;if(!sel.length){renderMultiPanel();draw();return}
  E('wbCancelLoad').hidden=false;const t0=performance.now();let offset=0;
  try{
    while(true){
      const d=await post('/api/workbench/tracks',{query:buildQuery('a'),unchecked:S.unchecked,offset,limit:10,include_enemies:S.showEnemy},ctl.signal);
      if(v!==loadVer)return;d.rounds.forEach((r,i)=>r.index=offset+i);tracksA.push(...d.rounds);offset+=d.rounds.length;
      note(t('已加载 {0}/{1} 回合',[tracksA.length,d.total]));renderMultiPanel();draw();
      if(d.done||!d.rounds.length)break;
    }
    const ms=Math.round(performance.now()-t0);window.wbPerf.loads.push({rounds:tracksA.length,ms});note(t('已加载 {0} 回合 · {1} ms',[tracksA.length,ms]));
  }catch(e){if(e.name==='AbortError'){note(t('已取消加载：保留 {0} 回合（共 {1}）',[tracksA.length,sel.length]))}
    else if(/安全上限/.test(e.message)){const box=E('wbEmpty');box.hidden=false;const ms=matchesInScope();
      box.replaceChildren(el('b',{},e.message),el('p',{},t('叠加播放不会静默丢弃回合。可以按比赛、胜负、下包或区域缩小范围；热力图与道具模式可以直接使用全部回合。')),
        ...ms.slice(0,4).map(m=>btn(t('只看 ')+m.name.replace(/\.dem$/,''),()=>{S.f.matches=[m.id];renderMatches();scheduleRefresh()})),btn(t('切换到热力图'),()=>setMode('heat')));note(e.message)}
    else throw e}
  finally{if(v===loadVer){E('wbCancelLoad').hidden=true;loadCtl=null}}
}
E('wbCancelLoad').onclick=()=>{if(loadCtl)loadCtl.abort()};
function setTimeline(){const w=[Number(S.f.w0),Number(S.f.w1)];E('wbTime').min=w[0];E('wbTime').max=w[1];tNow=Math.min(Math.max(tNow,w[0]),w[1]);E('wbTime').value=tNow;timeLabel()}
function timeLabel(){E('wbTimeLabel').textContent=t('对齐后 {0}s',[tNow.toFixed(2)])+(S.mode==='nade'?t('（道具按时间轴累计显示）'):'');E('wbPlay').textContent=playing?t('暂停'):t('播放')}
E('wbTime').oninput=()=>{tNow=+E('wbTime').value;playing=false;timeLabel();if(S.mode==='nade')renderNadeList();draw()};
E('wbPlay').onclick=()=>{if(tNow>=+E('wbTime').max)tNow=+E('wbTime').min;playing=!playing;timeLabel()};
function tick(now){const dt=(now-lastFrame)/1000;lastFrame=now;
  if(playing&&S.mode!=='single'&&S.mode!=='heat'){tNow=Math.min(+E('wbTime').max,tNow+dt*+E('wbSpeed').value);if(tNow>=+E('wbTime').max)playing=false;E('wbTime').value=tNow;timeLabel();
    const t0=performance.now();draw();if(S.mode==='multi'&&dt>0){fpsSamples.push(1/dt);if(fpsSamples.length>120)fpsSamples.shift()}window.wbPerf.lastDrawMs=+(performance.now()-t0).toFixed(2)}
  requestAnimationFrame(tick)}
requestAnimationFrame(tick);
/* compact side-panel helpers: one summary line, main list as rows, secondary info folded */
function sec(title,open,...kids){const d=el('details',{class:'wb-sec'},el('summary',{},title),...kids);d.open=!!open;return d}
function line(color,label,meta,...actions){return el('div',{class:'wb-line'},el('i',{class:'dot',style:color?`background:${color}`:''}),el('span',{class:'lbl',title:label},label),el('small',{class:'meta'},meta||''),el('span',{class:'acts'},...actions))}
function ibtn(text,title,fn){const b=btn(text,fn,'ibtn');b.title=title;return b}
function renderMultiPanel(){
  const root=E('wbMulti'),hidden=new Set(S.hidden),visible=tracksA.filter(r=>!hidden.has(r.key)).length;
  root.replaceChildren(el('h2',{},t('多回合叠加')),el('p',{class:'wb-note'},t('{0}/{1} 回合可见 · 颜色＝回合 · 点击地图上的玩家打开该回合',[visible,tracksA.length])));
  if(compare())root.append(el('p',{class:'wb-note'},t('双方对照下多回合仅播放当前组；热力图与道具模式并排显示参考组。')));
  const list=el('div',{class:'wb-lines'});
  for(const r of tracksA){const c=el('input',{type:'checkbox',title:t('显示 / 隐藏')});c.checked=!hidden.has(r.key);c.onchange=()=>{S.hidden=c.checked?S.hidden.filter(k=>k!==r.key):[...S.hidden,r.key];save();draw();renderMultiPanel()};
    const ln=line(roundColor(r.index),`${r.name.replace(/\.dem$/,'')} R${r.round}`,t('对齐 {0}s',[r.anchor.toFixed(0)]),
      ibtn('▶',t('▶ 单回合'),()=>openSingle(r.match,r.round,Math.max(r.window[0],r.anchor+tNow-2),r.anchor+tNow+8,[])),
      ibtn('＋',t('加入播放列表'),()=>{playlist.push({match:r.match,round:r.round,name:r.name,start:r.anchor+tNow});renderPlaylist()}));
    ln.prepend(c);list.append(ln)}
  root.append(sec(t('回合 ({0})',[tracksA.length]),true,list),el('div',{id:'wbPlaylist'}),sec(t('可见对象统计'),false,el('div',{id:'wbStats'})));
  renderMultiStats();renderPlaylist();
}
let playlist=[];
function renderPlaylist(){const root=E('wbPlaylist');if(!root)return;root.replaceChildren();if(!playlist.length)return;
  root.append(sec(t('临时播放列表 ')+playlist.length,true,el('div',{class:'wb-lines'},...playlist.map((x,i)=>line('',`${i+1}. ${x.name.replace(/\.dem$/,'')} R${x.round}`,x.start.toFixed(1)+'s',ibtn('▶',t('播放'),()=>openSingle(x.match,x.round,Math.max(0,x.start-1),x.start+10,[])),ibtn('×',t('移除'),()=>{playlist.splice(i,1);renderPlaylist()}))))))}
function renderMultiStats(){const root=E('wbStats');if(!root)return;const hidden=new Set(S.hidden),visible=tracksA.filter(r=>!hidden.has(r.key));
  const players=visible.reduce((a,r)=>a+r.players.filter(p=>p.own&&!S.hiddenPlayers.includes(r.key+':'+p.id)).length,0);
  const util={};for(const r of visible)for(const e of r.events)if(KINDS_EV[e.type]&&e.side===S.f.side)util[KINDS_EV[e.type]]=(util[KINDS_EV[e.type]]||0)+1;
  root.replaceChildren(el('dl',{class:'wb-kv'},el('dt',{},t('回合')),el('dd',{},`${visible.length} / ${tracksA.length}`),el('dt',{},t('玩家轨迹')),el('dd',{},String(players)),el('dt',{},t('本方道具事件')),el('dd',{},Object.entries(util).map(([k,v])=>KIND_NAME[k]+' '+v).join(' · ')||t('无'))))}

/* ---------------- box selection ---------------- */
async function onBox(){
  const zone={mode:'passed',rect:box,floor:radarMeta?.lower_url?S.floor:'any'};
  const root=E('wbBoxHits');root.replaceChildren(el('h3',{},t('框选区域')),el('p',{class:'wb-note'},t('正在统计…')));
  if(S.mode==='nade'){renderNadeList();draw()}
  const d=await post('/api/workbench/zone',{query:buildQuery('a'),unchecked:S.unchecked,zone});
  root.replaceChildren(el('div',{class:'wb-card'},el('b',{},t('框选区域 · {0}/{1} 回合经过',[d.hits.length,d.rounds])),el('small',{},zone.floor==='any'?t('不分楼层'):zone.floor==='lower'?t('仅下层'):t('仅上层')),
    el('div',{class:'wb-row'},btn(t('设为区域筛选条件'),()=>{S.f.rect=box;S.f.zoneMode='passed';S.f.zoneFloor=zone.floor;syncControls();scheduleRefresh()}),
      btn(t('全部加入播放列表'),()=>{for(const h of d.hits)playlist.push({match:h.match,round:h.round,name:h.name,start:h.raw_seconds});renderPlaylist()}),
      btn(t('清除框选'),()=>E('wbClearBox').click())),
    sec(t('命中回合 ({0})',[d.hits.length]),false,el('div',{class:'wb-lines'},...d.hits.map(h=>line('',`${h.name.replace(/\.dem$/,'')} R${h.round}`,t('{0} · 对齐后 {1}s',[nm(h.match,h.player),h.t.toFixed(1)]),ibtn('▶',t('▶ 回放验证'),()=>openSingle(h.match,h.round,h.evidence.start,h.evidence.end,h.evidence.players))))))));
}

/* ---------------- heatmap ---------------- */
function smooth(h,r){const n=h.grid,raw=new Float32Array(n*n);for(const c of h.cells)raw[c[1]*n+c[0]]=c[3];if(!r)return raw;
  const tmp=new Float32Array(n*n),out=new Float32Array(n*n),w=[];for(let i=-r;i<=r;i++)w.push(Math.exp(-(i*i)/(2*(r/1.5)**2)));const ws=w.reduce((a,b)=>a+b,0);
  for(let y=0;y<n;y++)for(let x=0;x<n;x++){let s=0;for(let i=-r;i<=r;i++){const xx=x+i;if(xx>=0&&xx<n)s+=raw[y*n+xx]*w[i+r]}tmp[y*n+x]=s/ws}
  for(let y=0;y<n;y++)for(let x=0;x<n;x++){let s=0;for(let i=-r;i<=r;i++){const yy=y+i;if(yy>=0&&yy<n)s+=tmp[yy*n+x]*w[i+r]}out[y*n+x]=s/ws}return out}
/* Density rendering: every grid cell becomes a soft radial stamp on an alpha layer, then the layer is colourised
   through a palette LUT (the usual heatmap look). Values stay the server's normalised shares; groups share one max. */
const PALETTES={thermal:[[0,0,0,255],[.2,0,180,255],[.4,0,230,120],[.6,200,240,0],[.8,255,150,0],[1,255,30,20]],
  mission:[[0,90,18,11],[.3,160,30,16],[.55,252,61,33],[.8,255,178,63],[1,244,234,210]]};
function lut(name){const st=PALETTES[name]||PALETTES.thermal,out=new Uint8ClampedArray(256*3);
  for(let i=0;i<256;i++){const v=i/255;let j=1;while(j<st.length-1&&v>st[j][0])j++;const a=st[j-1],b=st[j],k=Math.max(0,Math.min(1,(v-a[0])/((b[0]-a[0])||1)));for(let c=0;c<3;c++)out[i*3+c]=a[c+1]+(b[c+1]-a[c+1])*k}return out}
function smoothRadius(h){return Math.max(1,Math.round((1+S.heat.smooth*1.6)*8/h.cell))}
function heatImage(h,max){const n=h.grid,cv=document.createElement('canvas');cv.width=cv.height=n;const ctx=cv.getContext('2d'),img=ctx.createImageData(n,n),L=lut(S.heat.palette);
  for(let i=0;i<n*n;i++){const v=max>0?Math.sqrt(Math.min(1,h.smoothed[i]/max)):0;if(v<.07)continue;const c=Math.round(v*255);img.data.set([L[c*3],L[c*3+1],L[c*3+2],Math.round(255*Math.min(.86,.15+v*.8))],i*4)}
  ctx.putImageData(img,0,0);return cv}
function heatRecolor(){for(const h of [heatA,heatB])if(h)h.smoothed=smooth(h,smoothRadius(h));heatMax=Math.max(0,...[heatA,heatB].filter(Boolean).map(h=>h.smoothed.reduce((a,b)=>Math.max(a,b),0)));for(const h of [heatA,heatB])if(h)h.image=heatImage(h,heatMax)}
let heatMax=0,heatSel=null;
async function loadHeat(){
  const v=++heatVer;const body={query:buildQuery('a'),unchecked:S.unchecked,metric:S.heat.metric,floor:S.floor,cell:S.heat.cell};
  renderHeatPanel();if(!resA?.counts.rounds){heatA=heatB=null;draw();return}
  note(t('正在计算热力图…'));const t0=performance.now();
  let d;if(compare()){if(!resB?.counts.rounds){heatB=null;d=null}else d=await post('/api/workbench/heatmap',{...body,query_b:buildQuery('b'),unchecked_b:[]})}
  const single=d?null:await post('/api/workbench/heatmap',body);if(v!==heatVer)return;
  heatA=d?d.a:single;heatB=d?d.b:null;heatCompareInfo=d;
  heatRecolor();
  note(t('热力图 {0} ms · 服务端 {1} ms{2}',[Math.round(performance.now()-t0),(heatA.usage?.elapsed_ms??0),heatA.usage?.cache_hit?t('（缓存）'):'']));renderHeatPanel();draw();
}
let heatCompareInfo=null;
function drawHeat(ctx,k,which){const h=which==='b'?heatB:heatA;const lg=E(which==='b'?'wbLegendB':'wbLegendA');
  if(!h){lg.replaceChildren(which==='b'?t('参考组没有可比回合'):'');return}
  ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(h.image,0,0,1024,1024);
  if(heatSel&&heatSel.which===which){ctx.strokeStyle='#fff';ctx.lineWidth=2*k;ctx.strokeRect((heatSel.cx-S.heat.smooth)*h.cell,(heatSel.cy-S.heat.smooth)*h.cell,(2*S.heat.smooth+1)*h.cell,(2*S.heat.smooth+1)*h.cell)}
  lg.replaceChildren(el('span',{},'0'),el('span',{class:'bar '+(S.heat.palette||'thermal')}),el('span',{},(heatMax*100).toFixed(2)+'%'+(compare()?t('（共同色阶）'):'')),el('span',{},t('分母：{0}',[h.metric==='reach'?h.valid_rounds+t(' 个有效回合'):h.metric==='kills'||h.metric==='deaths'?h.observed_seconds+t(' 次事件'):h.observed_seconds.toFixed(0)+t(' 玩家·秒')])))}
function renderHeatPanel(){
  const root=E('wbHeat');root.replaceChildren(el('h2',{},t('热力图')));
  const metric=el('select',{'aria-label':t('指标')},...[['dwell',t('位置停留密度')],['reach',t('回合到达率')],['kills',t('击杀位置')],['deaths',t('阵亡位置')],['scoped_dwell',t('开镜停留（需真实 is_scoped）')]].map(([v,l])=>el('option',{value:v},l)));metric.value=S.heat.metric;
  if(!resA?.capabilities?.scoped)metric.querySelector('[value=scoped_dwell]').disabled=true;
  metric.onchange=()=>{S.heat.metric=metric.value;save();loadHeat().catch(e=>note(e.message))};
  const cell=el('select',{'aria-label':t('网格')},...[[8,t('细 8px')],[16,t('中 16px')],[32,t('粗 32px')]].map(([v,l])=>el('option',{value:v},l)));cell.value=S.heat.cell;cell.onchange=()=>{S.heat.cell=+cell.value;save();loadHeat().catch(e=>note(e.message))};
  const sm=el('input',{type:'range',min:0,max:4,step:1,value:S.heat.smooth,title:t('平滑半径')});sm.oninput=()=>{S.heat.smooth=+sm.value;save();heatRecolor();draw()};
  const pal=el('select',{'aria-label':t('配色')},el('option',{value:'thermal'},t('经典热力')),el('option',{value:'mission'},t('任务红')));pal.value=S.heat.palette||'thermal';pal.onchange=()=>{S.heat.palette=pal.value;save();heatRecolor();draw()};
  root.append(el('div',{class:'wb-row'},metric,cell,pal),el('label',{class:'field inline'},t('平滑半径'),sm));
  for(const [h,label] of [[heatA,compare()?t('当前组'):t('样本')],[heatB,t('职业参考')]])if(h)root.append(el('p',{class:'wb-sum'},el('b',{},label),' '+(h.metric==='kills'||h.metric==='deaths'?t('{0} 个有效回合 · {1} 次事件',[h.valid_rounds,h.observed_seconds]):t('{0} 个有效回合 · {1} 玩家·秒',[h.valid_rounds,h.observed_seconds.toFixed(0)]))));
  if(compare()){if(!resB?.counts.rounds)root.append(el('p',{class:'wb-note warn'},t('参考组在相同地图/阵营/对齐/时间条件下没有有效回合，无法对照。')));
    if(heatCompareInfo)for(const n of heatCompareInfo.notes)root.append(el('p',{class:'wb-note warn'},'⚠ '+t(n)))}
  const defs={dwell:t('选定玩家在各格累计停留的存活秒数 ÷ 有效观察时长。每个采样按到下一采样的真实间隔计时（>1 秒视为缺失），改变采样频率不会成比例放大；阵亡后与缺失坐标不计入分子和分母。'),
    reach:t('有多少比例的有效回合中，至少一名计入玩家经过该格（相邻采样间按线段补全经过的格子）。分母为有效回合数。'),scoped_dwell:t('仅统计 is_scoped=true 的存活秒数 ÷ 有效观察时长；字段来自补充解析。'),kills:t('所选阵营玩家完成击杀时自己所在的位置 ÷ 击杀总数。'),deaths:t('所选阵营玩家阵亡时的位置 ÷ 阵亡总数。')};
  const info=[el('p',{},defs[S.heat.metric]),el('p',{class:'wb-note'},t('热力图只表达活动分布，不直接表示胜率或战术优劣。'))];
  for(const [h,label] of [[heatA,compare()?t('当前组'):t('样本')],[heatB,t('职业参考')]])if(h)info.push(el('dl',{class:'wb-kv'},el('dt',{},label),el('dd',{},t('{0} 个有效回合 · {1} 个玩家回合',[h.valid_rounds,h.player_rounds])),el('dt',{},t('有效观察')),el('dd',{},t('{0} 玩家·秒（本楼层 {1}）',[h.observed_seconds.toFixed(1),h.on_floor_seconds.toFixed(1)])),el('dt',{},t('分母')),el('dd',{},t(h.denominator))));
  if(compare())info.push(el('p',{class:'wb-note'},heatCompareInfo?.differences_allowed?t('口径一致：可比较同一格的占比差异。第一版仍并排显示，不叠加差值图。'):t('口径不完全一致：只并排显示，不提供差值。')));
  root.append(sec('ⓘ '+t('指标口径与样本'),false,...info));
  root.append(el('div',{id:'wbCell'},el('p',{class:'wb-hint'},t('点击地图上的热区，列出实际贡献该区域的回合。'))));
}
async function heatCell(which,cx,cy){heatSel={which,cx,cy};draw();
  const body={query:buildQuery('a'),unchecked:S.unchecked,metric:S.heat.metric,floor:S.floor,cell:S.heat.cell,cx,cy,radius:S.heat.smooth,which};if(which==='b'){body.query_b=buildQuery('b');body.unchecked_b=[]}
  const d=await post('/api/workbench/cell',body);const root=E('wbCell');
  root.replaceChildren(sec(t('热区贡献回合（{0}）· {1}',[which==='b'?t('参考组'):t('当前'),d.total_contributors]),true,
    d.contributors.length?el('div',{class:'wb-lines'},...d.contributors.map(c=>line('',`${c.name.replace(/\.dem$/,'')} R${c.round}`,S.heat.metric==='reach'?c.players.map(x=>nm(c.match,x)).join('/'):c.value.toFixed(1)+t(' 玩家·秒'),ibtn('▶',t('▶ 播放贡献过程'),()=>openSingle(c.match,c.round,c.evidence.start,c.evidence.end,c.evidence.players))))):el('p',{},t('该区域没有贡献回合。'))));
}

/* ---------------- grenades ---------------- */
let nadeDots={a:[],b:[]};
async function loadNades(){
  if(!playing)tNow=+E('wbTime').max;timeLabel();
  const v=++nadeVer;if(!resA?.counts.rounds){nadeA=null;cmpNade=null;renderNadePanel();draw();return}
  const base={query:buildQuery('a'),unchecked:S.unchecked,space_tol:S.nade.space,time_tol:S.nade.time};note(t('正在整理道具…'));
  const d=compare()&&resB?.counts.rounds?await post('/api/workbench/grenades',{...base,query_b:buildQuery('b'),unchecked_b:[]}):await post('/api/workbench/grenades',{...base,kinds:null});
  if(v!==nadeVer)return;if(d.items&&d.a_rounds!==undefined){cmpNade=d;nadeA=null}else{nadeA=d;cmpNade=null}
  note(t('道具 {0} 颗',[(cmpNade||nadeA).items.length]));renderNadePanel();draw();
}
function visibleNades(which){
  const src=cmpNade?cmpNade.items.filter(i=>i.group===which):(which==='a'?nadeA?.items||[]:[]);
  return src.filter(i=>S.nade.kinds.includes(i.kind)&&(!S.nade.player||i.player===S.nade.player.split(':')[1]&&i.match===S.nade.player.split(':')[0])&&i.t<=tNow+1e-6&&(!box||i.position&&i.position[0]>=box[0]&&i.position[0]<=box[2]&&i.position[1]>=box[1]&&i.position[1]<=box[3]))}
function drawNades(ctx,k,which){
  const items=visibleNades(which),cl=(cmpNade||nadeA)?.clusters||[],selected=cl.find(c=>c.id===selCluster);nadeDots[which]=[];
  const lg=E(which==='b'?'wbLegendB':'wbLegendA');lg.replaceChildren(...Object.entries(KIND_NAME).map(([k2,n])=>el('span',{},el('i',{class:'sw',style:`background:${KIND_COLOR[k2]}`}),n)),el('span',{},t('□ 实体起点 · 线＝解析器轨迹')));
  if(which==='b'&&!cmpNade){lg.replaceChildren(t('参考组没有可比回合'));return}
  for(const i of items){if(i.floor!==S.floor||!i.position)continue;const [u,v]=px(i.position),on=!selected||selected.members.includes(i.id),hl=selNade===i.id;
    ctx.globalAlpha=on?1:.18;
    if(S.showTraj&&i.trajectory){ctx.beginPath();let st=false;for(const q of i.trajectory){if(floorOf(q[3])!==S.floor){st=false;continue}const [a,b]=px([q[1],q[2]]);if(!st){ctx.moveTo(a,b);st=true}else ctx.lineTo(a,b)}ctx.strokeStyle=KIND_COLOR[i.kind];ctx.lineWidth=(hl?2.5:1.2)*k;ctx.globalAlpha=on?(hl?.95:.5):.1;ctx.stroke();ctx.globalAlpha=on?1:.18;
      if(i.origin&&floorOf(i.origin[2])===S.floor){const [a,b]=px(i.origin);ctx.strokeStyle=KIND_COLOR[i.kind];ctx.lineWidth=1.3*k;ctx.strokeRect(a-3*k,b-3*k,6*k,6*k)}}
    dot(ctx,u,v,hl?8:5.5,KIND_COLOR[i.kind],hl?'#fff':'#0b0c0e',k);nadeDots[which].push({u,v,i})}
  ctx.globalAlpha=1;
  if(selected&&selected.floor===S.floor){const [u,v]=px(selected.centroid);ctx.strokeStyle='#ffd77a';ctx.lineWidth=2*k;ctx.setLineDash([5*k,4*k]);ctx.beginPath();ctx.arc(u,v,Math.max(12,selected.spread/radarMeta.scale+8),0,Math.PI*2);ctx.stroke();ctx.setLineDash([])}
}
function renderNadePanel(){
  const root=E('wbNade');root.replaceChildren(el('h2',{},t('道具')));const d=cmpNade||nadeA;
  if(!d){root.append(el('p',{},t('没有可分析的回合。')));return}
  const cov=nadeA?.trajectory_coverage||{with_trajectory:d.items.filter(i=>i.trajectory).length,total:d.items.length};
  root.append(el('p',{class:'wb-note'},t('{0} 颗 · 真实轨迹 {1} · 按时间轴累计显示',[cov.total,cov.with_trajectory+'/'+cov.total])));
  const kinds=el('div',{class:'wb-chipset'},...Object.entries(KIND_NAME).map(([k,n])=>{const b=el('button',{class:'kchip','aria-pressed':String(S.nade.kinds.includes(k))},el('i',{class:'dot',style:`background:${KIND_COLOR[k]}`}),n);b.onclick=()=>{S.nade.kinds=S.nade.kinds.includes(k)?S.nade.kinds.filter(x=>x!==k):[...S.nade.kinds,k];save();b.setAttribute('aria-pressed',String(S.nade.kinds.includes(k)));renderNadeList();draw()};return b}));
  const players=[...new Set(d.items.filter(i=>i.player).map(i=>i.match+':'+i.player))].sort();const pl=el('select',{'aria-label':t('全部玩家')},el('option',{value:''},t('全部玩家')),...players.map(p=>{const m=(catalog?.matches||[]).find(x=>x.id===p.split(':')[0]);return el('option',{value:p},(m?m.name.replace(/\.dem$/,'').slice(0,18):'')+' '+nm(p.split(':')[0],p.split(':')[1]))}));pl.value=S.nade.player;pl.onchange=()=>{S.nade.player=pl.value;save();renderNadeList();draw()};
  root.append(kinds,el('div',{class:'wb-row'},pl));
  const shown=d.clusters.filter(c=>c.occurrences>=2).slice(0,25),list=el('div',{class:'wb-lines',id:'wbClusters'});
  for(const c of shown){const meta=cmpNade?t('当前 {0}% · 参考 {1}%',[(c.a_rate*100).toFixed(0),(c.b_rate*100).toFixed(0)]):t('{0} 回合 · {1}s',[c.occurrences,Number(c.median_t).toFixed(1)]);
    const ln=line(KIND_COLOR[c.kind],`${c.id} ${KIND_NAME[c.kind]}${c.floor==='lower'?' · '+t('下层'):''}`,meta,
      ibtn(selCluster===c.id?'◉':'◎',selCluster===c.id?t('取消高亮'):t('在地图高亮'),()=>{selCluster=selCluster===c.id?null:c.id;if(selCluster)S.floor=c.floor;syncControls();renderNadePanel();draw()}),
      ibtn('▶',t('▶ 依次核对'),()=>{const items=(d.items||[]).filter(i=>c.members.includes(i.id));playlist=items.map(i=>({match:i.match,round:i.round,name:i.name,start:i.evidence.start}));const i=items[0];if(i)openSingle(i.match,i.round,i.evidence.start,i.evidence.end,i.evidence.players)}));
    if(selCluster===c.id)ln.classList.add('sel');
    ln.title=cmpNade?t('当前 {0}/{1} 回合（{2}%）· 参考 {3}/{4}（{5}%）· 中位 {6}s / {7}s',[c.a_occurrences,cmpNade.a_rounds,(c.a_rate*100).toFixed(0),c.b_occurrences,cmpNade.b_rounds,(c.b_rate*100).toFixed(0),c.a_median_t??'—',c.b_median_t??'—']):t('{0} 个回合 · 共 {1} 颗 · 中位对齐时间 {2}s · 半径 {3} 单位',[c.occurrences,c.count,c.median_t,c.spread.toFixed(0)]);
    list.append(ln);if(cmpNade&&c.difference.length)list.append(el('small',{class:'wb-diff'},t('观测差异：')+c.difference.map(x=>t(x)).join(t('、'))+t('（不代表优劣）')))}
  if(!shown.length)list.append(el('p',{class:'wb-note'},t('没有在 ≥2 个回合重复出现的组合。')));
  root.append(sec(t('候选组合（相近位置 · 相近时间）')+' · '+shown.length,true,list));
  const sp=el('input',{type:'number',min:20,max:800,step:10,value:S.nade.space}),tm=el('input',{type:'number',min:.5,max:30,step:.5,value:S.nade.time});
  sp.onchange=tm.onchange=()=>{S.nade.space=+sp.value;S.nade.time=+tm.value;save();loadNades().catch(e=>note(e.message))};
  root.append(sec(t('组合参数'),false,el('div',{class:'wb-row'},el('label',{class:'field inline'},t('组合空间容差'),sp,t('单位')),el('label',{class:'field inline'},t('时间容差'),tm,t('秒'))),el('p',{class:'wb-note'},t(d.clusters[0]?.basis||'')+t('。不同楼层不会凭平面距离合并。'))));
  if(d.combos?.length)root.append(sec(t('同回合组合出现次数')+' · '+d.combos.length,false,el('div',{class:'wb-lines'},...d.combos.slice(0,8).map(c=>line('',c.clusters.join(' + '),t('{0} 回合',[c.occurrences]))))));
  const sort=el('select',{'aria-label':t('按对齐时间')},el('option',{value:'time'},t('按对齐时间')),el('option',{value:'round'},t('按回合')));sort.value=S.nade.sort;sort.onchange=()=>{S.nade.sort=sort.value;save();renderNadeList()};
  const listSec=sec(t('道具列表'),false,sort,el('div',{id:'wbNadeList'}));listSec.id='wbNadeSec';root.append(listSec);
  root.append(sec(t('说明'),false,...(d.limits||[]).map(l=>el('p',{class:'wb-note'},t(l))),...(cmpNade?[el('p',{class:'wb-note'},t(cmpNade.note))]:[])));
  renderNadeList();
}
function renderNadeList(){
  const root=E('wbNadeList');if(!root)return;const items=[...visibleNades('a'),...(cmpNade?visibleNades('b'):[])].filter(i=>!selCluster||((cmpNade||nadeA).clusters.find(c=>c.id===selCluster)?.members||[]).includes(i.id));
  items.sort(S.nade.sort==='round'?(a,b)=>a.name.localeCompare(b.name)||a.round-b.round||a.t-b.t:(a,b)=>a.t-b.t);
  const sum=E('wbNadeSec')?.querySelector('summary');if(sum)sum.textContent=t('道具列表')+' · '+items.length;
  root.replaceChildren(el('p',{class:'wb-note'},t('{0} 颗（时间 ≤ 对齐后 {1}s{2}）',[items.length,tNow.toFixed(1),box?t('，在框选区域内'):''])));
  const list=el('div',{class:'wb-lines'});
  for(const i of items.slice(0,200)){const ln=line(KIND_COLOR[i.kind],`${nm(i.match,i.player)||t('未知')} · ${i.name.replace(/\.dem$/,'').slice(0,16)} R${i.round}`,(cmpNade?(i.group==='a'?t('当前 · '):t('参考 · ')):'')+i.t.toFixed(1)+'s'+(i.trajectory?'':' · '+t('无轨迹')),
      ibtn('▶',t('▶ 播放前后过程'),()=>openSingle(i.match,i.round,i.evidence.start,i.evidence.end,i.evidence.players)));
    ln.dataset.nade=i.id;if(selNade===i.id)ln.classList.add('sel');
    ln.title=t('{0}{1} R{2} · 对齐后 {3}s（原始 {4}s）· {5}',[cmpNade?(i.group==='a'?t('当前 · '):t('参考 · ')):'',i.name.replace(/\.dem$/,''),i.round,i.t.toFixed(1),i.raw.toFixed(1),i.floor==='lower'?t('下层'):t('上层')])+'\n'+(i.trajectory?t('真实起点（实体首帧）+ 轨迹 {0} 点 · 关联依据 {1}',[i.trajectory.length,i.link_basis]):t('无真实轨迹：只显示事件作用点'));
    ln.onmouseenter=()=>{selNade=i.id;draw()};list.append(ln)}
  root.append(list);
  if(items.length>200)root.append(el('p',{class:'wb-note'},t('列表只显示前 200 颗；请用类型/玩家/框选缩小范围（地图上全部显示）。')));
}

/* ---------------- evidence jump into the existing single-round player ---------------- */
async function openSingle(mid,n,start,end,players){
  setMode('single');
  if(typeof match==='undefined'||match!==mid)await open(mid,n);else await loadRound(n);
  if(typeof playEvidence==='function')playEvidence({start:Math.max(0,start),end:Math.max(start+.5,end),players:players||[]});
}
window.wbOpenSingle=openSingle;
// Performance self-check (no model calls): keep the first n selected rounds, load them in batches, time 60 draws.
window.wbBench=async n=>{const all=[...(resA?.selection||[]).map(s=>s.key),...S.unchecked];S.unchecked=all.slice(n);await refresh();if(S.mode!=='multi'){S.mode='multi'}
  const t0=performance.now();await loadTracks();const load=performance.now()-t0;tNow=(+S.f.w0+ +S.f.w1)/2;const d0=performance.now();for(let i=0;i<60;i++){tNow+=.05;draw()}const per=(performance.now()-d0)/60;
  return {rounds:tracksA.length,players:tracksA.reduce((a,r)=>a+r.players.length,0),load_ms:Math.round(load),draw_ms:+per.toFixed(2),max_fps_by_draw:Math.round(1000/Math.max(per,0.001))}};
window.wbDebug=()=>({mode:S.mode,source:S.source,compare:S.compare,cmpNade:!!cmpNade,nadeA:!!nadeA,resB:resB?.counts,heatB:!!heatB,tracks:tracksA.length});

/* ---------------- Eregion analysis of the current selection ---------------- */
let agentPreview=null;
function renderAgent(){
  const root=E('wbAgent');root.replaceChildren(el('h2',{},t('Agent 分析当前选择')));
  root.append(el('p',{},t('筛选、播放、热力图与道具统计均为本地计算（0 次模型调用）。点击下方按钮后才生成证据包；启动分析需要再次确认。')));
  root.append(btn(t('预览发送内容'),async()=>{agentPreview=await post('/api/workbench/agent/preview',agentBody());renderAgentPreview()}));
  root.append(el('div',{id:'wbAgentPreview'}),el('div',{id:'wbAgentResult'}));
  if(S.agentJob)pollAgent();
}
function agentBody(){const b={query:buildQuery('a'),unchecked:S.unchecked,lang:I18N.lang};if(compare()&&resB?.counts.rounds){b.query_b=buildQuery('b');b.unchecked_b=[]}return b}
function renderAgentPreview(){
  const p=agentPreview,root=E('wbAgentPreview');root.replaceChildren();if(!p)return;
  const consent=el('input',{type:'checkbox'});
  root.append(el('dl',{class:'wb-kv'},el('dt',{},t('有效样本')),el('dd',{},t('{0} 回合 / {1} 场',[p.packet.a.valid_rounds,p.packet.a.matches])+(p.packet.b?t(' ｜ 参考 {0} 回合',[p.packet.b.valid_rounds]):'')),el('dt',{},t('证据条目')),el('dd',{},String(p.packet.evidence.length)),el('dt',{},t('大小')),el('dd',{},p.characters+t(' 字符')),
    el('dt',{},t('发送到')),el('dd',{},p.destination.host||t('尚未配置模型服务')),el('dt',{},t('调用上限')),el('dd',{},t('最多 2 次（第二次仅用于补证或结构修复）；输入预算 60000，单次输出 ≤12000 tokens，300 秒'))),
    el('p',{class:'wb-note'},t(p.scope)),...(p.packet.incomparable||[]).map(x=>el('p',{class:'wb-note'},t('⚠ 不可比：')+t(x))),
    el('label',{class:'wb-check'},consent,t('允许发送上述匿名证据进行本次分析')),
    btn(t('分析当前选择（最多 2 次调用）'),async()=>{if(!consent.checked)throw Error(t('请先勾选发送授权'));const s=await post('/api/workbench/agent/start',{...agentBody(),consent:true,endpoint_host:p.destination.host});S.agentJob=s.id;save();if(s.deduplicated)note(t('相同证据包已有结果，未重复调用模型'));pollAgent()}));
}
async function pollAgent(){
  clearTimeout(agentTimer);const id=S.agentJob;if(!id)return;let s;try{s=await get('/api/workbench/agent/job?id='+id)}catch(e){S.agentJob='';save();return}
  if(id!==S.agentJob)return;const root=E('wbAgentResult');if(!root)return;
  const names={running:t('分析中'),completed:t('已完成'),output_truncated:t('模型输出被截断（思考占满输出上限）'),invalid_output:t('模型输出格式无效'),budget_exhausted:t('预算耗尽（保留本地分析）'),cancelled:t('已取消'),interrupted:t('服务重启，任务中断'),model_failed:t('模型未完成（保留本地分析）')};
  const u=s.usage||{};root.replaceChildren(el('p',{},t('{0} · 模型调用 {1}/{2}',[names[s.status]||s.status,s.model_calls,s.max_calls])+(u.input_tokens!=null?t(' · 输入 {0} / 输出 {1} tokens',[u.input_tokens,u.output_tokens]):'')));
  if(s.status==='running'){root.append(btn(t('取消'),async()=>{await post('/api/workbench/agent/cancel',{id});note(t('正在取消；已发出的调用可能持续到超时'))}));agentTimer=setTimeout(pollAgent,1500)}
  if(s.status!=='running'&&!s.result)root.append(el('p',{class:'wb-note'},t('未完成部分：模型发现。本地筛选、热力与道具统计不受影响，可继续使用。')));
  const ev=Object.fromEntries((s.evidence||[]).map(e=>[e.id,e]));
  if(s.result){root.append(el('p',{class:'coach-summary'},t('Agent 推断：')+s.result.summary));
    for(const f of s.result.findings){const box=el('div',{class:'wb-finding'},el('h3',{},f.conclusion));
      box.append(el('p',{},el('span',{class:'wb-tag fact'},t('事实')),f.facts.join(t('；'))),el('p',{},el('span',{class:'wb-tag infer'},t('模型推断')),f.inference),el('p',{},el('span',{class:'wb-tag unc'},t('不确定性')),f.uncertainty),el('p',{},el('span',{class:'wb-tag advice'},t('建议')),f.recommendation));
      for(const id2 of f.evidence_ids){const e=ev[id2];if(e)box.append(btn(`▶ ${id2} · ${e.match_alias} R${e.round} ${e.start.toFixed(0)}–${e.end.toFixed(0)}s`,()=>openSingle(e.match,e.round,e.start,e.end,e.players)))}
      root.append(box)}
    for(const m of s.result.missing||[])root.append(el('p',{class:'wb-note'},t('缺失：')+m))}
}

/* ---------------- init ---------------- */
const wait=setInterval(async()=>{if(typeof token==='undefined'||!token)return;clearInterval(wait);
  restore();const params=new URLSearchParams(location.search);
  const legacy=params.has('match')||params.has('comparison_job')||params.has('case');
  if(params.get('wbmode')&&MODES.includes(params.get('wbmode')))S.mode=params.get('wbmode');else if(legacy)S.mode='single';
  setFilters(S.filtersOpen??false);sideTab(false);
  syncControls();try{await loadCatalog();fit();await refresh()}catch(e){note(e.message)}
  if(params.get('view')==='review')S.mode='single';
  setMode(S.mode,params.get('view')==='review');
  if(['room','profile'].includes(params.get('view')))showView(params.get('view'));
  if(params.get('view')==='matches'||(!legacy&&!(catalog?.matches||[]).length&&S.mode!=='single'))showView('matches');
},100);
})();
