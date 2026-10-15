#!/usr/bin/env node
// Records the Chinese product video from YOUR running app and YOUR demos:
// real app footage (frame-accurate fake clock, scripted cursor, on-screen captions) + motion-graphics cards,
// then adds synthesised background music. No voice-over.
//
//   node record.cjs                 full video  -> out/roundcrafter_zh.mp4 (+ .srt)
//   node record.cjs --preview       a few stills per shot in out/preview/ (fast check of every shot)
//   node record.cjs --only lab,heat record just these shots
//   node record.cjs --list          print the plan (which shots run with your data, and why some are skipped)
//
// Settings: video.config.json next to this file (see video.config.example.json). Everything is optional.
'use strict';
const fs=require('fs'),path=require('path'),{spawn,spawnSync}=require('child_process');
const {chromium}=require('playwright');

const HERE=__dirname;
const ARGS=process.argv.slice(2);
const flag=n=>ARGS.includes('--'+n);
const opt=n=>{const i=ARGS.indexOf('--'+n);return i>=0?ARGS[i+1]:null};
const CFG={app:'http://127.0.0.1:8790',out:'out/roundcrafter_zh.mp4',match:null,round:null,anonymize:'others',python:process.platform==='win32'?'python':'python3',
  lab:{map:'de_dust2',mode:'auto',origin:null,target:null},skip:[],...readJson(path.join(HERE,'video.config.json'))};
if(opt('app'))CFG.app=opt('app');if(opt('out'))CFG.out=opt('out');
const PREVIEW=flag('preview'),ONLY=opt('only')?opt('only').split(','):null;
const OUT=path.resolve(HERE,CFG.out),OUTDIR=path.dirname(OUT);
const FPS=30,DT=1000/FPS,W=1920,H=1080;
let WB_MAPS=['de_dust2','de_nuke'];   // maps the multi-round workbench supports (read from the app at start)

function readJson(p){try{return JSON.parse(fs.readFileSync(p,'utf8'))}catch(e){if(e.code!=='ENOENT')throw new Error(p+': '+e.message);return {}}}
const log=(...a)=>console.log('[video]',...a);
async function api(p){const r=await fetch(CFG.app+p);if(!r.ok)throw new Error(p+' → HTTP '+r.status);return r.json()}

// ---------------------------------------------------------------- tactic-board / lab points (radar UV 0..1)
const BOARD={
  de_dust2:{arrows:[[[0.40,0.88],[0.68,0.66]],[[0.88,0.56],[0.82,0.22]]],smokes:[[0.71,0.21],[0.49,0.40]],side:'T'},
  de_nuke:{arrows:[[[0.10,0.56],[0.42,0.57]],[[0.45,0.60],[0.57,0.53]]],smokes:[[0.62,0.48],[0.70,0.58]],side:'T'},
  de_mirage:{arrows:[[[0.84,0.37],[0.55,0.74]],[[0.80,0.33],[0.40,0.46]]],smokes:[[0.44,0.72],[0.47,0.63]],side:'T'},
};
const LAB_POINTS={de_dust2:{origin:[0.500,0.640],target:[0.490,0.410]},de_nuke:{origin:[0.300,0.560],target:[0.560,0.640]},de_mirage:{origin:[0.700,0.430],target:[0.520,0.440]}};

// ---------------------------------------------------------------- discover what this machine has
async function discover(){
  const status=await api('/api/status').catch(e=>{throw new Error(`App not reachable at ${CFG.app} (${e.message}). Start it first (./start-tactics.ps1)`)});
  const [demos,ids]=await Promise.all([api('/api/demos'),api('/api/demo/identities')]);
  const page=await (await fetch(CFG.app+'/demos')).text();const sel=page.match(/<select id="wbMap">([\s\S]*?)<\/select>/);
  if(sel)WB_MAPS=[...sel[1].matchAll(/value="([^"]+)"/g)].map(x=>x[1]);if(CFG.workbenchMaps)WB_MAPS=CFG.workbenchMaps;
  const kind=Object.fromEntries(ids.matches.map(m=>[m.id,m.identity||{kind:'unknown'}]));
  const done=demos.matches.filter(m=>m.status==='completed').map(m=>({...m,identity:kind[m.id]||{kind:'unknown'}}));
  const isPro=m=>m.identity.kind==='professional';
  const mine=done.filter(m=>!isPro(m));
  let match=CFG.match?done.find(m=>m.id===CFG.match||m.name===CFG.match):null;
  if(CFG.match&&!match)throw new Error('match '+CFG.match+' not found in the library');
  // Featured match: your own (player) demo on a workbench map if you have one, otherwise a pro demo on a workbench map
  // ("featured": "pro" forces a pro demo). Unclassified demos are only a last resort.
  const onWb=m=>WB_MAPS.includes(m.map),newest=xs=>xs.slice().sort((a,b)=>b.rounds-a.rounds||b.created_at-a.created_at)[0];
  if(!match&&CFG.featured!=='pro')match=newest(mine.filter(m=>onWb(m)&&m.identity.kind==='player'));
  if(!match)match=newest(done.filter(m=>onWb(m)&&isPro(m)))||newest(mine.filter(onWb))||done[0];
  if(!match)throw new Error('No parsed match in the library. Import at least one demo in the app first.');
  const pros=done.filter(m=>isPro(m)&&m.map===match.map&&m.id!==match.id&&(!m.sha256||m.sha256!==match.sha256));
  const cat=await api('/api/workbench/catalog').catch(()=>({matches:[]}));
  const rounds=(cat.matches.find(m=>m.id===match.id)||{}).rounds||[];
  let round=CFG.round||rounds[Math.min(5,rounds.length-1)]||1,side=(BOARD[match.map]||{}).side||'T',compare=null;
  // Find a round of yours that actually has comparable pro rounds, so the comparison shot shows real candidates.
  if(pros.length&&!skipped('procompare')){
    // Scan a spread of rounds and keep the best-matching pro round (from a different match).
    const tryRounds=CFG.round?[CFG.round]:rounds.filter(n=>n>=3).slice(0,16);let best=-1;
    for(const n of tryRounds)for(const s of ['T','CT']){
      const c=await api(`/api/demo/compare?match=${match.id}&round=${n}&side=${s}`).catch(()=>null);
      const top=(c?.candidates||[]).find(x=>x.match!==match.id);
      if(top&&(top.score??0)>best){best=top.score??0;round=n;side=s;compare=top}}
  }
  const [hubPlayers,account,lab]=await Promise.all([api('/api/hub/players').catch(()=>({players:[]})),api('/api/hub/account').catch(()=>({linked:false})),api('/api/lab/maps').catch(()=>({maps:[]}))]);
  const labMap=lab.maps.includes(CFG.lab.map)?CFG.lab.map:lab.maps.includes(match.map)?match.map:lab.maps[0];
  return {status,match,pros,round,side,compare,players:hubPlayers.players,account,labMap,done,
    wbSource:match.identity.kind==='player'?'player':isPro(match)?'pro':'unknown',featuredPro:isPro(match),proVerified:pros.some(m=>m.identity.verified)};
}
const skipped=id=>(CFG.skip||[]).includes(id)||(ONLY&&!ONLY.includes(id));

// ---------------------------------------------------------------- privacy: alias other people's names
async function aliases(d){
  if(CFG.anonymize==='none')return [];
  const CALL=['Atlas','Nova','Kestrel','Vega','Rook','Orbit','Flint','Ember','Quasar','Lumen','Comet','Drift','Pulsar','Zenith','Echo','Halo','Ion','Jett','Kilo','Lynx'];
  const own=new Set();if(d.account.linked){own.add(d.account.persona);for(const p of d.players)if(p.steamid===d.account.steamid)own.add(p.name)}
  const names=new Set();
  const scope=CFG.anonymize==='all'?d.done:d.done.filter(m=>m.identity.kind!=='professional');
  for(const m of scope){const r=await api('/api/demo/players?id='+m.id).catch(()=>({names:{}}));for(const n of Object.values(r.names||{}))names.add(n)}
  if(CFG.anonymize==='all')for(const p of d.players)names.add(p.name);
  else{const proNames=new Set();for(const m of d.done.filter(m=>m.identity.kind==='professional')){const r=await api('/api/demo/players?id='+m.id).catch(()=>({names:{}}));for(const n of Object.values(r.names||{}))proNames.add(n)}
    for(const p of d.players)if(!proNames.has(p.name))names.add(p.name)
    for(const n of proNames)names.delete(n)}   // a pro who also appears in an unclassified demo keeps their real name
  if(CFG.anonymize!=='all')for(const n of own)names.delete(n);
  return [...names].filter(n=>n&&n.length>=2).sort((a,b)=>b.length-a.length).map((n,i)=>[n,CALL[i]||'Player'+String(i+1).padStart(2,'0')]);
}
// Runs inside the page before any app script: rewrites names in every JSON response, masks SteamIDs on screen.
function privacyInit({pairs,all}){
  const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  // One single-pass pattern, so an alias is never rewritten by a later rule:
  //  - any name that is a whole JSON string ("name")
  //  - names of 4+ characters containing a letter, also inside longer text (Agent findings etc.)
  // Short or numeric names ("123", "Dog") are only replaced as whole strings, so numbers and keys stay intact.
  const map=new Map(pairs.map(([n,a])=>[JSON.stringify(n).slice(1,-1),a]));
  const keys=[...map.keys()],loose=keys.filter(k=>k.length>=4&&/\p{L}/u.test(k));
  const rx=keys.length?new RegExp('"(?:'+keys.map(esc).join('|')+')"'+(loose.length?'|(?<![\\p{L}\\p{N}_])(?:'+loose.map(esc).join('|')+')(?![\\p{L}\\p{N}_])':''),'gu'):null;
  const sub=m=>m[0]==='"'&&m.length>1&&m.at(-1)==='"'&&map.has(m.slice(1,-1))?'"'+map.get(m.slice(1,-1))+'"':map.get(m)??m;
  const of=window.fetch;
  window.fetch=async(...a)=>{const r=await of(...a);if(!rx||!(r.headers.get('content-type')||'').includes('json'))return r;
    const t=(await r.text()).replace(rx,sub);return new Response(t,{status:r.status,statusText:r.statusText,headers:r.headers})};
  const SID=/7656119\d{10}/g,mask=s=>s.replace(SID,m=>m.slice(0,7)+'••••••••••');
  const walk=n=>{if(n.nodeType===3){if(SID.test(n.data)){SID.lastIndex=0;n.data=mask(n.data)}SID.lastIndex=0}else for(const c of n.childNodes)walk(c)};
  new MutationObserver(ms=>{for(const m of ms){if(m.type==='characterData')walk(m.target);for(const x of m.addedNodes)walk(x)}}).observe(document,{subtree:true,childList:true,characterData:true});
  if(all)document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent='img.avatar{visibility:hidden}';document.head.append(s)});
}

// ---------------------------------------------------------------- the shot list
// kind 'mg' = motion-graphics card from scenes.html; kind 'app' = real app footage.
// acts: [verb, t(s), ...]   move: [ 'move', target, t, dur ]   target = CSS selector | [x,y] px | [u,v] radar UV
function buildShots(d){
  const m=d.match,mapName=m.map.replace('de_','').replace(/^./,c=>c.toUpperCase()),B=BOARD[m.map];
  const wb=WB_MAPS.includes(m.map),hasPlayers=d.account.linked||d.players.length>0;
  const S=[];const add=(s,why)=>{if(why){s.why=why}S.push(s)};
  add({id:'title',kind:'mg',scene:'s01',dur:5});
  add({id:'library',kind:'app',dur:5,caps:[[0,'导入 demo · 几秒钟解析完成']],acts:[
    ['move',`.match-card:has-text(${JSON.stringify(m.name.replace(/\.dem$/,''))})`,0.4,1.1],['click',1.7],['until',1.8,`document.querySelector('#round option')`,20000],['wait',1.9,1200]]});
  add({id:'replay',kind:'app',dur:14,caps:[[0,'转播级 2D 回放 · 每秒 16 帧插值'],[5,'真实站位、血量与装备'],[9.5,'烟、闪、火、雷按真实轨迹出现']],acts:[
    ['move','#round',0.3,0.8],['select',1.2,'#round',String(d.round)],['wait',1.25,1500],
    ['move','#side',1.5,0.5],['select',2.0,'#side',d.side],
    ['move','#speed',2.2,0.5],['select',2.8,'#speed','2'],
    ['move','text=播放',3.1,0.6],['click',3.8],['move',[1250,600],4.3,1.4],['move',[1300,700],9.5,1.6]]});
  add({id:'stats',kind:'app',dur:5.5,caps:[[0,'整场数据自动统计：击杀 · ADR · KAST · 爆头率 · Rating']],acts:[
    ['move','#statsTab',0.3,0.9],['click',1.3],['wait',1.35,900],['move',[1720,520],2.0,1.4]]});
  add({id:'agent',kind:'app',dur:6.5,caps:[[0,'AI 分析师先读证据包：每次进点、道具、击杀都带时间']],acts:[
    ['move','#analysisTab',0.3,0.9],['click',1.3],['wait',1.35,900],['move',[1720,700],2.0,1.0],['wheel',3.2,260],['wheel',4.6,260]]});
  add({id:'evidence',kind:'mg',scene:'s05',dur:7,caps:[[0,'工具核对关键时间窗 · 结论必须引用证据编号'],[3.8,'本地审核，删掉数据不支持的结论']]});
  add({id:'finding',kind:'mg',scene:'s06',dur:7,caps:[[0,'每条发现：事实 · 推断 · 不确定性 · 建议'],[3.8,'点一下，跳回对应的回放片段']]});
  add({id:'modes',kind:'mg',scene:'s07',dur:6.5,caps:[[0,'四种模式，每种都有严格的调用预算']]});
  add({id:'rag',kind:'mg',scene:'s08',dur:9,caps:[[0,'混合向量检索：先按对局状态过滤，再结合语义与关键词'],[4.6,'中文问题，也能找到英文资料']]});
  // ---- pro comparison from the single-round review
  add({id:'procompare',kind:'app',dur:16,caps:[[0,'职业对照：自动找出同地图、同阵营、局面相似的职业回合'],[6,'按事件对齐，两场并排同步播放'],[11.5,'再让 Agent 解释：职业选手哪里做得不一样']],acts:[
    ['js',0,`document.getElementById('side').value=${JSON.stringify(d.side)};document.getElementById('side').dispatchEvent(new Event('change'))`],
    ['move','#compareTab',0.3,0.8],['click',1.2],['wait',1.25,400],
    ['move','#findComparison',1.6,0.6],['click',2.3],['until',2.35,`[...document.querySelectorAll('#comparisonCandidates button')].length>0`,40000],
    ['move','#comparisonCandidates',2.6,0.8],
    ['move','#comparisonCandidates button',4.6,0.8],['click',5.5],['until',5.55,`!document.getElementById('comparisonViewer').hidden`,30000],['wait',5.6,600],
    ['move','#comparePlay',6.2,0.7],['click',7.0],['move',[960,560],7.6,1.5],
    ['move','#analyzeComparison',11.0,1.2],['move',[1500,640],13.5,1.5],
    ['js',15.9,`document.getElementById('closeComparison')?.click()`]]},
    !d.pros.length?`no professional demo on ${mapName} in your library (mark one as 职业比赛 in 比赛库)`:!d.compare?'no comparable pro round found for your match':null);
  // ---- tactic board
  if(B)add({id:'board',kind:'app',dur:11.5,caps:[[0,'在战术板上画出方案'],[6.8,'一键演示成完整的一回合']],acts:[
    ['move','#mode',0.2,0.8],['click',1.1],['wait',1.15,900],
    ['move','#tbTools [data-tool=arrow]',1.5,0.6],['click',2.2],
    ['drag',2.5,...B.arrows[0],1.0],['drag',3.8,...B.arrows[1],0.9],
    ['move','#tbTools [data-tool=smoke]',4.9,0.6],['click',5.6],['clickUV',6.1,B.smokes[0]],['clickUV',6.5,B.smokes[1]],
    ['move','text=▶ 演示',6.9,0.8],['click',7.8],['move',[1250,560],8.4,1.4]]});
  else add({id:'board',kind:'app',dur:0},'no tactic-board points defined for '+m.map);
  // ---- multi-round workbench
  const wbWhy=!wb?`your match is on ${mapName}; the multi-round workbench supports Dust2 / Nuke`:null;
  add({id:'chap-multi',kind:'mg',scene:'chap1',dur:3.2,chap:{k:'03',en:'MULTI-ROUND',title:'多回合分析',sub:'把几十个回合叠在一起，习惯一眼就能看出来'}},wbWhy);
  const openWb=[
    ['js',0,`const s=document.getElementById('wbSource');s.value=${JSON.stringify(d.wbSource)};s.dispatchEvent(new Event('change'));const mp=document.getElementById('wbMap');if(![...mp.options].some(o=>o.value===${JSON.stringify(m.map)}))mp.add(new Option(${JSON.stringify(mapName)},${JSON.stringify(m.map)}));mp.value=${JSON.stringify(m.map)};mp.dispatchEvent(new Event('change'));`+LIMIT_JS(m.name)],
    ['move','.mc-nav button[data-view=analysis]',0.2,0.8],['click',1.0],['wait',1.05,500],
    ['js',1.1,`if(document.getElementById('wbFilters').offsetParent===null)document.getElementById('wbFilterToggle').click()`],
    ['js',1.15,`try{setMode('heat')}catch{}`],['js',1.2,LIMIT_JS(m.name)],   // don't open on an over-limit overlay
    ['move','#wbSource',1.4,0.6],['wait',2.05,600],
    ['js',2.2,`const s=document.getElementById('wbMap');if(![...s.options].some(o=>o.value===${JSON.stringify(m.map)}))s.add(new Option(${JSON.stringify(mapName)},${JSON.stringify(m.map)}))`],
    ['move','#wbMap',2.3,0.5],
    ['js',3.0,LIMIT_JS(m.name)],   // stay under the overlay limit before switching to the overlay
    ['move','.wb-modes button[data-mode=multi]',3.1,0.6],['click',3.7],['until',3.75,WB_READY,60000]];
  add({id:'multi',kind:'app',dur:12,caps:[[0,d.featuredPro?'多回合分析：所有职业比赛里的同类回合，叠在一张图上':'多回合分析：你所有比赛里的同类回合，叠在一张图上'],[6,'按回合开始、首次进点或下包对齐，一起播放']],acts:[
    ...openWb,['move','#wbAlign',4.4,0.6],['select',5.0,'#wbAlign','first_entry'],['until',5.05,WB_READY,60000],
    ['move','#wbSpeed',5.6,0.6],['select',6.2,'#wbSpeed','2'],['move','#wbPlay',6.5,0.6],['click',7.1],['move',[900,560],7.6,1.6]]},wbWhy);
  add({id:'filters',kind:'app',dur:12,caps:[[0,'筛选：阵营、胜负、下包、存活人数、经济、区域、选手'],[6.5,'每个条件都会显示被排除了多少回合']],acts:[
    ['js',0,`document.getElementById('wbPlay').textContent.includes('暂停')&&document.getElementById('wbPlay').click()`],
    ['move','#wbSide',0.3,0.7],['select',1.1,'#wbSide',d.side==='CT'?'T':'CT'],['until',1.15,WB_READY,60000],['wait',1.2,500],
    ['move','#wbSide',2.0,0.3],['select',2.4,'#wbSide',d.side],['until',2.45,WB_READY,60000],
    ['move','#wbOutcome',3.0,0.7],['select',3.8,'#wbOutcome','win'],['until',3.85,WB_READY,60000],
    ['move','#wbPlant',4.4,0.6],['select',5.1,'#wbPlant','planted'],['until',5.15,WB_READY,60000],
    ['move','#wbChips',5.8,0.8],['move','#wbRoundCount',7.0,0.8],['click',7.9],['wait',7.95,300],['move','#wbRounds',8.4,0.8],['wheel',9.4,240],
    ['js',11.9,`for(const [id,v] of [['wbOutcome','any'],['wbPlant','any']]){const e=document.getElementById(id);e.value=v;e.dispatchEvent(new Event('change'))}`]]},wbWhy);
  add({id:'heat',kind:'app',dur:15,caps:[[0,'热力图：停留密度、到达率、击杀与阵亡位置'],[8,'AWP 开镜热力图：狙击手习惯架在哪里']],acts:[
    ['until',0,WB_READY,60000],
    ['move','.wb-modes button[data-mode=heat]',0.3,0.8],['click',1.2],['until',1.25,WB_READY,60000],['wait',1.3,500],
    ['move','#wbHeat select >> nth=0',2.2,0.7],['select',3.0,'#wbHeat select >> nth=0','reach'],['until',3.05,WB_READY,60000],
    ['select',4.6,'#wbHeat select >> nth=0','kills'],['until',4.65,WB_READY,60000],
    ['select',6.2,'#wbHeat select >> nth=0','deaths'],['until',6.25,WB_READY,60000],
    ['move','#wbWeapon',7.6,0.7],['fill',8.4,'#wbWeapon','awp'],['until',8.45,WB_READY,60000],
    ['move','#wbHeat select >> nth=0',9.0,0.6],['select',9.7,'#wbHeat select >> nth=0','scoped_dwell'],['until',9.75,WB_READY,60000],
    ['move',[880,540],10.4,1.4],
    ['js',14.9,`const w=document.getElementById('wbWeapon');w.value='';w.dispatchEvent(new Event('change'))`]]},wbWhy);
  add({id:'nade',kind:'app',dur:13,caps:[[0,'道具视图：每颗烟、闪、雷、火的落点自动聚类'],[6.5,'按选手筛选，点一下在地图上高亮，或直接播放']],acts:[
    ['until',0,WB_READY,60000],
    ['move','.wb-modes button[data-mode=nade]',0.3,0.8],['click',1.2],['until',1.25,WB_READY,60000],['wait',1.3,500],
    ['move','#wbNade button:has-text("闪光")',2.2,0.7],['click',3.0],['wait',3.05,400],['click',4.0],['wait',4.05,400],
    ['move','#wbNade button:has-text("燃烧")',4.5,0.5],['click',5.1],['wait',5.15,400],['click',5.9],['wait',5.95,400],
    ['move','#wbNade select >> nth=0',6.4,0.6],['select',7.1,'#wbNade select >> nth=0',{index:1}],['until',7.15,WB_READY,60000],['move',[880,560],7.6,0.8],
    ['move','#wbNade select >> nth=0',8.6,0.6],['select',9.2,'#wbNade select >> nth=0',{index:0}],['until',9.25,WB_READY,60000],
    ['js',9.3,`const c=document.getElementById('wbClusters');let d=c?.closest('details');while(d){d.open=true;d=d.parentElement?.closest('details')}c?.scrollIntoView({block:'nearest'})`],
    ['move','#wbClusters button >> nth=0',9.5,0.7],['click',10.3],['wait',10.35,400],['move',[880,560],10.8,1.4]]},wbWhy);
  add({id:'wbpro',kind:'app',dur:10,caps:[[0,'对照职业：同样的筛选条件，左边是你，右边是职业比赛'],[5,'热力图、道具、Agent 分析都能并排比较']],acts:[
    ['until',0,WB_READY,60000],
    d.proVerified?['wait',0.1,1]:['js',0.1,`const c=document.getElementById('wbDeclared');if(!c.checked){c.checked=true;c.dispatchEvent(new Event('change'))}`],
    ['move','.wb-modes button[data-mode=heat]',0.3,0.7],['click',1.1],['until',1.15,WB_READY,60000],
    ['move','#wbCompareToggle',1.7,0.7],['click',2.5],['until',2.55,WB_READY,60000],['wait',2.6,800],['move',[700,560],3.4,1.4],['move',[1250,560],5.6,1.4],
    ['move','#wbTabAgent',7.6,0.8],['click',8.5],['wait',8.55,500]]},wbWhy||(!d.pros.length?`no professional demo on ${mapName}`:d.featuredPro?'featured match is itself a pro demo (the review-level pro comparison covers this)':null));
  // ---- career page
  const careerWhy=!hasPlayers?'no player statistics yet (open a match → 比赛数据 once, or link Steam)':null;
  add({id:'chap-career',kind:'mg',scene:'chap2',dur:3.2,chap:{k:'05',en:'CAREER',title:'我的生涯',sub:'每一场比赛自动统计，进步看得见'}},careerWhy);
  add({id:'career',kind:'app',dur:13,caps:[[0,'我的生涯：Rating、ADR、KAST、首杀、多杀、道具伤害'],[5,'Rating 走势与分地图数据'],[9,'关联 Steam 后，下载的 demo 自动导入；点任意一场直接打开回放']],acts:[
    ['move','.mc-nav button[data-view=profile]',0.2,0.8],['click',1.0],['until',1.05,`document.querySelector('#profileStats .stat-tile')||document.querySelector('#playerQuick button')`,20000],
    ...(d.account.linked&&!d.featuredPro?[['wait',1.1,800]]:[['move','#playerQuick button >> nth=0',1.4,0.8],['click',2.3]]),
    ['until',2.35,`document.querySelector('#profileStats .stat-tile')`,20000],['move',[1150,420],2.8,1.2],
    ['wheel',5.0,320],['move',[1150,600],5.4,1.0],['wheel',7.2,380],['move','#trackingCard',9.0,1.0],['move',[1200,640],11.0,1.2]]},careerWhy);
  // ---- utility lab
  const labWhy=!d.labMap?'no lab map installed (data/maps/all/<map>/scene.npz)':null;
  const LP=d.labMap&&(CFG.lab.origin&&CFG.lab.target?{origin:CFG.lab.origin,target:CFG.lab.target}:LAB_POINTS[d.labMap]);
  add({id:'chap-lab',kind:'mg',scene:'chap3',dur:3.2,chap:{k:'06',en:'UTILITY LAB',title:'道具实验室',sub:'基于地图真实碰撞模型，算出你想要的道具投法'}},labWhy||(!LP?'no lab points for '+d.labMap:null));
  add({id:'lab',kind:'app',dur:19,caps:[[0,'道具实验室：选地图和投掷方式'],[3,'在地图上点站位，再点想要的落点'],[7.4,'本地物理模拟，比较站投、跳投等多种投法'],[11,'给出瞄点、难度和完整轨迹'],[15.5,'复制 setpos / setang，进游戏直接练']],acts:[
    ['goto',0,'/lab'],['until',0.05,`/就绪|ready/i.test(document.getElementById('status').textContent)`,60000],
    ['move','#map',0.3,0.6],['select',0.9,'#map',d.labMap||''],['until',0.95,`/就绪|ready/i.test(document.getElementById('status').textContent)`,60000],
    ['move','#mode',1.3,0.6],['select',1.9,'#mode',CFG.lab.mode||'auto'],
    ...(Array.isArray(LP?.origin)&&LP.origin.length===3?[
      ['move','#origin',2.4,0.6],['fill',3.0,'#origin',LP.origin.join(', ')],['move','#target',3.4,0.6],['fill',4.0,'#target',LP.target.join(', ')],['move','#apply',4.6,0.6],['click',5.3]]:[
      ['move','#pickOrigin',2.4,0.6],['click',3.0],['labUV',3.6,LP?.origin],['wait',3.65,500],['labUV',4.8,LP?.target],['wait',4.85,500]]),
    ['move','#solve',6.0,0.8],['click',6.9],['until',6.95,`!document.getElementById('cancel').disabled||document.getElementById('candidate').options.length>1`,10000],['wait',7.0,400],['move',[1100,560],7.4,1.0],
    ['until',9.0,`document.getElementById('cancel').disabled`,120000],
    ['move','#candidate',9.4,0.8],['move','#timeline',11.0,0.8],['drag2',11.8,'#timeline',0.05,1.0,2.4],
    ['move','#aim',14.4,0.6],['click',15.1],['wait',15.15,600],['move','#copy',16.0,0.8],['click',16.9]]},labWhy||(!LP?'no lab points for '+d.labMap:null));
  add({id:'models',kind:'app',dur:9,caps:[[0,'模型自选：主流大模型，或完全本地运行'],[4.6,'选手名字永远不会发给模型']],acts:[
    ['move','.llm-btn',0.3,0.9],['click',1.3],['wait',1.35,900],
    ['move','.llm-tabs button:nth-child(2)',1.8,0.7],['click',2.6],['wait',2.65,500],
    ['move','.llm-panel:not([hidden]) .llm-providers button[data-id=local]',3.0,0.7],['click',3.8],['wait',3.85,300],
    ['move','#embLocal',4.3,0.7],['select',5.2,'#embLocal',{index:1}],['move',[1100,560],6.0,1.2],
    ['js',8.9,`document.querySelector('dialog[open]')?.close()`]]});
  add({id:'outro',kind:'mg',scene:'s11',dur:7});
  return S;
}
// Tick the featured match, then others, while the total stays at or under ~100 rounds (unticked = all matches).
const LIMIT_JS=name=>`const ls=[...document.querySelectorAll('#wbMatches label')].map(l=>({c:l.querySelector('input'),n:+((l.textContent.match(/(\\d+) 回合/)||[])[1]||0),f:l.textContent.includes(${JSON.stringify(name.replace(/\.dem$/,''))})}));
if(ls.reduce((a,x)=>a+x.n,0)>110){ls.sort((a,b)=>b.f-a.f||a.n-b.n);let s=0;for(const x of ls){if(s>0&&s+x.n>100)continue;s+=x.n;if(!x.c.checked){x.c.checked=true;x.c.dispatchEvent(new Event('change'))}}}`;
// Workbench is "ready" when no load is running and the status line isn't a progress message.
const WB_READY=`document.getElementById('wbCancelLoad').hidden&&!/…|\\.\\.\\.|已加载 \\d+\\/\\d+/.test(document.getElementById('wbLoad')?.textContent||'')`;

// ---------------------------------------------------------------- overlay (cursor, click ripple, captions) inside the app page
const CURSOR=`<svg width="34" height="34" viewBox="0 0 34 34"><path d="M4 2 L4 27 L11 20 L16 31 L21 29 L16 18 L26 18 Z" fill="#fff" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>`;
async function injectOverlay(p){
  await p.evaluate(svg=>{
    if(document.getElementById('vo-cur'))return;
    const l=document.createElement('link');l.rel='stylesheet';l.href='https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@500;700&family=Space+Mono:wght@700&display=block';document.head.append(l);
    const F='"Noto Sans SC","Microsoft YaHei","PingFang SC","WenQuanYi Zen Hei",sans-serif';
    const st=document.createElement('style');st.textContent=`
.vo[popover]{margin:0;border:0;padding:0;background:transparent;overflow:visible;inset:auto;color:inherit;position:fixed;pointer-events:none}
#vo-cur{left:0;top:0;z-index:2147483647;transform:translate(-4px,-2px);filter:drop-shadow(0 2px 4px #000a)}
#vo-rip{z-index:2147483646;width:46px;height:46px;margin:-23px 0 0 -23px!important;border:3px solid #fc3d21!important;border-radius:50%;opacity:0}
#vo-sub{left:0;right:0;bottom:150px;width:100%;display:flex;justify-content:center;z-index:2147483640}
#vo-sub span{font:500 46px/1.35 ${F};color:#fff;background:#000000c8;padding:10px 30px;border-left:4px solid #fc3d21;max-width:1700px;text-align:center}
#vo-tag{right:40px;bottom:16px;z-index:2147483640;font:700 18px "Space Mono",monospace;letter-spacing:.18em;color:#82d68f;border:1px solid #82d68f80!important;padding:6px 14px!important;background:#08090bdd!important}
#vo-prog{left:0;bottom:0;height:5px;background:#fc3d21!important;z-index:2147483641}
#vo-fade{inset:0;width:100%;height:100%;background:#000!important;opacity:0;z-index:2147483645}`;
    document.head.append(st);
    // Popovers live in the browser's top layer, so they stay above modal <dialog>s.
    for(const [id,html] of [['vo-prog',''],['vo-tag','● 实机演示 · REAL APP'],['vo-sub','<span></span>'],['vo-rip',''],['vo-cur',svg],['vo-fade','']]){const d=document.createElement('div');d.id=id;d.className='vo';d.popover='manual';d.innerHTML=html;document.body.append(d);d.showPopover()}
    window.__voRaise=()=>{for(const id of ['vo-prog','vo-tag','vo-sub','vo-rip','vo-cur','vo-fade']){const d=document.getElementById(id);d.hidePopover();d.showPopover()}};
  },CURSOR);
}
async function setOverlay(p,o){await p.evaluate(o=>{const $=id=>document.getElementById(id);
  const dlg=!!document.querySelector('dialog[open]');if(dlg!==window.__voDlg){window.__voDlg=dlg;window.__voRaise()}
  $('vo-cur').style.left=o.x+'px';$('vo-cur').style.top=o.y+'px';
  const r=$('vo-rip');r.style.left=o.x+'px';r.style.top=o.y+'px';r.style.opacity=o.rip;r.style.transform=`scale(${1+1.4*(1-o.rip)})`;
  const s=$('vo-sub');s.style.display=o.caption?'flex':'none';s.firstChild.textContent=o.caption||'';
  $('vo-prog').style.width=o.progress+'%';$('vo-fade').style.opacity=o.fade},o)}

// Open any collapsed <details> around a control and scroll it into view, so it can be shown and used.
async function reveal(p,sel){if(typeof sel!=='string'||/>>|text=|:has-text/.test(sel))return;
  await p.evaluate(sel=>{const e=document.querySelector(sel);if(!e)return;let d=e.closest('details');while(d){d.open=true;d=d.parentElement?.closest('details')}e.scrollIntoView({block:'nearest'})},sel).catch(()=>{})}
async function center(p,target){
  if(Array.isArray(target)&&target[0]>1)return {x:target[0],y:target[1]};
  if(Array.isArray(target))return uvToScreen(p,target);
  await reveal(p,target);const b=await p.locator(target).first().boundingBox({timeout:3000});if(!b)throw new Error('not visible: '+target);
  return {x:b.x+Math.min(b.width/2,140),y:b.y+Math.min(b.height/2,120)};
}
// Review / tactic board: radar UV → screen through the SVG's own transform.
function uvToScreen(p,[u,v]){return p.evaluate(([u,v])=>{const s=document.getElementById('map');const pt=s.createSVGPoint();pt.x=u*1024;pt.y=v*1024;const q=pt.matrixTransform(s.getScreenCTM());return {x:q.x,y:q.y}},[u,v])}
// Utility lab 2D view: same fit as free-lab.js fit2() (content bounds + 4% margin, centred in the canvas).
function labUvToScreen(p,[u,v]){return p.evaluate(async([u,v])=>{const meta=await (await fetch('/api/lab/radar/'+document.getElementById('map').value)).json();
  const c=document.querySelector('canvas.lab2d'),r=c.getBoundingClientRect();const [l,tp,rr,bb]=meta.content_bounds.map(x=>x*1024);const size=Math.max(rr-l,bb-tp)*1.04;
  const v0=[(l+rr-size)/2,(tp+bb-size)/2],s=Math.min(r.width,r.height)/size,ox=(r.width-size*s)/2-v0[0]*s,oy=(r.height-size*s)/2-v0[1]*s;
  return {x:r.left+ox+u*1024*s,y:r.top+oy+v*1024*s}},[u,v])}
const ease=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;
const until=async(p,expr,ms)=>{const t0=Date.now();await p.clock.runFor(300);await p.waitForTimeout(100);while(Date.now()-t0<ms){if(await p.evaluate(expr).catch(()=>false))return true;await p.clock.runFor(200);await p.waitForTimeout(120)}return false};

// ---------------------------------------------------------------- main
(async()=>{
  const d=await discover();
  log(`match: ${d.match.name} (${d.match.map}, ${d.match.identity.kind}) · round ${d.round} ${d.side} · pro demos on this map: ${d.pros.length} · lab map: ${d.labMap||'—'}`);
  let SHOTS=buildShots(d);
  for(const s of SHOTS)if(s.why||s.dur===0)log(`skip ${s.id}: ${s.why||'n/a'}`);
  SHOTS=SHOTS.filter(s=>!s.why&&s.dur>0&&!skipped(s.id));
  if(flag('list')){for(const s of SHOTS)console.log(s.id.padEnd(12),s.kind,s.dur+'s',(s.caps||[]).map(c=>c[1]).join(' / '));return}
  const TOTAL=SHOTS.reduce((a,s)=>a+s.dur,0);log(`${SHOTS.length} shots, ${TOTAL.toFixed(1)} s`);
  fs.mkdirSync(OUTDIR,{recursive:true});const PREV=path.join(OUTDIR,'preview');if(PREVIEW)fs.mkdirSync(PREV,{recursive:true});
  const pairs=await aliases(d);if(pairs.length)log(`anonymising ${pairs.length} player names (anonymize: ${CFG.anonymize})`);if(flag('debug'))log(pairs.map(p=>p.join('→')).join(', '));

  const b=await chromium.launch(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{});
  const ctx=await b.newContext({viewport:{width:W,height:H},deviceScaleFactor:1});
  await ctx.addInitScript(()=>{try{localStorage.setItem('cs2-lang','zh');localStorage.removeItem('cs2-workbench-v2')}catch{}});
  await ctx.addInitScript(privacyInit,{pairs,all:CFG.anonymize==='all'});
  const app=await ctx.newPage();await app.clock.install({time:new Date('2026-10-14T12:00:00')});
  const settle=async n=>{for(let i=0;i<n;i++)await app.clock.runFor(DT);await app.waitForTimeout(800);for(let i=0;i<20;i++)await app.clock.runFor(DT)};
  await app.goto(CFG.app+'/demos?view=matches');await settle(40);await injectOverlay(app);await app.waitForTimeout(800);
  const mg=await b.newPage({viewport:{width:W,height:H}});await mg.goto('file://'+path.join(HERE,'scenes.html').replace(/\\/g,'/'));await mg.evaluate(()=>document.fonts.ready);
  let st=0;const mgScenes=[];for(const s of SHOTS)if(s.kind==='mg'){mgScenes.push({id:s.scene,start:st,dur:s.dur,subs:[],...(s.chap||{})});s.mgStart=st;st+=s.dur+1}
  await mg.evaluate(tl=>setup(tl),{duration:st,scenes:mgScenes});await mg.waitForTimeout(500);

  const silent=PREVIEW?null:OUT.replace(/\.mp4$/,'')+'.silent.mp4';
  const ffmpeg=require('ffmpeg-static');
  const ff=PREVIEW?null:spawn(ffmpeg,['-y','-loglevel','error','-f','image2pipe','-framerate',String(FPS),'-c:v','mjpeg','-i','-','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',String(FPS),'-movflags','+faststart',silent],{stdio:['pipe','inherit','inherit']});
  const put=async buf=>{if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r))};
  let cur={x:960,y:620},rip=0,shotStart=0;const t0=Date.now(),srt=[],cuts=[];
  for(const [si,shot] of SHOTS.entries()){
    const N=Math.round(shot.dur*FPS);const acts=(shot.acts||[]).map(a=>({a,done:false}));let move=null,drag=null;
    log(`shot ${si+1}/${SHOTS.length} ${shot.id}`);cuts.push(shotStart);
    for(const c of shot.caps||[]){const nx=(shot.caps.find(x=>x[0]>c[0])||[shot.dur])[0];srt.push([shotStart+c[0],shotStart+nx,c[1]])}
    for(let i=0;i<N;i++){
      const t=i/FPS,g=shotStart+t;
      const cap=(shot.caps||[]).filter(c=>t>=c[0]).at(-1);const caption=cap?cap[1]:'';
      const fade=Math.min(1,Math.max(0,1-t/0.25,1-(shot.dur-t)/0.25));
      if(shot.kind==='mg'){
        await mg.evaluate(([tt,o])=>{render(tt);overlay(o)},[shot.mgStart+t,{caption,progress:100*g/TOTAL,tc:String(Math.floor(g/60)).padStart(2,'0')+':'+(g%60).toFixed(2).padStart(5,'0'),sc:String(si+1).padStart(2,'0')+' / '+String(SHOTS.length).padStart(2,'0'),fade,tag:!['s01','s11'].includes(shot.scene)&&!shot.chap}]);
        if(PREVIEW){if(i===Math.floor(N*0.7))fs.writeFileSync(path.join(PREV,`${String(si+1).padStart(2,'0')}_${shot.id}.jpg`),await mg.screenshot({type:'jpeg',quality:85}))}
        else await put(await mg.screenshot({type:'jpeg',quality:94}));
      }else{
        for(const it of acts){
          const a=it.a,at=a[0]==='move'?a[2]:a[1];if(it.done||t<at)continue;it.done=true;
          try{
            switch(a[0]){
              case 'move':{const to=await center(app,a[1]);move={from:{...cur},to,t0:t,d:a[3]};break}
              case 'click':rip=1;await app.mouse.click(cur.x,cur.y);await app.waitForTimeout(250);break;
              case 'clickUV':{const q=await uvToScreen(app,a[2]);move={from:{...cur},to:q,t0:t,d:0.25};cur=q;rip=1;await app.mouse.click(q.x,q.y);await app.waitForTimeout(150);break}
              case 'labUV':{if(!a[2])break;const q=await labUvToScreen(app,a[2]);move={from:{...cur},to:q,t0:t,d:0.5};cur=q;rip=1;await app.mouse.click(q.x,q.y);await app.waitForTimeout(250);break}
              case 'select':{rip=1;await reveal(app,a[2]);const h=await app.locator(a[2]).first().elementHandle({timeout:3000});
                // Set the value in the page (no focus, so no native picker is ever drawn), then fire the events the app listens to.
                const ok=await h.evaluate((e,v)=>{const i=typeof v==='object'?v.index:[...e.options].findIndex(o=>o.value===v&&!o.disabled);if(i<0||i>=e.options.length||e.options[i].disabled)return false;e.selectedIndex=i;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true},a[3]);
                if(!ok)throw new Error('option not available: '+JSON.stringify(a[3]));await app.waitForTimeout(300);break}
              case 'fill':rip=1;await reveal(app,a[2]);await app.fill(a[2],a[3],{timeout:3000});await app.dispatchEvent(a[2],'change');await app.waitForTimeout(300);break;
              case 'wait':await app.waitForTimeout(a[2]);break;
              case 'js':await app.evaluate(a[2]);await app.waitForTimeout(200);break;
              case 'until':if(!await until(app,a[2],a[3]))log(`  (still waiting after ${a[3]/1000}s: ${shot.id})`);break;
              case 'wheel':await app.mouse.move(cur.x,cur.y);await app.mouse.wheel(0,a[2]);break;
              case 'drag':{const p0=await uvToScreen(app,a[2]),p1=await uvToScreen(app,a[3]);cur=p0;await app.mouse.move(p0.x,p0.y);await app.mouse.down();drag={p0,p1,t0:t,d:a[4]};break}
              case 'drag2':{const bb=await app.locator(a[2]).boundingBox();const p0={x:bb.x+bb.width*a[3],y:bb.y+bb.height/2},p1={x:bb.x+bb.width*a[4],y:bb.y+bb.height/2};cur=p0;await app.mouse.move(p0.x,p0.y);await app.mouse.down();drag={p0,p1,t0:t,d:a[5]};break}
              case 'goto':await app.goto(CFG.app+a[2]);await settle(30);await injectOverlay(app);break;
            }
          }catch(e){log(`  action failed in ${shot.id}: ${a[0]} ${[a[1],a[2]].find(x=>typeof x==='string')||''} — ${e.message.split('\n')[0]}`)}
        }
        if(move){const k=Math.min(1,(t-move.t0)/move.d),e=ease(k);cur={x:move.from.x+(move.to.x-move.from.x)*e,y:move.from.y+(move.to.y-move.from.y)*e};if(k>=1)move=null;await app.mouse.move(cur.x,cur.y)}
        if(drag){const k=Math.min(1,(t-drag.t0)/drag.d),e=ease(k);cur={x:drag.p0.x+(drag.p1.x-drag.p0.x)*e,y:drag.p0.y+(drag.p1.y-drag.p0.y)*e};await app.mouse.move(cur.x,cur.y);if(k>=1){await app.mouse.up();drag=null}}
        await app.clock.runFor(DT);
        await setOverlay(app,{x:cur.x,y:cur.y,rip,caption,progress:100*g/TOTAL,fade});rip=Math.max(0,rip-0.12);
        if(PREVIEW){if(i%45===0||i===N-12)fs.writeFileSync(path.join(PREV,`${String(si+1).padStart(2,'0')}_${shot.id}_${String(i).padStart(3,'0')}.jpg`),await app.screenshot({type:'jpeg',quality:80}))}
        else await put(await app.screenshot({type:'jpeg',quality:94}));
      }
    }
    shotStart+=shot.dur;
  }
  await b.close();
  if(PREVIEW){log('preview stills in',PREV);return}
  ff.stdin.end();await new Promise(r=>ff.on('close',r));

  // captions as .srt (handy for YouTube CC), then music + mux
  const ts=x=>{const ms=Math.round(x*1000);return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(n=>String(n).padStart(2,'0')).join(':')+','+String(ms%1000).padStart(3,'0')};
  fs.writeFileSync(OUT.replace(/\.mp4$/,'.srt'),srt.map((s,i)=>`${i+1}\n${ts(s[0])} --> ${ts(s[1]-0.05)}\n${s[2]}\n`).join('\n'),'utf8');
  // YouTube chapters (paste into the description). YouTube needs 00:00 first and chapters of 10 s or more.
  const CH={title:'开场 · 导入与 2D 回放',agent:'AI 分析师',procompare:'职业对照',board:'战术板','chap-multi':'多回合分析：热力图 · 道具 · 筛选','chap-career':'我的生涯','chap-lab':'道具实验室',models:'模型设置与结尾'};
  const mmss=x=>String(Math.floor(x/60)).padStart(2,'0')+':'+String(Math.floor(x%60)).padStart(2,'0');
  let chapters=[],acc=0;for(const s of SHOTS){if(CH[s.id])chapters.push([acc,CH[s.id]]);acc+=s.dur}
  chapters=chapters.filter((c,i)=>i===0||c[0]-chapters[i-1][0]>=10);if(chapters.length>1&&TOTAL-chapters.at(-1)[0]<10)chapters.pop();if(chapters.length)chapters[0][0]=0;
  fs.writeFileSync(OUT.replace(/\.mp4$/,'')+'.chapters.txt',chapters.map(c=>mmss(c[0])+' '+c[1]).join('\n')+'\n','utf8');
  const wav=OUT.replace(/\.mp4$/,'')+'.music.wav';
  const py=/[\\/]/.test(CFG.python)?path.resolve(HERE,CFG.python):CFG.python;
  const mus=spawnSync(py,[path.join(HERE,'music.py'),TOTAL.toFixed(3),cuts.slice(1).map(c=>c.toFixed(2)).join(','),wav],{stdio:'inherit'});
  if(mus.status!==0||!fs.existsSync(wav)){fs.renameSync(silent,OUT);log(`music failed (run inside the app's Python environment so numpy is available, or set "python" in video.config.json) — wrote a silent video: ${OUT}`);return}
  const mux=spawnSync(ffmpeg,['-y','-loglevel','error','-i',silent,'-i',wav,'-map','0:v','-map','1:a','-c:v','copy','-af','loudnorm=I=-14:TP=-1.5:LRA=11','-ar','48000','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',OUT],{stdio:'inherit'});
  if(mux.status!==0)throw new Error('ffmpeg mux failed');
  fs.rmSync(silent);fs.rmSync(wav);
  log(`done: ${OUT} (${TOTAL.toFixed(1)} s, recorded in ${Math.round((Date.now()-t0)/1000)} s)`);
})().catch(e=>{console.error('[video] '+e.message);process.exit(1)});
