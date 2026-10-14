// Full-match observation adapter over the project's installed parser. No model calls.
const fs=require('node:fs'),path=require('node:path');
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const file=process.argv[2],out=process.argv[3];fs.mkdirSync(out,{recursive:true});
function progress(stage){fs.writeFileSync(path.join(out,'parser-progress.json'),JSON.stringify({stage}));}
const finite=v=>typeof v==='number'&&Number.isFinite(v);const xyz=(e,pre='')=>[e[pre+'X'],e[pre+'Y'],e[pre+'Z']].every(finite)?[e[pre+'X'],e[pre+'Y'],e[pre+'Z']]:null;
try{
 progress('正在读取回合和道具事件');const header=p.parseHeader(file);
 const types=['round_freeze_end','round_end','bomb_planted','bomb_defused','bomb_exploded','player_death','smokegrenade_detonate','smokegrenade_expired','flashbang_detonate','hegrenade_detonate','inferno_startburn','inferno_expire'];
 const events=p.parseEvents(file,types,['X','Y','Z','team_num'],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
 const starts=events.filter(e=>e.event_name==='round_freeze_end');const {rounds,skips}=pairRounds(starts,events.filter(e=>e.event_name==='round_end'));
 if(!rounds.length)throw Error('NO_COMPLETE_ROUNDS');if(rounds.length>100)throw Error('TOO_MANY_ROUNDS');
 const anchors=p.parseTicks(file,['game_time'],starts.slice(0,8).map(e=>e.tick));const unique=[...new Map(anchors.filter(a=>finite(a.game_time)).map(a=>[a.tick,a])).values()].sort((a,b)=>a.tick-b.tick);
 const rates=unique.slice(1).map((b,i)=>(b.tick-unique[i].tick)/(b.game_time-unique[i].game_time));const rate=rates[0];if(!finite(rate)||rate<30||rate>256||rates.some(r=>Math.abs(r-rate)>.1))throw Error('TICK_RATE_UNKNOWN');
 const ticks=new Set();for(const {start,end} of rounds){if((end.tick-start.tick)/rate>600)throw Error('ROUND_TOO_LONG');for(let t=start.tick;t<end.tick;t+=Math.max(1,Math.round(rate/4)))ticks.add(t);ticks.add(end.tick-1)}
 if(ticks.size>60000)throw Error('FRAME_BUDGET_EXHAUSTED');
 progress('正在提取四帧每秒的玩家轨迹');
 const fields=['X','Y','Z','yaw','team_num','is_alive','health','armor_value','inventory','active_weapon_name','last_place_name','game_time'];
 const rows=p.parseTicks(file,fields,[...ticks]);const ids=[...new Set(rows.filter(x=>[2,3].includes(x.team_num)).map(x=>String(x.steamid)))].sort();const pseudonym=id=>id==null||!ids.includes(String(id))?null:'P'+(ids.indexOf(String(id))+1);
 const byTick=new Map();for(const x of rows){if(![2,3].includes(x.team_num)||!xyz(x))continue;if(!byTick.has(x.tick))byTick.set(x.tick,[]);byTick.get(x.tick).push({id:pseudonym(x.steamid),side:x.team_num===2?'T':'CT',position:xyz(x),yaw:finite(x.yaw)?x.yaw:null,alive:x.is_alive===true,hp:finite(x.health)?x.health:null,armor:finite(x.armor_value)?x.armor_value:null,area:x.last_place_name||null,inventory:x.inventory||[],weapon:x.active_weapon_name||null})}
 const summaries=[];let n=0;
 for(const {start,end} of rounds){
  const number=++n;const selected=events.filter(e=>e.tick>=start.tick&&e.tick<=end.tick);
  const packed=selected.map((e,i)=>({id:`r${number}-e${i}`,type:e.event_name,tick:e.tick,seconds:(e.tick-start.tick)/rate,actor:pseudonym(e.user_steamid),attacker:pseudonym(e.attacker_steamid),side:e.user_team_num===2?'T':e.user_team_num===3?'CT':null,position:[e.x,e.y,e.z].every(finite)?[e.x,e.y,e.z]:xyz(e,'user_'),actor_position:xyz(e,'user_'),entity:e.entityid??null,weapon:e.weapon||null}));
  const frames=[...byTick].filter(([t])=>t>=start.tick&&t<end.tick).sort((a,b)=>a[0]-b[0]).map(([tick,players])=>({tick,seconds:(tick-start.tick)/rate,players}));
  const round={number,source_round:start.total_rounds_played+1,start_tick:start.tick,end_tick:end.tick,duration:(end.tick-start.tick)/rate,winner:end.winner===2?'T':'CT',frames,events:packed};
  fs.writeFileSync(path.join(out,`round-${number}.json`),JSON.stringify(round));summaries.push({number,source_round:round.source_round,duration:round.duration,winner:round.winner,frames:frames.length,events:packed.length,missing_roster_frames:frames.filter(f=>f.players.length!==10).length});
 }
 fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify({schema:1,map:header.map_name,game_build:header.patch_version,tick_rate:rate,sampling_hz:4,perspective:'spectator_global_not_player_knowledge',players:ids.length,rounds:summaries,skipped_rounds:skips,limitations:['只含冻结结束到回合结束；四帧每秒抽样，不是逐 tick 完整回放','匿名玩家编号仅在本场内稳定；阵营按每帧读取','道具点为实际事件坐标；不重建烟雾体素、火焰范围和空中弹道','战术意图、队内语音和指挥内容未知']}));progress('轨迹提取完成');
}catch(e){console.error(String(e.message).slice(0,200));process.exitCode=1}
