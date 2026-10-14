/* Tactic room (04), career page (05) and the review's match-stats tab.
   Stats come from parsed demos on this machine; ratings are labelled (1.0 = HLTV public formula, 2.0≈ = approximation). */
(()=>{
const E=id=>document.getElementById(id);
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e[k]=v;else if(v!=null&&v!==false)e.setAttribute(k,v===true?'':v)}for(const c of kids.flat())if(c!=null)e.append(c);return e}
function b(text,fn,cls=''){const x=el('button',{class:cls},text);x.onclick=async e=>{e.stopPropagation();try{await fn(e)}catch(err){flash(err.message)}};return x}
function flash(msg){const n=el('div',{class:'hub-toast'},msg);document.body.append(n);setTimeout(()=>n.remove(),4000)}
const MAPNAME=m=>(m||'').replace('de_','').replace(/^./,c=>c.toUpperCase());
const fmt=v=>v==null?'—':v;const date=s=>s?new Date(s*1000).toLocaleDateString():'—';

/* ================= tactic room ================= */
let roomRows=[],roomSel=null;
async function refreshRoom(){
  const q=new URLSearchParams({map:E('roomMap').value,q:E('roomSearch').value,tag:E('roomTag').value,folder:E('roomFolder').value});
  const r=await api('/api/room/tactics?'+q);roomRows=r.tactics;
  const keep=(sel,vals,label)=>{const v=sel.value;sel.replaceChildren(el('option',{value:''},label),...vals.map(x=>el('option',{value:x},x)));sel.value=vals.includes(v)?v:''};
  keep(E('roomTag'),r.tags,t('全部标签'));keep(E('roomFolder'),r.folders,t('全部文件夹'));
  const cards=E('roomCards');cards.replaceChildren();
  if(!roomRows.length)cards.append(el('p',{class:'mc-note'},t('还没有战术。点击“新建战术”，或在复盘中打开战术板保存。')));
  for(const x of roomRows){const c=el('button',{class:'room-card'+(roomSel===x.id?' sel':'')},el('b',{},x.name),
      el('span',{class:'meta'},el('span',{class:'mc-tag'},MAPNAME(x.map)),x.side!=='any'?el('span',{class:'mc-tag '+(x.side==='T'?'amber':'cyan')},x.side):null,el('span',{class:'mc-tag'},x.stages+t(' 阶段')),x.folder?el('span',{class:'mc-tag'},'▤ '+x.folder):null),
      el('span',{class:'tags'},...x.tags.map(g=>el('i',{},'#'+g))),el('small',{},t('更新于 ')+date(x.updated)+(x.source?.match?t(' · 来自复盘 R')+(x.source.round??'?'):'')));
    c.onclick=()=>selectTactic(x.id);cards.append(c)}
  const leg=E('roomLegacyList');leg.replaceChildren(...r.legacy.map(l=>el('div',{class:'wb-line'},el('i',{class:'dot'}),el('span',{class:'lbl'},l.name+' · '+MAPNAME(l.map)),el('small',{class:'meta'},l.stages+t(' 阶段')),el('span',{class:'acts'},b(t('导入战术室'),async()=>{await api('/api/room/import_legacy',{match:l.match,board:l.id});flash(t('已导入'));refreshRoom()},'ibtn wide-ibtn')))));
  E('roomLegacy').hidden=!r.legacy.length;
}
async function selectTactic(id){roomSel=id;const x=await api('/api/room/tactic?id='+id);const box=E('roomDetail');box.replaceChildren();
  box.append(await preview(x),el('h2',{},x.name));
  const name=el('input',{value:x.name,'aria-label':t('名称')}),tags=el('input',{value:x.tags.join(', '),placeholder:t('标签，用逗号分隔')}),folder=el('input',{value:x.folder||'',placeholder:t('文件夹')}),
    side=el('select',{},...[['any',t('不限阵营')],['T','T'],['CT','CT']].map(([v,l])=>el('option',{value:v},l))),notes=el('textarea',{placeholder:t('备注（站位思路、口令、适用经济等）')},x.notes||'');side.value=x.side||'any';
  box.append(el('label',{class:'field'},t('名称'),name),el('div',{class:'wb-row'},el('label',{class:'field'},t('标签'),tags),el('label',{class:'field'},t('文件夹'),folder),el('label',{class:'field'},t('阵营'),side)),el('label',{class:'field'},t('备注'),notes),
    el('div',{class:'toolbar'},b(t('▶ 打开编辑'),()=>openEditor(x),'mc-primary'),
      b(t('保存信息'),async()=>{await api('/api/room/tactic',{id:x.id,name:name.value,tags:tags.value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),folder:folder.value,side:side.value,notes:notes.value});flash(t('已保存'));refreshRoom()}),
      b(t('复制'),async()=>{const d=await api('/api/room/tactic/duplicate',{id:x.id});await refreshRoom();selectTactic(d.id)}),
      b(t('删除'),async()=>{if(!confirm(t('删除这个战术？此操作不可撤销。')))return;await api('/api/room/tactic/delete',{id:x.id});roomSel=null;E('roomDetail').replaceChildren(el('p',{class:'mc-note'},t('已删除。')));refreshRoom()})),
    el('p',{class:'mc-note'},t('{0} 阶段 · 创建于 {1}',[x.steps.length,date(x.created)])+(x.source?.match?t(' · 来源：比赛复盘 R{0}',[x.source.round??'?']):'')));
  refreshRoom()}
async function preview(x){const meta=await api('/api/lab/radar/'+x.map).catch(()=>null);const NS='http://www.w3.org/2000/svg',s=document.createElementNS(NS,'svg');s.setAttribute('class','room-preview');
  if(!meta)return s;const cb=meta.content_bounds.map(v=>v*1024),size=Math.max(cb[2]-cb[0],cb[3]-cb[1]);s.setAttribute('viewBox',`${cb[0]} ${cb[1]} ${size} ${size}`);
  const add=(tag,a)=>{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(a))e.setAttribute(k,v);s.append(e);return e};
  add('image',{href:meta.upper_url,width:1024,height:1024,class:'room-radar'});const st=x.steps[0];
  for(const it of st.items||[]){if(it.type==='arrow'||it.type==='pen')add('path',{d:it.pts.map((p,i)=>(i?'L':'M')+p[0]+' '+p[1]).join(' '),fill:'none',stroke:it.color,'stroke-width':4});else if(['smoke','flash','fire','he'].includes(it.type))add('circle',{cx:it.pts[0][0],cy:it.pts[0][1],r:{smoke:144,flash:60,fire:110,he:90}[it.type]/meta.scale,fill:{smoke:'#cfd3d855',flash:'#fff6b055',fire:'#ff9a3d55',he:'#ff6a4a44'}[it.type]})}
  for(const p of st.players)add('circle',{cx:(p.position[0]-meta.pos_x)/meta.scale,cy:(meta.pos_y-p.position[1])/meta.scale,r:9,fill:p.side==='T'?'#f0b34a':'#62b6e6',stroke:'#000','stroke-width':2});
  return s}
async function openEditor(x){
  // board-only mode: radar of the tactic's map, no match loaded
  window.showView('review',{noAuto:true});document.body.classList.add('board-only');playing=false;round=null;data=null;match=null;
  radar=await api('/api/lab/radar/'+x.map);engine.setRadar(radar);fitMap();$('radar').setAttribute('href',radar.upper_url);$('floor').disabled=!radar.lower_url;
  $('title').textContent=x.name||t('新战术');$('meta').textContent=MAPNAME(x.map)+' · '+t('战术室');
  TacticBoard.setStandalone(true);
  if(x.id)TacticBoard.load(x);else{TacticBoard.open([],{});E('boardName').value=x.name||t('新战术')}
  TacticBoard.setStandalone(true);await loadBoards();render()}
E('roomNew').onclick=()=>{const map=E('roomMap').value||'de_dust2';openEditor({map,name:t('新战术 · ')+MAPNAME(map)}).catch(e=>flash(e.message))};
for(const id of ['roomMap','roomTag','roomFolder'])E(id).onchange=()=>refreshRoom().catch(e=>flash(e.message));
let roomTimer=null;E('roomSearch').oninput=()=>{clearTimeout(roomTimer);roomTimer=setTimeout(()=>refreshRoom().catch(e=>flash(e.message)),250)};

/* ================= career page ================= */
let acct=null,viewing=null,playersIdx=[];
async function refreshAccount(){acct=await api('/api/hub/account');const a=acct,card=E('accountCard');card.replaceChildren();
  if(a.linked){card.append(el('div',{class:'acct'},a.avatar?el('img',{src:a.avatar,alt:'',class:'avatar'}):el('div',{class:'avatar ph'},'◉'),
      el('div',{},el('b',{},a.persona||t('已关联账号')),el('small',{class:'mc-mono'},a.steamid),el('span',{class:'mc-tag '+(a.verified?'green':'amber')},a.verified?t('Steam 登录已验证'):t('手动输入 · 未验证')))),
    el('div',{class:'toolbar'},b(t('查看我的数据'),()=>showProfile(a.steamid),'mc-primary'),a.has_api_key?b(t('刷新 Steam 资料'),async()=>{await api('/api/hub/refresh',{});refreshAccount()}):null,b(t('解除关联'),async()=>{if(confirm(t('解除与此 Steam 账号的关联？')))await api('/api/hub/unlink',{});refreshAccount()})))}
  else{const sid=el('input',{placeholder:t('SteamID64 或个人资料链接')});
    card.append(el('p',{},t('关联后自动追踪你的比赛，并在“我的生涯”中显示数据。')),el('a',{href:'/auth/steam/start',class:'steam-btn'},t('通过 Steam 登录关联')),
      el('p',{class:'mc-note'},t('将跳转到 steamcommunity.com 官方页面登录；本应用只接收并向 Steam 核验你的 SteamID，不接触密码。')),
      el('details',{},el('summary',{},t('手动输入 SteamID')),sid,b(t('关联'),async()=>{await api('/api/hub/account/manual',{steamid:sid.value});refreshAccount()})))}
  const q=new URLSearchParams(location.search);if(q.get('link_error'))card.append(el('p',{class:'wb-note warn'},t('关联失败：')+q.get('link_error')));
  renderTracking();if(a.linked&&!viewing)showProfile(a.steamid)}
function renderTracking(){const a=acct,s=a.settings,box=E('trackingCard');box.replaceChildren();
  const dir=el('input',{value:s.replays_dir}),auto=el('input',{type:'checkbox'});auto.checked=s.auto_import;
  const key=el('input',{type:'password',autocomplete:'off',placeholder:a.has_api_key?t('已保存（留空不修改）'):t('32 位 Steam Web API Key')}),code=el('input',{type:'password',autocomplete:'off',placeholder:a.has_auth_code?t('已保存（留空不修改）'):t('比赛历史验证码 xxxx-xxxxx-xxxx')}),known=el('input',{value:s.known_code,placeholder:'CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx'});
  const w=a.watcher;
  box.append(el('h3',{},t('① 自动导入下载的 demo')),el('label',{class:'field'},t('CS2 回放目录'),dir),el('label',{class:'check'},auto,t('自动导入（每分钟检查一次）')),
    el('p',{class:'mc-note'},t('在 CS2「观战 → 你的比赛」下载 demo 后，会自动导入并解析。')+(w.last_scan?t(' 上次检查 {0} · 已导入 {1}',[new Date(w.last_scan*1000).toLocaleTimeString(),w.imported]):'')+(w.last_error?' · '+t(w.last_error):'')),
    el('div',{class:'toolbar'},b(t('立即检查'),async()=>{const r=await api('/api/hub/scan',{});flash(t('导入 {0} 场，等待 {1} 场',[r.imported,r.pending]));refreshAccount()})),
    el('h3',{},t('② 追踪新比赛（Steam 分享码）')),el('p',{class:'mc-note'},t('使用你自己的 Steam Web API Key 与比赛历史验证码（Steam 帮助 → CS2 → 比赛历史）。密钥只保存在本机，页面不会再显示。')),
    el('label',{class:'field'},'Steam Web API Key',key),el('label',{class:'field'},t('比赛历史验证码'),code),el('label',{class:'field'},t('最近一场比赛分享码'),known),
    el('div',{class:'toolbar'},b(t('保存设置'),async()=>{const raw={replays_dir:dir.value,auto_import:auto.checked,known_code:known.value};if(key.value)raw.api_key=key.value;if(code.value)raw.auth_code=code.value;await api('/api/hub/settings',raw);flash(t('设置已保存'));refreshAccount()},'mc-primary'),
      b(t('检查新比赛'),async()=>{const r=await api('/api/hub/sharecodes/check',{});flash(t('发现 {0} 场新比赛',[r.found.length]));refreshAccount()})),
    a.sharecodes.length?el('div',{class:'wb-lines'},...a.sharecodes.slice().reverse().slice(0,8).map(c=>el('div',{class:'wb-line'},el('i',{class:'dot'}),el('span',{class:'lbl mc-mono'},c.code),el('small',{class:'meta'},'#'+c.match_id.slice(-8)),el('span',{class:'acts'})))):null,
    a.sharecodes.length?el('p',{class:'mc-note'},t('Valve 不允许在没有游戏客户端的情况下下载天梯 demo：请在 CS2 中下载这些比赛，下载后会自动导入。')):null)}
async function loadPlayers(){const r=await api('/api/hub/players');playersIdx=r.players;E('playerList').replaceChildren(...playersIdx.map(p=>el('option',{value:p.name})));
  E('playerQuick').replaceChildren(...playersIdx.slice(0,12).map(p=>b(p.name+' · '+p.matches,()=>showProfile(p.steamid),'chip')))}
E('playerSearch').onchange=()=>{const p=playersIdx.find(x=>x.name.toLowerCase()===E('playerSearch').value.trim().toLowerCase());if(p)showProfile(p.steamid);else flash(t('本机 demo 中没有这名选手'))};
function spark(vals){const w=420,h=70,NS='http://www.w3.org/2000/svg',s=document.createElementNS(NS,'svg');s.setAttribute('viewBox',`0 0 ${w} ${h}`);s.setAttribute('class','spark');
  if(vals.length<2)return s;const lo=Math.min(...vals,.6),hi=Math.max(...vals,1.4),x=i=>8+i*(w-16)/(vals.length-1),y=v=>h-8-(v-lo)/(hi-lo)*(h-16);
  const base=document.createElementNS(NS,'line');base.setAttribute('x1',0);base.setAttribute('x2',w);base.setAttribute('y1',y(1));base.setAttribute('y2',y(1));base.setAttribute('class','spark-base');s.append(base);
  const p=document.createElementNS(NS,'polyline');p.setAttribute('points',vals.map((v,i)=>x(i)+','+y(v)).join(' '));s.append(p);
  vals.forEach((v,i)=>{const c=document.createElementNS(NS,'circle');c.setAttribute('cx',x(i));c.setAttribute('cy',y(v));c.setAttribute('r',3);c.setAttribute('class',v>=1?'up':'down');s.append(c)});return s}
async function showProfile(steamid){viewing=steamid;const p=await api('/api/hub/profile?steamid='+steamid);const root=E('profileStats');root.replaceChildren();
  E('profileWho').textContent=(p.name||steamid)+(p.is_me?t(' · 我'):'');
  if(!p.matches.length){root.append(el('p',{},p.is_me?t('还没有包含你的 demo。下载比赛 demo 后会自动导入，或在“比赛库”上传。'):t('本机 demo 中没有这名选手的比赛。')));return}
  const s=p.summary,tile=(label,val,sub,cls='')=>el('div',{class:'stat-tile '+cls},el('small',{},label),el('b',{},val),sub?el('span',{},sub):null);
  root.append(el('div',{class:'profile-head'},el('h2',{},p.name),el('span',{class:'mc-mono'},p.steamid),el('span',{class:'mc-tag'},t('{0} 胜 {1} 负 · {2} 场',[p.wins,p.losses,p.matches.length]))),
    el('div',{class:'stat-tiles'},tile('Rating 2.0≈',s.rating2_approx.toFixed(2),'Rating 1.0 '+s.rating1.toFixed(2),s.rating2_approx>=1?'good':'bad'),tile('ADR',s.adr.toFixed(1)),tile('KAST',s.kast.toFixed(1)+'%'),
      tile('K / D',s.kd.toFixed(2),s.kills+' / '+s.deaths+' / '+s.assists),tile(t('爆头率'),s.hs_pct.toFixed(1)+'%'),tile(t('首杀 / 首死'),s.opening_kills+' / '+s.opening_deaths),tile(t('多杀回合'),String(Object.values(s.multi).reduce((a,b)=>a+b,0)),'3K+ '+(s.multi['3']+s.multi['4']+s.multi['5'])),tile(t('道具伤害'),String(s.utility_damage))),
    el('h3',{},t('Rating 走势（每场）')),spark(p.matches.map(m=>m.rating2_approx)));
  const mt=el('table',{class:'hub-table'},el('thead',{},el('tr',{},...[t('地图'),t('场次'),t('胜率'),'K/D','ADR','KAST','Rating 2.0≈'].map(h=>el('th',{},h)))),el('tbody',{},...p.maps.map(m=>el('tr',{},el('td',{},MAPNAME(m.map)),el('td',{},m.matches),el('td',{},Math.round(100*m.wins/Math.max(1,m.matches))+'%'),el('td',{},m.kd.toFixed(2)),el('td',{},m.adr.toFixed(1)),el('td',{},m.kast.toFixed(1)+'%'),el('td',{},m.rating2_approx.toFixed(2))))));
  root.append(el('h3',{},t('地图')),mt,el('h3',{},t('比赛（点击打开回放）')));
  const list=el('table',{class:'hub-table click'},el('thead',{},el('tr',{},...[t('日期'),t('地图'),t('比分'),'K-D-A','ADR','KAST','HS%','R 2.0≈'].map(h=>el('th',{},h)))),el('tbody',{},...p.matches.slice().reverse().map(m=>{
    const tr=el('tr',{class:m.result==='W'?'win':m.result==='L'?'loss':''},el('td',{},date(m.played_at)),el('td',{},MAPNAME(m.map)),el('td',{},el('b',{class:'res'},m.result),' '+fmt(m.score[0])+' : '+fmt(m.score[1])),el('td',{},m.kills+'-'+m.deaths+'-'+m.assists),el('td',{},m.adr.toFixed(1)),el('td',{},m.kast.toFixed(0)+'%'),el('td',{},m.hs_pct.toFixed(0)+'%'),el('td',{class:m.rating2_approx>=1?'good':'bad'},m.rating2_approx.toFixed(2)));
    tr.title=t('打开这场比赛的回放');tr.onclick=()=>openMatchFor(m.match,m.player_id);return tr})));
  root.append(list,...p.notes.map(n=>el('p',{class:'mc-note'},t(n))))}
async function openMatchFor(mid,pid){await open(mid,1);engine.selected=pid;dirty=true;updateUi(true)}

/* ================= review: match stats tab ================= */
async function renderMatchStats(){const root=E('matchStats');root.replaceChildren(el('p',{class:'mc-note'},t('正在统计…')));
  let s;try{s=await api('/api/hub/stats?id='+match)}catch(e){root.replaceChildren(el('p',{},t('需要 16 Hz 回放数据才能统计（生成补充解析）。')));return}
  root.replaceChildren(el('p',{class:'mc-mono'},Object.entries(s.final_score).map(([k,v])=>k+' '+v).join('  :  ')+' · '+s.rounds+t(' 回合')));
  const teams=[...new Set(s.players.map(p=>p.team))];
  for(const team of teams){root.append(el('h3',{},team||'—'),el('table',{class:'hub-table click'},el('thead',{},el('tr',{},...[t('选手'),'K','D','A','ADR','KAST','HS%',t('首杀'),'R 2.0≈'].map(h=>el('th',{},h)))),
    el('tbody',{},...s.players.filter(p=>p.team===team).map(p=>{const tr=el('tr',{},el('td',{},el('b',{},p.name)),el('td',{},p.kills),el('td',{},p.deaths),el('td',{},p.assists),el('td',{},p.adr.toFixed(1)),el('td',{},p.kast.toFixed(0)+'%'),el('td',{},p.hs_pct.toFixed(0)+'%'),el('td',{},p.opening_kills+'/'+p.opening_deaths),el('td',{class:p.rating2_approx>=1?'good':'bad'},p.rating2_approx.toFixed(2)));
      tr.title=t('查看该选手生涯数据');tr.onclick=()=>{if(p.steamid){window.showView('profile');showProfile(p.steamid)}};return tr}))))}
  root.append(...s.notes.map(n=>el('p',{class:'mc-note'},t(n))))}
E('statsTab').onclick=()=>{showPanel('stats');renderMatchStats()};

/* ================= view hooks ================= */
document.addEventListener('viewchange',e=>{if(e.detail==='room')refreshRoom().catch(err=>flash(err.message));if(e.detail==='profile'){refreshAccount().catch(err=>flash(err.message));loadPlayers().catch(()=>{})}});
window.PlayerHub={refreshRoom,showProfile};
})();
