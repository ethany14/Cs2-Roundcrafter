const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
let engine=new ReplayEngine(document.getElementById('replayCanvas')),replayData=null,showAllClaims=false,playerNames={};
// Real in-game names for display only. Internal IDs (P1…) stay the key everywhere and in every model payload.
function nm(id){return id&&playerNames[id]||id}
function withNames(s){return typeof s==='string'?s.replace(/(?<![A-Za-z0-9])P\d{1,2}(?![0-9])/g,m=>playerNames[m]||m):s}
window.playerNameOf=nm;
let token,match,data,round,radar,seconds=0,playing=false,job,xhr,board=null,stage=0,history=[],saved=[],view=[0,0,1024,1024],drag=null,loadVersion=0,clip=null,coachVersion=0;
const labels={smokegrenade_detonate:t('烟雾生效'),flashbang_detonate:t('闪光引爆'),hegrenade_detonate:t('手雷引爆'),inferno_startburn:t('燃烧开始'),player_death:t('击杀'),bomb_planted:t('下包'),bomb_defused:t('拆包'),bomb_exploded:t('爆炸')};
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(t(d.error)||t('请求失败'));return d}
function status(tv){$('status').textContent=tv}function safe(fn){return async(...a)=>{try{await fn(...a)}catch(e){status(e.message)}}}
function button(text,fn){const b=document.createElement('button');b.textContent=text;b.onclick=safe(fn);return b}
function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p)}
const statusNames={completed:t('已完成'),failed:t('失败'),cancelled:t('已取消'),interrupted:t('已中断'),parsing:t('解析中'),uploading:t('上传中'),analyzing:t('整理中')};
function matchCard(x,identity){const b=document.createElement('button');b.className='match-card';const name=document.createElement('b');name.textContent=x.name.replace(/\.dem$/,'');const meta=document.createElement('span');meta.className='meta';
 const kind=identity?.kind||'unknown',tags=[[({player:t('普通玩家'),professional:identity?.verified?t('职业 · 来源已核对'):t('职业 · 上传者声明'),unknown:t('未分类')}[kind]),kind==='professional'?'cyan':kind==='player'?'green':''],[x.map?x.map.replace('de_','').toUpperCase():'—',''],[x.rounds?x.rounds+t(' 回合'):'—',''],[statusNames[x.status]||x.status,x.status==='completed'?'':x.status==='failed'?'red':'amber']];
 for(const [text,cls] of tags){const s=document.createElement('span');s.className='mc-tag '+cls;s.textContent=text;meta.append(s)}b.append(name,meta);b.onclick=safe(()=>x.status==='completed'?open(x.id):watch(x.id));return b}
async function library(){const d=await api('/api/demos');const identities=await api('/api/demo/identities');const kinds=Object.fromEntries(identities.matches.map(m=>[m.id,m.identity]));$('samples').replaceChildren(...d.samples.map(x=>new Option(x.name,x.name)));$('library').replaceChildren(...d.matches.map(x=>matchCard(x,kinds[x.id])))}
async function watch(id){job=id;$('cancel').hidden=false;for(;;){const s=await api('/api/demo/job?id='+id);status(s.stage);if(!['uploading','parsing','analyzing'].includes(s.status)){job=null;$('cancel').hidden=true;await library();if(s.status==='completed')await open(id);break}await new Promise(r=>setTimeout(r,800))}}
$('sample').onclick=safe(async()=>{const d=await api('/api/demo/start',{sample:$('samples').value});await watch(d.id)});
$('file').onchange=safe(async()=>{const f=$('file').files[0];if(!f)return;if(f.size>1073741824)throw Error(t('文件超过 1 GiB'));const kind=$('uploadKind').value,source=$('uploadSource').value.trim();if(kind==='professional'&&!/^https?:\/\//.test(source))throw Error(t('职业 demo 请先填写来源链接'));status(t('正在上传'));$('cancel').hidden=false;const d=await new Promise((resolve,reject)=>{xhr=new XMLHttpRequest();xhr.open('POST','/api/demo/upload');xhr.setRequestHeader('X-Local-Token',token);xhr.setRequestHeader('X-Demo-Name',encodeURIComponent(f.name));xhr.setRequestHeader('X-Demo-Kind',kind);xhr.setRequestHeader('X-Demo-Source',encodeURIComponent(source));xhr.upload.onprogress=e=>status(t('上传 ')+Math.round(e.loaded/f.size*100)+'%');xhr.onload=()=>{try{const d=JSON.parse(xhr.responseText);xhr.status<300?resolve(d):reject(Error(t(d.error)))}catch(e){reject(e)}};xhr.onerror=()=>reject(Error(t('上传连接失败')));xhr.onabort=()=>reject(Error(t('已取消上传')));xhr.send(f)}).finally(()=>{xhr=null;$('cancel').hidden=true});await watch(d.id)});
$('cancel').onclick=safe(async()=>{if(xhr)xhr.abort();if(job)await api('/api/demo/cancel',{id:job})});
async function open(id,selectedRound){if(window.showView)window.showView('review');playing=false;board=null;match=id;data=await api('/api/demo/result?id='+id);playerNames=(await api('/api/demo/players?id='+id).catch(()=>({names:{}}))).names||{};engine.names=playerNames;const requestedRound=selectedRound||Number(new URLSearchParams(location.search).get('round'))||data.rounds[0].number;historyReplace();$('title').textContent=data.map+t(' · 比赛战术');$('meta').textContent=data.rounds.length+t(' 回合 / ')+data.tactics.length+t(' 个候选');$('limits').textContent=data.limitations.map(x=>t(x)).join(t('；'));$('candidates').replaceChildren(...data.tactics.map(c=>new Option('R'+c.round+' · '+c.side+' · '+I18N.gloss(c.title),c.id))); $('round').replaceChildren(...data.rounds.map(r=>new Option(t('第 ')+r.number+t(' 回合 · ')+r.winner+t(' 胜'),r.number)));try{radar=await api('/api/lab/radar/'+data.map);engine.setRadar(radar);fitMap()}catch{radar=null;engine.setRadar(null);status(t('此地图没有本地雷达图，保留事件和战术证据'))}await loadRound(requestedRound);await loadBoards();await loadMatchAnalysis(true)}
function historyReplace(){window.history.replaceState(null,'','/demos?match='+match)}
async function loadRound(n){const version=++loadVersion;playing=false;if(window.resetComparison)window.resetComparison();const [r,rp]=await Promise.all([api('/api/demo/round?id='+match+'&round='+n),api('/api/demo/replay?id='+match+'&round='+n).catch(()=>null)]);if(version!==loadVersion)return;round=r;replayData=rp;engine.setRound(r,rp);engine.selected=null;$('replaySource').textContent=rp?t('16 Hz 插值回放 · 真实道具轨迹'):t('4 Hz 观测帧 · 生成补充解析后可得 16 Hz');board=null;clip=null;seconds=0;$('round').value=n;window.history.replaceState(null,'','/demos?match='+match+'&round='+n);$('timeline').max=r.duration;$('editing').hidden=true;renderTactic();renderRounds();renderEventTicks();loadCoach();$('events').replaceChildren(...r.events.filter(e=>labels[e.type]).map(e=>button(e.seconds.toFixed(2)+'s · '+labels[e.type]+' · '+(nm(e.actor)||t('未知')),()=>{seconds=e.seconds;board=null;$('editing').hidden=true;render()})));render()}
function card(){return data?.tactics.find(c=>c.round===round.number&&c.side===$('side').value)}
function renderTactic(){const c=card();$('details').replaceChildren();if(!c)return;$('tactic').textContent=I18N.gloss(c.title);$('candidates').value=c.id;paragraph($('details'),t('观察事实'));c.facts.forEach(f=>$('details').append(button(withNames(I18N.gloss(f.text)),()=>{seconds=(f.tick-round.start_tick)/data.tick_rate;render()})));paragraph($('details'),t('规则推断：')+(c.inferences.map(I18N.gloss).join(' ')||t('仅展示开局防守分布，不推断预设战术。')));paragraph($('details'),t('未知：')+c.unknown.map(I18N.gloss).join(t('；')));c.roles.forEach(r=>paragraph($('details'),nm(r.player)+t(' · 装备 ')+r.opening_inventory.join(', ')+t(' · 路线 ')+r.route.map(x=>x.seconds.toFixed(1)+'s '+x.area).join(' → ')));const ownEvents=round.events.filter(e=>c.event_ids.includes(e.id));ownEvents.forEach(e=>$('details').append(button((nm(e.actor)||t('未知玩家'))+' · '+e.seconds.toFixed(2)+'s '+(labels[e.type]||e.type),()=>{seconds=e.seconds;render()})));phases()}
function frame(){if(!round?.frames?.length)return {players:[]};return round.frames.reduce((a,b)=>Math.abs(a.seconds-seconds)<Math.abs(b.seconds-seconds)?a:b)}
function xy(p){return [(p[0]-radar.pos_x)/radar.scale,(radar.pos_y-p[1])/radar.scale]}
function world(p,z){return [p[0]*radar.scale+radar.pos_x,radar.pos_y-p[1]*radar.scale,z]}
function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));parent.append(e);return e}
function onFloor(p){return !radar?.lower_url||($('floor').value==='lower'?p[2]<radar.floor_split_z:p[2]>=radar.floor_split_z)}
function render(){if(!round&&!board)return;const replayMode=!board;$('replayCanvas').hidden=!replayMode;$('radar').style.display=replayMode?'none':'';$('map').classList.toggle('overlay',replayMode);
 if(replayMode){$('markers').replaceChildren();$('ink').replaceChildren();if(radar){$('floor').disabled=!radar.lower_url;if(clip&&radar.lower_url){const tracked=engine.state(seconds).filter(p=>clip.players?.includes(p.id)&&p.alive);if(tracked.length)$('floor').value=tracked.filter(p=>p.z<radar.floor_split_z).length>tracked.length/2?'lower':'upper'}}$('map').setAttribute('viewBox',view.join(' '));dirty=true;updateUi(true);return}
 $('time').textContent=t('战术板编辑中');$('replayCanvas').hidden=true;engine.ctx.clearRect(0,0,engine.c.width,engine.c.height);if(radar)$('radar').setAttribute('href',$('floor').value==='lower'&&radar.lower_url?radar.lower_url:radar.upper_url);TacticBoard.render()}
function phases(){$('phases').replaceChildren();if(board)return;const ticks=board?board.map(s=>s.source_tick):card()?.phase_ticks||[];ticks.forEach((tv,i)=>$('phases').append(button((board?t('方案 '):t('阶段 '))+(i+1),()=>{if(board){stage=i;$('note').value=board[i].note||''}else seconds=(tv-round.start_tick)/data.tick_rate;render()})))}
$('candidates').onchange=safe(async()=>{const c=data.tactics.find(x=>x.id===$('candidates').value);$('side').value=c.side;await loadRound(c.round);seconds=c.focus_seconds;render()});
$('round').onchange=safe(()=>loadRound(+$('round').value));$('side').onchange=()=>{renderTactic();if(window.resetComparison)window.resetComparison();if(!$('comparePanel').hidden)findComparison().catch(compareError)};for(const [id,delta] of [['prev',-1],['next',1]])$(id).onclick=safe(()=>{if(round){const n=round.number+delta;if(data.rounds.some(r=>r.number===n))return loadRound(n)}});
$('timeline').oninput=()=>{if(round&&!board){clip=null;seconds=+$('timeline').value;dirty=true;updateUi(true)}};$('play').onclick=()=>{if(round&&!board){if(clip&&seconds>=clip.end)seconds=clip.start;else if(seconds>=round.duration)seconds=0;playing=!playing;render()}};$('floor').onchange=()=>{dirty=true;render()};$('reset').onclick=()=>{fitMap();render()};
// Display-rate loop: positions are interpolated by the engine, the DOM (HUD, scoreboard, killfeed) refreshes ~8 Hz.
let lastFrame=performance.now(),dirty=true,lastUi=0;
function loop(now){const dt=Math.min(.1,(now-lastFrame)/1000);lastFrame=now;
 if(round&&!board){if(playing){seconds=Math.min(round.duration,seconds+dt*+$('speed').value);const stop=Math.min(round.duration,clip?.end??round.duration);if(seconds>=stop){seconds=stop;playing=false}dirty=true}
  if(dirty){engine.view=view;engine.floor=$('floor').value;engine.clip=clip;engine.trail=+$('trailLen').value;engine.draw(seconds);dirty=false;updateUi(false)}}
 requestAnimationFrame(loop)}
requestAnimationFrame(loop);
new ResizeObserver(()=>{dirty=true}).observe($('replayCanvas'));
$('trailLen').onchange=()=>{dirty=true};
function fmtClock(s){s=Math.max(0,Math.ceil(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
function updateUi(force){const now=performance.now();if(!force&&now-lastUi<120)return;lastUi=now;if(!round)return;
 $('play').textContent=playing?t('暂停'):t('播放');$('timeline').value=seconds;$('time').textContent=seconds.toFixed(1)+'s / '+round.duration.toFixed(1)+'s'+(clip?t(' · 证据片段播放'):'');
 const st=engine.state(seconds);$('hudT').textContent=st.filter(p=>p.side==='T'&&p.alive).length;$('hudCT').textContent=st.filter(p=>p.side==='CT'&&p.alive).length;
 const d=engine.data,pl=d?.plant;if(pl&&seconds>=pl.t){const over=(d.defuse&&seconds>=d.defuse.t)||(d.boom&&seconds>=d.boom.t);$('hudClock').textContent=over?'—':fmtClock(40-(seconds-pl.t));$('hudPhase').textContent=d.defuse&&seconds>=d.defuse.t?t('已拆除'):d.boom&&seconds>=d.boom.t?t('已爆炸'):t('C4 计时');$('hudClock').classList.add('bomb')}
 else{$('hudClock').textContent=fmtClock(115-seconds);$('hudPhase').textContent=t('回合时间');$('hudClock').classList.remove('bomb')}
 const tm=replayData?.teams||{},ended=seconds>=round.duration-.25,win=replayData?.winner;
 for(const side of ['T','CT']){const tt=tm[side];$('hud'+side+'Name').textContent=tt?.name||side;const sc=tt?.score;$('hud'+side+'Score').textContent=sc==null?'–':sc+(ended&&win===side?1:0)}
 renderKillfeed();if(!$('roster').hidden)renderScoreboard(st)}
async function loadBoards(){const map=data?.map||radar?.map;if(!map)return;const r=await api('/api/room/tactics?map='+map).catch(()=>({tactics:[]}));$('boards').replaceChildren(new Option(t('加载战术室中的方案'),''),...r.tactics.map(b=>new Option(b.name+' · '+b.stages+t(' 阶段'),b.id)))}
window.loadBoards=loadBoards;
function point(e){const p=$('map').createSVGPoint();p.x=e.clientX;p.y=e.clientY;const v=p.matrixTransform($('map').getScreenCTM().inverse());return [v.x,v.y]}
$('map').onpointerdown=e=>{if(!radar)return;if(board){TacticBoard.down(e,point(e));$('map').setPointerCapture(e.pointerId);render();return}const p=point(e),id=e.target.closest('[data-player]')?.getAttribute('data-player');if(board)checkpoint();drag={p,id,view:[...view],last:p};$('map').setPointerCapture(e.pointerId)};
$('map').onpointermove=e=>{if(board){TacticBoard.move(e,point(e));return}if(!drag)return;const p=point(e);drag.last=p;if(board&&drag.id){const player=board[stage].players.find(x=>x.id===drag.id);player.position=world(p,player.position[2]);player.area=null;render()}else if(!board){view[0]+=drag.p[0]-p[0];view[1]+=drag.p[1]-p[1];render()}};
$('map').onpointerup=e=>{if(board){TacticBoard.up(e);return}if(drag&&board&&!drag.id&&Math.hypot(drag.p[0]-drag.last[0],drag.p[1]-drag.last[1])>5)board[stage].lines.push([...drag.p,...drag.last]);
 if(drag&&!board&&Math.hypot(drag.p[0]-drag.last[0],drag.p[1]-drag.last[1])<3){const r=$('map').getBoundingClientRect(),p=engine.pick(e.clientX-r.left,e.clientY-r.top);engine.selected=p&&p.id!==engine.selected?p.id:null}
 drag=null;render()};
$('map').addEventListener('pointermove',e=>{if(drag||board||!round)return;const r=$('map').getBoundingClientRect(),p=engine.pick(e.clientX-r.left,e.clientY-r.top);const id=p?.id||null;if(id!==engine.hover){engine.hover=id;$('map').style.cursor=id?'pointer':'';dirty=true}});$('map').onpointercancel=()=>{drag=null};
$('map').addEventListener('wheel',e=>{e.preventDefault();const p=point(e),scale=e.deltaY>0?1.15:.87;const w=Math.min(1800,Math.max(200,view[2]*scale)),ratio=w/view[2];view=[p[0]-(p[0]-view[0])*ratio,p[1]-(p[1]-view[1])*ratio,w,w];render()},{passive:false});
safe(async()=>{token=(await api('/api/status')).token;await library();const id=new URLSearchParams(location.search).get('match');if(id){const caseId=new URLSearchParams(location.search).get('case');await open(id);if(caseId){const c=await api('/api/demo/case?id='+encodeURIComponent(caseId));if(c.match===match){await loadRound(c.round);playEvidence(c)}}}})();

const pilots=[[t('Nuke · R13 快速进入'),'3f9df19a017b45a6a55a988b89ccab07',13],[t('Nuke · R24 进攻过程'),'3f9df19a017b45a6a55a988b89ccab07',24],[t('Dust2 · R1 A 区进攻'),'4f35a9243f58418b983a9ea1757b4cb3',1],[t('Dust2 · R17 B 区进攻'),'4f35a9243f58418b983a9ea1757b4cb3',17]];
$('pilotLinks').replaceChildren(...pilots.map(([name,id,n])=>{const a=document.createElement('a');a.textContent=name;a.href='/demos?match='+id+'&round='+n;return a}));
function playEvidence(item){board=null;$('editing').hidden=true;clip=item;seconds=item.start;playing=true;engine.selected=item.players?.length===1?item.players[0]:engine.selected;phases();render()}
async function loadCoach(){const version=++coachVersion,mid=match,n=round.number;const box=$('coach');box.replaceChildren();const h=document.createElement('h2');h.textContent=t('这一回合怎么打');box.append(h);

let state;try{state=await api('/api/demo/coach?id='+mid+'&round='+n)}catch(e){paragraph(box,e.message);return}if(version!==coachVersion)return;
const budgetNames={input_budget:t('输入上下文预算达到上限'),time_budget:t('分析时间达到上限'),call_budget:t('模型调用次数用完')};
if(state.budget_reason)paragraph(box,budgetNames[state.budget_reason]||state.budget_reason);
paragraph(box,(state.packet.side==='both'?t('双方视角 · '):t('T 方视角 · '))+(state.status==='completed'?t('Eregion 已完成解释'):state.status==='running'?t('Eregion 正在取证与解释'):state.status==='not_analyzed'?t('本地证据已就绪，尚未调用模型'):state.status==='output_truncated'?t('模型输出被截断（思考占满输出上限）'):state.status==='invalid_output'?t('模型输出格式无效'):state.status)+t(' · 累计模型调用 ')+(state.model_calls||0)+'/'+(state.max_calls||5));
if(state.status!=='completed'&&state.status!=='running'){box.append(button(t('设置预算并分析'),()=>showMatchAnalysis()));paragraph(box,t('在整场战术栏核对发送范围与预算，支持当前回合或整场分析。'))}
if(state.status==='running'){box.append(button(t('取消分析'),async()=>{await api('/api/demo/coach/cancel',{match:mid,round:n});loadCoach()}));setTimeout(()=>{if(version===coachVersion)loadCoach()},1500)}
if(!state.result&&state.previous_result){paragraph(box,t('本次分析未完成，以下保留上次结果。'));state.result=state.previous_result}
if(state.result){if((state.lang||'zh')!==I18N.lang)paragraph(box,t('这条解读是用另一种语言生成的；在“整场分析”中重新分析本回合可得到当前语言的版本。'));const summary=document.createElement('p');summary.className='coach-summary';summary.textContent=t('Agent 推断：')+withNames(state.result.summary);box.append(summary);state.result.claims.forEach((c,i)=>{const section=document.createElement('div');section.className='coach-claim compact';const head=document.createElement('div');head.className='claim-head';const title=document.createElement('b');title.textContent=(i+1)+'. '+withNames(c.observed_title);const play=button('▶ '+c.start.toFixed(0)+'–'+c.end.toFixed(0)+'s',()=>playEvidence(c));play.className='claim-play';head.append(title,play);section.append(head);
 const more=document.createElement('details');const ms=document.createElement('summary');ms.textContent=t('详情')+(c.confidence?' · '+t('推断把握：')+({high:t('较高'),medium:t('中等'),low:t('较低')}[c.confidence]||c.confidence):'');more.append(ms);paragraph(more,withNames(c.interpretation));paragraph(more,t('涉及：')+c.players.map(nm).join(' / '));
 const facts=document.createElement('ul');for(const f of c.facts){const li=document.createElement('li');li.textContent=withNames(I18N.gloss(f));facts.append(li)}more.append(facts);more.append(button(t('对照职业回合'),()=>{if(c.side==='T'||c.side==='CT')$('side').value=c.side;renderTactic();$('compareTab').click()}));section.append(more);box.append(section)});const extra=document.createElement('details');const label=document.createElement('summary');label.textContent=t('其他解释与待核对项');extra.append(label);paragraph(extra,withNames(state.result.alternatives.join(t('；'))));box.append(extra)}
const details=document.createElement('details');details.open=!state.result;const title=document.createElement('summary');title.textContent=t('行动证据：点击播放并高亮涉及人员');details.append(title);state.packet.evidence.filter(e=>e.kind!=='route').forEach(e=>details.append(button(withNames(I18N.gloss(e.text)),()=>playEvidence(e))));box.append(details);
}

$('imports').onclick=()=>window.showView&&window.showView('matches');

const PANELS={stats:['statsTab','statsPanel'],roster:['rosterTab','roster'],coach:['analysisTab','coachPane'],match:['matchTab','matchCoach'],compare:['compareTab','comparePanel'],cases:['casesTab','casesPanel'],move:['moveTab','movePanel']};
function showPanel(name){for(const [k,[tab,pane]] of Object.entries(PANELS)){$(pane).hidden=k!==name;$(tab).setAttribute('aria-selected',String(k===name))}if(name==='roster')updateUi(true)}
window.showPanel=showPanel;
$('analysisTab').onclick=()=>showPanel('coach');
$('rosterTab').onclick=()=>showPanel('roster');
function renderRounds(){$('roundStrip').replaceChildren(...data.rounds.map(r=>{const b=button(String(r.number),()=>loadRound(r.number));b.dataset.side=r.winner;b.className=r.number===round.number?'active':'';b.title=t('第 ')+r.number+t(' 回合');return b}))}
const UTIL=[[/smoke/i,'smoke'],[/flash/i,'flash'],[/high explosive|he grenade/i,'he'],[/molotov|incendiary/i,'fire'],[/decoy/i,'decoy']];
function shortWeapon(w){if(!w)return '—';if(/knife|bayonet|karambit|butterfly|daggers|bowie|falchion|navaja|stiletto|talon|ursus|kukri/i.test(w))return t('刀');return w.replace(/^weapon_/,'').replace(' Explosive','').replace(' Grenade','')}
function renderScoreboard(st){
 const root=$('roster'),f=frame(),inv=Object.fromEntries(f.players.map(p=>[p.id,p.inventory||[]])),econ=Object.fromEntries((replayData?.economy||[]).map(x=>[x.player,x]));
 const kills={};for(const e of engine.data?.events||[]){if(e.t>seconds)break;if(e.k==='player_death'&&e.by&&e.by!==e.a)kills[e.by]=(kills[e.by]||0)+1}
 root.replaceChildren();
 for(const side of ['T','CT']){const ps=st.filter(p=>p.side===side).sort((a,b)=>(b.alive-a.alive)||a.id.localeCompare(b.id,undefined,{numeric:true}));
  const head=document.createElement('div');head.className='sb-head '+side.toLowerCase();const money=ps.reduce((a,p)=>a+(econ[p.id]?.start_balance||0),0);
  head.innerHTML='';const hn=document.createElement('b');hn.textContent=(replayData?.teams?.[side]?.name?replayData.teams[side].name+' · ':'')+(side==='T'?t('进攻方 T'):t('防守方 CT'));const ha=document.createElement('span');ha.textContent=ps.filter(p=>p.alive).length+'/'+ps.length+t(' 存活')+(money?' · $'+money.toLocaleString():'');head.append(hn,ha);root.append(head);
  for(const p of ps){const row=document.createElement('button');row.className='sb-row '+side.toLowerCase()+(p.alive?'':' dead')+(engine.selected===p.id?' sel':'');row.onclick=()=>{engine.selected=engine.selected===p.id?null:p.id;dirty=true;updateUi(true)};
   const id=document.createElement('span');id.className='sb-id';id.textContent=nm(p.id);id.title=p.id;
   const hp=document.createElement('span');hp.className='sb-hp';const fill=document.createElement('i');fill.style.width=Math.max(0,Math.min(100,p.hp))+'%';const hv=document.createElement('em');hv.textContent=p.alive?p.hp:t('阵亡');hp.append(fill,hv);
   const ar=document.createElement('span');ar.className='sb-ar';if(p.alive&&p.armor>0){ar.append(CSIcon.el(p.helmet?'armor_helmet':'kevlar','',t('护甲')));const n=document.createElement('small');n.textContent=p.armor;ar.append(n)}
   const items=p.alive?(inv[p.id]||[]):[],activeKey=CSIcon.key(p.weapon),keys=items.map(x=>CSIcon.key(x));
   const w=document.createElement('span');w.className='sb-w';
   if(p.alive){const prim=keys.find(k=>CSIcon.kind(k)==='primary'),pist=keys.find(k=>CSIcon.kind(k)==='pistol'),main=prim||pist;
    if(main){const i=CSIcon.el(main,'main'+(main===activeKey?' held':''),items[keys.indexOf(main)]);w.append(i)}
    if(prim&&pist){const i=CSIcon.el(pist,'side'+(pist===activeKey?' held':''),items[keys.indexOf(pist)]);w.append(i)}
    if(!main&&p.weapon)w.append(CSIcon.el(p.weapon,'main held'))}
   const u=document.createElement('span');u.className='sb-u';
   if(p.alive){for(const [x,k] of items.map((x,i)=>[x,keys[i]]))if(CSIcon.GRENADES.has(k))u.append(CSIcon.el(k,'g '+(k===activeKey?'active':''),x));
    if(keys.includes('c4'))u.append(CSIcon.el('c4','c4',t('携带 C4')));if(p.kit)u.append(CSIcon.el('defuser','kit',t('拆弹器')));}
   if(p.flash>.05){const fl=document.createElement('i');fl.className='u blind';fl.title=t('被闪');u.append(fl)}
   const m=document.createElement('span');m.className='sb-m';m.textContent=econ[p.id]?.start_balance!=null?'$'+econ[p.id].start_balance:'';m.title=t('冻结结束时金钱');
   const k=document.createElement('span');k.className='sb-k';k.textContent=kills[p.id]?'✕'+kills[p.id]:'';k.title=t('本回合击杀');
   row.append(id,hp,ar,w,u,m,k);root.append(row)}}
 const note=document.createElement('p');note.className='mc-note';note.textContent=replayData?.economy?t('金钱为冻结结束时的真实值；点击队员在地图上高亮。'):t('点击队员在地图上高亮。生成补充解析后显示金钱。');root.append(note)}
function renderRoster(f){const root=$('roster');root.replaceChildren();for(const side of ['T','CT']){const h=document.createElement('h3');h.className=side==='CT'?'ct':'';h.textContent=(side==='T'?t('进攻方'):t('防守方'))+' · '+f.players.filter(p=>p.side===side&&p.alive).length+t(' 人存活');root.append(h);for(const p of f.players.filter(p=>p.side===side)){const row=document.createElement('div');row.className='player-row '+(side==='CT'?'ct':'');const b=document.createElement('b');b.textContent=p.id;const hp=document.createElement('span');hp.textContent=p.alive?(p.hp??'?')+' HP':t('阵亡');b.append(hp);row.append(b);const bar=document.createElement('div');bar.className='health';const fill=document.createElement('i');fill.style.width=Math.max(0,Math.min(100,p.hp||0))+'%';bar.append(fill);row.append(bar);const note=document.createElement('small');note.textContent=(p.weapon||'—')+' · '+(p.inventory||[]).filter(x=>/grenade|flash|molotov|incendiary/i.test(x)).join(' / ');row.append(note);root.append(row)}}}

function fitMap(){if(!radar?.content_bounds){view=[0,0,1024,1024];return}const [l,tv,r,b]=radar.content_bounds.map(x=>x*1024);const size=Math.max(r-l,b-tv)*1.08;view=[(l+r-size)/2,(tv+b-size)/2,size,size]}
const TICK_CLASS={player_death:'kill',bomb_planted:'plant',bomb_defused:'defuse',bomb_exploded:'boom',smokegrenade_detonate:'smoke',flashbang_detonate:'flash',hegrenade_detonate:'he',inferno_startburn:'fire'};
function renderEventTicks(){const root=$('eventTicks');root.replaceChildren(...round.events.filter(e=>TICK_CLASS[e.type]).map(e=>{const b=document.createElement('button');b.className='tick '+TICK_CLASS[e.type];b.style.left=(e.seconds/round.duration*100)+'%';
 const side=e.type==='player_death'?(round.frames[0]?.players.find(p=>p.id===e.attacker)?.side||''):(e.side||'');if(side)b.dataset.side=side;b.title=e.seconds.toFixed(1)+'s · '+labels[e.type]+' · '+(e.type==='player_death'?nm(e.attacker||'?')+' → '+nm(e.actor||'?'):nm(e.actor||''));
 b.onclick=()=>{clip=null;seconds=Math.max(0,e.seconds-(e.type==='player_death'?2:1));playing=false;render()};return b}))}
function renderKillfeed(){const side=id=>engine.data?.players[id]?.side||'';const events=(engine.data?.events||[]).filter(e=>e.k==='player_death'&&e.t<=seconds&&e.t>seconds-7).slice(-5);
 $('killfeed').replaceChildren(...events.map(e=>{const row=document.createElement('div');const a=document.createElement('b');a.textContent=nm(e.by)||t('世界');a.className=side(e.by).toLowerCase();const w=document.createElement('span');w.className='kf-w';w.append(CSIcon.el(e.w||'world','',e.w||''));if(e.hs){const hs=document.createElement('b');hs.className='hs';hs.textContent='⊙';hs.title=t('爆头');w.append(hs)}const v=document.createElement('b');v.textContent=nm(e.a)||'?';v.className=side(e.a).toLowerCase();row.append(a,w,v);return row}))}

let matchAnalysis=null,analysisPoll=null,analysisKey='';
function showMatchAnalysis(){showPanel('match')}
$('matchTab').onclick=showMatchAnalysis;
async function loadMatchAnalysis(initial=false){
 const mid=match;if(!mid)return;clearTimeout(analysisPoll);
 const state=await api('/api/demo/analysis?id='+mid);if(mid!==match)return;matchAnalysis=state;
 if(initial){$('analysisConsent').checked=false;$('analysisBudget').value=Math.min(200,Math.max(2,state.rounds.filter(r=>r.status!=='completed'||r.version!==4).length*2));analysisKey=''}
 $('analysisScope').textContent=state.supported?t('发送到 ')+(state.destination.host||t('尚未配置的模型服务'))+t('：所选回合的匿名编号、位置路线、装备和事件。不发送原始 demo、姓名或账号。'):t('当前地图暂不支持战术解释；可继续查看本地回放。');
 const j=state.job,running=j?.status==='running';$('cancelAnalysis').hidden=!running;
 $('analyzeMatch').disabled=running||!state.supported||!state.destination.configured;$('analyzeRound').disabled=$('analyzeMatch').disabled;
 const names={running:t('分析中'),completed:t('已完成'),output_truncated:t('模型输出被截断（思考占满输出上限）'),invalid_output:t('模型输出格式无效'),completed_with_failures:t('部分回合失败'),budget_exhausted:t('预算耗尽'),cancelled:t('已取消'),interrupted:t('服务重启，任务已中断'),failed:t('任务失败')};
 $('analysisStatus').textContent=j?(names[j.status]||j.status)+t(' · 完成 ')+j.completed.length+'/'+j.rounds.length+t(' 回合 · 本批调用 ')+j.calls+'/'+j.max_calls+((j.current_rounds?.length)?t(' · 同时分析 ')+j.current_rounds.map(n=>'R'+n).join(' / '):(j.current_round?t(' · 当前 R')+j.current_round:'')): t('尚未启动整场分析');
 $('analysisRounds').replaceChildren(...state.rounds.map(r=>{const label=r.status==='completed'?t('已分析'):r.status==='running'?t('分析中'):r.has_result?t('保留旧结果'):r.status==='not_analyzed'?t('未分析'):names[r.status]||r.status;const mark=r.status==='completed'?'✓':r.status==='running'?'…':r.has_result?'↺':r.status==='not_analyzed'?'○':'!';const b=button(r.round+mark,async()=>{await loadRound(r.round);showPanel('coach')});b.title='R'+r.round+' · '+label;b.className='round-chip '+(r.status==='completed'?'ok':r.status==='not_analyzed'?'':'warn')+(r.round===round?.number?' active':'');return b}));
 const shown=state.claims.filter(c=>showAllClaims||c.round===round?.number);
 $('analysisClaims').replaceChildren(...[(()=>{const h=document.createElement('h3');h.textContent=showAllClaims?t('全部回合结论 · ')+state.claims.length:t('本回合结论 · ')+shown.length;return h})(),
  button(showAllClaims?t('只看本回合'):t('显示全部 {0} 条',[state.claims.length]),()=>{showAllClaims=!showAllClaims;loadMatchAnalysis()}),
  ...shown.map(c=>button('▶ R'+c.round+' · '+withNames(c.title)+' · '+c.start.toFixed(0)+'–'+c.end.toFixed(0)+'s'+(c.previous?t('（上次结果）'):''),async()=>{await loadRound(c.round);playEvidence(c);showPanel('coach')}))]);
 $('analysisSetup').open=!j&&!state.claims.length;
 const key=JSON.stringify(state.rounds);if(key!==analysisKey){analysisKey=key;if(round)loadCoach()}
 if(running)analysisPoll=setTimeout(()=>loadMatchAnalysis().catch(e=>{$('analysisStatus').textContent=e.message}),1800);
}
async function startMatchAnalysis(regenerate){
 if(!$('analysisConsent').checked)throw Error(t('请先勾选匿名证据发送授权'));
 const budget=Number($('analysisBudget').value);if(!Number.isInteger(budget)||budget<1||budget>200)throw Error(t('调用预算须为1至200'));
 const raw={match,request_id:crypto.randomUUID().replaceAll('-',''),consent:true,endpoint_host:matchAnalysis.destination.host,max_calls:budget,concurrency:Number($('analysisConcurrency').value),regenerate,lang:I18N.lang};
 if(regenerate)raw.rounds=[round.number];
 await api('/api/demo/analysis/start',raw);$('analysisConsent').checked=false;await loadMatchAnalysis();
}
for(const [id,regen] of [['analyzeMatch',false],['analyzeRound',true]])$(id).onclick=async()=>{try{await startMatchAnalysis(regen)}catch(e){$('analysisStatus').textContent=e.message}};
$('cancelAnalysis').onclick=async()=>{try{await api('/api/demo/analysis/cancel',{match});await loadMatchAnalysis()}catch(e){$('analysisStatus').textContent=e.message}};

$('casesTab').onclick=()=>{showPanel('cases');searchCases()};
let caseSearchVersion=0;
async function searchCases(){const version=++caseSearchVersion;try{const s=await api('/api/demo/cases?q='+encodeURIComponent($('caseQuery').value)+'&map='+$('caseMap').value+'&side='+$('caseSide').value);if(version!==caseSearchVersion)return;$('caseStatus').textContent=s.total+t(' 条匹配 · 显示 ')+s.cases.length+t(' 条 · 本地检索，不调用模型');$('caseResults').replaceChildren();for(const c of s.cases){const card=document.createElement('div');card.className='coach-claim';const h=document.createElement('h3');h.textContent=c.title;card.append(h);paragraph(card,c.map.replace('de_','')+' · R'+c.round+' · '+c.side+t(' · 模型推断 · ')+c.evidence_count+t(' 条依据'));paragraph(card,c.interpretation);card.append(button(t('▶ 播放 ')+c.start.toFixed(1)+'–'+c.end.toFixed(1)+t(' 秒'),async()=>{if(match!==c.match)await open(c.match,c.round);else await loadRound(c.round);playEvidence(c);$('analysisTab').click()}));$('caseResults').append(card)}}catch(e){$('caseStatus').textContent=e.message}}
$('caseSearch').onclick=searchCases;$('caseQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();searchCases()}};
async function learnCase(id){try{const s=await api('/api/demo/case/learning?id='+id);const root=$('caseLearning');root.replaceChildren();const title=document.createElement('h2');title.textContent=t('学习清单 · ')+s.case.title;root.append(title);const whole=document.createElement('a');whole.href='/demos?view=research&case='+id+'&whole=1';whole.textContent=t('自动补齐整套教学与逐人步骤 →');whole.className='button';root.append(whole);paragraph(root,t('整套共用最多 8 次搜索、16 次读取、2 次模型调用；启动前查看发送范围，可随时取消。'));s.unknown.forEach(tv=>paragraph(root,tv));for(const p of s.players){const d=document.createElement('details'),h=document.createElement('summary');h.textContent=p.id+t(' · 行动依据');d.append(h);p.facts.forEach(f=>paragraph(d,f));root.append(d)}if(!s.utility_needs.length)paragraph(root,t('此片段没有记录到对应方道具事件，不能据此虚构必需投法。'));for(const n of s.utility_needs){const d=document.createElement('div');d.className='coach-claim';paragraph(d,n.seconds.toFixed(1)+t(' 秒 · ')+n.actor+' · '+({smoke:t('烟'),flash:t('闪'),fire:t('火'),he:t('雷')}[n.kind]));paragraph(d,t('实际道具事件；投掷动作和适配仍待核对'));for(const c of n.candidates){paragraph(d,t('本地教学候选（未确认匹配）：')+c.title)}const a=document.createElement('a');a.href='/demos?view=research&case='+id+'&event='+encodeURIComponent(n.event_id);a.textContent=t('补齐这颗道具教学 →');d.append(a);root.append(d)}root.scrollIntoView({behavior:'smooth',block:'start'})}catch(e){$('caseStatus').textContent=e.message}}

$('map').addEventListener('contextmenu',e=>{if(board)e.preventDefault()});
