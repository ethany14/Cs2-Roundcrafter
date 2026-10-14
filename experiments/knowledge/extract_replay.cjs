// Replay track v1: 16 Hz player states + combat/utility events for smooth 2D playback. No model calls.
// Same round pairing and pseudonym rule as extract_match.cjs: IDs come from rows on the original 4 Hz ticks.
const fs=require('node:fs'),path=require('node:path');
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const VERSION=1,HZ=16;
const file=process.argv[2],out=process.argv[3];
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const dir=path.join(out,`replay-v${VERSION}`);fs.mkdirSync(dir,{recursive:true});
function progress(stage){fs.writeFileSync(path.join(out,'replay-progress.json'),JSON.stringify({stage}))}
const TYPES=['round_freeze_end','round_end','weapon_fire','player_hurt','player_death','smokegrenade_detonate','smokegrenade_expired','inferno_startburn','inferno_expire','flashbang_detonate','hegrenade_detonate','decoy_started','bomb_planted','bomb_defused','bomb_exploded'];
try{
 progress('reading events');
 const events=p.parseEvents(file,TYPES,['X','Y','Z','yaw','team_num'],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
 const starts=events.filter(e=>e.event_name==='round_freeze_end');const {rounds}=pairRounds(starts,events.filter(e=>e.event_name==='round_end'));
 const anchors=p.parseTicks(file,['game_time'],starts.slice(0,8).map(e=>e.tick));const unique=[...new Map(anchors.filter(a=>finite(a.game_time)).map(a=>[a.tick,a])).values()].sort((a,b)=>a.tick-b.tick);
 const rate=(unique[1].tick-unique[0].tick)/(unique[1].game_time-unique[0].game_time);
 const step4=Math.max(1,Math.round(rate/4)),step=Math.max(1,Math.round(rate/HZ));
 const base=new Set(),ticks=new Set();
 for(const {start,end} of rounds){for(let t=start.tick;t<end.tick;t+=step4)base.add(t);base.add(end.tick-1);for(let t=start.tick;t<end.tick;t+=step)ticks.add(t);ticks.add(end.tick-1)}
 for(const t of base)ticks.add(t);
 progress('reading 16 Hz player states');
 const rows=p.parseTicks(file,['X','Y','Z','yaw','team_num','is_alive','health','armor_value','active_weapon_name','flash_duration','has_helmet','has_defuser','team_rounds_total','team_clan_name'],[...ticks]);
 const ids=[...new Set(rows.filter(x=>[2,3].includes(x.team_num)&&base.has(x.tick)).map(x=>String(x.steamid)))].sort();
 const pid=id=>id==null||!ids.includes(String(id))?null:'P'+(ids.indexOf(String(id))+1);
 const byTick=new Map();for(const x of rows){if(![2,3].includes(x.team_num))continue;if(!byTick.has(x.tick))byTick.set(x.tick,[]);byTick.get(x.tick).push(x)}
 let n=0;const weapons=[],wi=w=>{if(!w)return -1;let i=weapons.indexOf(w);if(i<0){weapons.push(w);i=weapons.length-1}return i};
 for(const {start,end} of rounds){
  const number=++n;const tl=[...byTick.keys()].filter(t=>t>=start.tick&&t<end.tick).sort((a,b)=>a-b);
  const players={};
  tl.forEach((t,i)=>{for(const x of byTick.get(t)){const id=pid(x.steamid);if(!id)continue;
   const q=players[id]??={side:x.team_num===2?'T':'CT',x:[],y:[],z:[],yaw:[],hp:[],ar:[],w:[],fl:[],kit:0};
   const ok=[x.X,x.Y,x.Z].every(finite);
   q.x[i]=ok?Math.round(x.X):null;q.y[i]=ok?Math.round(x.Y):null;q.z[i]=ok?Math.round(x.Z):null;q.yaw[i]=finite(x.yaw)?Math.round(x.yaw):null;
   q.hp[i]=x.is_alive===true&&finite(x.health)?x.health:0;q.ar[i]=finite(x.armor_value)?x.armor_value:0;q.w[i]=wi(x.active_weapon_name||null);
   q.fl[i]=finite(x.flash_duration)?+x.flash_duration.toFixed(2):0;if(x.has_defuser)q.kit=1;if(x.has_helmet)q.hm=1;}});
  for(const q of Object.values(players))for(const k of ['x','y','z','yaw','hp','ar','w','fl'])for(let i=0;i<tl.length;i++)if(q[k][i]===undefined)q[k][i]=null;
  const sec=t=>+((t-start.tick)/rate).toFixed(3);
  // Real team names and match score at freeze end, per side (teams swap sides at half time).
  const teams={};for(const x of byTick.get(tl[0])||[]){const side=x.team_num===2?'T':'CT';if(!teams[side]&&(x.team_clan_name||Number.isFinite(x.team_rounds_total)))teams[side]={name:x.team_clan_name||null,score:Number.isFinite(x.team_rounds_total)?x.team_rounds_total:null}}
  const ev=[];
  for(const e of events){if(e.tick<start.tick||e.tick>end.tick)continue;const k=e.event_name;if(k==='round_freeze_end'||k==='round_end')continue;
   const pos=[e.x,e.y,e.z].every(finite)?[Math.round(e.x),Math.round(e.y),Math.round(e.z)]:[e.user_X,e.user_Y,e.user_Z].every(finite)?[Math.round(e.user_X),Math.round(e.user_Y),Math.round(e.user_Z)]:null;
   const row={k,t:sec(e.tick),a:pid(e.user_steamid)};
   if(k==='weapon_fire'){if(/knife|bayonet|grenade|flashbang|molotov|incgrenade|decoy|c4|taser/i.test(e.weapon||''))continue;row.w=(e.weapon||'').replace('weapon_','');row.p=pos;row.yaw=finite(e.user_yaw)?Math.round(e.user_yaw):null}
   else if(k==='player_hurt'){row.by=pid(e.attacker_steamid);row.w=e.weapon||null;row.d=e.dmg_health||0;row.h=e.health;row.g=e.hitgroup||null;row.p=pos;row.from=[e.attacker_X,e.attacker_Y].every(finite)?[Math.round(e.attacker_X),Math.round(e.attacker_Y)]:null}
   else if(k==='player_death'){row.by=pid(e.attacker_steamid);row.as=pid(e.assister_steamid);row.fa=!!e.assistedflash;row.w=e.weapon||null;row.hs=!!e.headshot;row.ts=!!e.thrusmoke;row.wb=(e.penetrated||0)>0;row.ns=!!e.noscope;row.p=pos}
   else{row.e=e.entityid??null;row.p=pos}
   ev.push(row)}
  fs.writeFileSync(path.join(dir,`round-${number}.json`),JSON.stringify({schema:VERSION,number,hz:HZ,rate,teams,winner:end.winner===2?'T':'CT',start_tick:start.tick,duration:(end.tick-start.tick)/rate,times:tl.map(sec),players,weapons,events:ev}));
 }
 // Local display names (most frequent name per steamid). Model payloads keep using the P-numbers.
 const names={};for(const x of rows){const id=pid(x.steamid);if(!id||!x.name)continue;const c=(names[id]??={steamid:String(x.steamid),counts:{}}).counts;c[x.name]=(c[x.name]||0)+1}
 const players=Object.fromEntries(Object.entries(names).map(([id,v])=>[id,{name:Object.entries(v.counts).sort((a,b)=>b[1]-a[1])[0][0],steamid:v.steamid}]));
 fs.writeFileSync(path.join(out,'players.json'),JSON.stringify({schema:1,source:'demo player names (local display only)',players}));
 fs.writeFileSync(path.join(dir,'index.json'),JSON.stringify({schema:VERSION,hz:HZ,rate,players:ids.length,rounds:n,
  limitations:['16 Hz 采样并在客户端插值；不是逐 tick 回放','射击线按开火时视角方向绘制，不代表弹道命中','烟雾/火焰范围为示意半径，不是体素或真实燃烧面积','致盲程度取自 flash_duration 字段']}));
 progress('replay track complete');
}catch(e){console.error(String(e.stack||e.message).slice(0,500));process.exitCode=1}
