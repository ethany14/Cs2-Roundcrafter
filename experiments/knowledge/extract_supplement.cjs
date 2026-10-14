// Versioned supplement for the multi-round workbench: economy, scope state and real grenade projectiles.
// Reuses the same round pairing, sampled ticks and pseudonym rule as extract_match.cjs so P-numbers line up.
// No model calls. Positions are parser projectile entities, never inferred from player or landing points.
const fs=require('node:fs'),path=require('node:path');
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const VERSION=1;
const file=process.argv[2],out=process.argv[3];
const finite=v=>typeof v==='number'&&Number.isFinite(v);
function progress(stage){fs.writeFileSync(path.join(out,'supplement-progress.json'),JSON.stringify({stage}));}
const KIND={CSmokeGrenadeProjectile:'smoke',CFlashbangProjectile:'flash',CHEGrenadeProjectile:'he',CMolotovProjectile:'fire',CIncendiaryGrenadeProjectile:'fire',CDecoyProjectile:'decoy'};
const THROWN={smokegrenade:'smoke',flashbang:'flash',hegrenade:'he',molotov:'fire',incgrenade:'fire',decoy:'decoy'};
try{
 progress('正在读取回合边界');
 const events=p.parseEvents(file,['round_freeze_end','round_end','grenade_thrown'],['X','Y','Z','pitch','yaw','team_num'],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
 const starts=events.filter(e=>e.event_name==='round_freeze_end');const {rounds}=pairRounds(starts,events.filter(e=>e.event_name==='round_end'));
 const anchors=p.parseTicks(file,['game_time'],starts.slice(0,8).map(e=>e.tick));const unique=[...new Map(anchors.filter(a=>finite(a.game_time)).map(a=>[a.tick,a])).values()].sort((a,b)=>a.tick-b.tick);
 const rate=(unique[1].tick-unique[0].tick)/(unique[1].game_time-unique[0].game_time);
 const ticks=new Set();for(const {start,end} of rounds){for(let t=start.tick;t<end.tick;t+=Math.max(1,Math.round(rate/4)))ticks.add(t);ticks.add(end.tick-1)}
 progress('正在读取经济与开镜状态');
 const fields=['X','Y','team_num','is_scoped','balance','start_balance','current_equip_value','round_start_equip_value','cash_spent_this_round'];
 const rows=p.parseTicks(file,fields,[...ticks]);
 // Same pseudonym rule as extract_match.cjs: sorted steamids seen on T/CT in sampled ticks.
 const ids=[...new Set(rows.filter(x=>[2,3].includes(x.team_num)).map(x=>String(x.steamid)))].sort();const pseudonym=id=>id==null||!ids.includes(String(id))?null:'P'+(ids.indexOf(String(id))+1);
 const byTick=new Map();for(const x of rows){if(![2,3].includes(x.team_num))continue;if(!byTick.has(x.tick))byTick.set(x.tick,[]);byTick.get(x.tick).push(x)}
 progress('正在读取道具实体轨迹（较慢）');
 const projectiles=new Map();
 for(const g of p.parseGrenades(file)){
  const kind=KIND[g.grenade_type];if(!kind||![g.x,g.y,g.z].every(finite))continue;
  const key=g.grenade_entity_id+'|'+g.steamid;let item=projectiles.get(key);
  // Entity indexes are reused within a match: a gap over two seconds starts a new projectile.
  if(item&&g.tick-item.last>rate*2){item.done.push(item.cur);item.cur=null}
  if(!item){item={done:[],cur:null,last:-1e9};projectiles.set(key,item)}
  if(!item.cur)item.cur={entity:g.grenade_entity_id,steamid:String(g.steamid),kind,points:[]};
  item.cur.points.push([g.tick,g.x,g.y,g.z]);item.last=g.tick;
 }
 const all=[];for(const item of projectiles.values()){if(item.cur)item.done.push(item.cur);all.push(...item.done)}
 const thrown=events.filter(e=>e.event_name==='grenade_thrown');
 const summaries=[];let n=0;
 for(const {start,end} of rounds){
  const number=++n;const sampled=[...byTick].filter(([t])=>t>=start.tick&&t<end.tick).sort((a,b)=>a[0]-b[0]);
  const first=sampled[0]?.[1]||[];
  const economy=first.map(x=>({player:pseudonym(x.steamid),side:x.team_num===2?'T':'CT',start_balance:finite(x.start_balance)?x.start_balance:null,balance:finite(x.balance)?x.balance:null,round_start_equip_value:finite(x.round_start_equip_value)?x.round_start_equip_value:null,current_equip_value:finite(x.current_equip_value)?x.current_equip_value:null,cash_spent_this_round:finite(x.cash_spent_this_round)?x.cash_spent_this_round:null}));
  // Tick-keyed so a missing frame row can never shift scope flags onto another sample.
  const scoped={},scopeKnown={};for(const [tick,players] of sampled)for(const x of players){const id=pseudonym(x.steamid);if(!id||typeof x.is_scoped!=='boolean')continue;scopeKnown[id]=(scopeKnown[id]||0)+1;if(x.is_scoped)(scoped[id]??=[]).push(tick)}
  const check=sampled.length?sampled[Math.floor(sampled.length/2)]:null;
  const grenades=[];
  for(const g of all){
   const t0=g.points[0][0];if(t0<start.tick||t0>end.tick)continue;
   const throw_=thrown.filter(e=>String(e.user_steamid)===g.steamid&&THROWN[e.weapon]===g.kind&&e.tick<=t0&&t0-e.tick<=rate).sort((a,b)=>b.tick-a.tick)[0]||null;
   const pts=g.points.filter((q,i)=>i===0||i===g.points.length-1||i%4===0).slice(0,400);
   grenades.push({entity:g.entity,kind:g.kind,thrower:pseudonym(g.steamid),side:throw_?.user_team_num===2?'T':throw_?.user_team_num===3?'CT':null,
    spawn_tick:t0,spawn_seconds:(t0-start.tick)/rate,last_tick:g.points.at(-1)[0],origin:g.points[0].slice(1),
    trajectory:pts.map(q=>[+((q[0]-start.tick)/rate).toFixed(3),+q[1].toFixed(1),+q[2].toFixed(1),+q[3].toFixed(1)]),
    throw_event:throw_?{tick:throw_.tick,seconds:(throw_.tick-start.tick)/rate,player_position:[throw_.user_X,throw_.user_Y,throw_.user_Z].every(finite)?[throw_.user_X,throw_.user_Y,throw_.user_Z]:null,pitch:finite(throw_.user_pitch)?throw_.user_pitch:null,yaw:finite(throw_.user_yaw)?throw_.user_yaw:null}:null});
  }
  summaries.push({number,start_tick:start.tick,economy,scoped_ticks:scoped,scope_known_samples:scopeKnown,grenades,
   check:check?{tick:check[0],players:check[1].map(x=>({id:pseudonym(x.steamid),x:x.X,y:x.Y}))}:null});
 }
 fs.writeFileSync(path.join(out,`supplement-v${VERSION}.json`),JSON.stringify({schema:VERSION,tick_rate:rate,players:ids.length,rounds:summaries,
  fields:{economy:'freeze-end tick: start_balance, balance, round_start_equip_value, current_equip_value, cash_spent_this_round',scoped:'ticks (same 4 Hz samples as frames) where is_scoped is true; scope_known_samples counts boolean samples',grenades:'parseGrenades projectile entity positions, every 4th tick; origin = first projectile tick'},
  limitations:['投掷视角来自 grenade_thrown 事件时刻的玩家状态，不保证是游戏内可复现的精确 setang','轨迹为每 4 tick 抽样的实体位置，不是逐 tick 完整弹道','金钱字段为冻结结束时刻；冻结后补买反映在后续 current_equip_value 之外']}));
 progress('补充数据完成');
}catch(e){console.error(String(e.stack||e.message).slice(0,400));process.exitCode=1}
