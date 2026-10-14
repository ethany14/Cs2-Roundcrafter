// Raw demo reads for local movement-model inference. Mirrors extract.cjs (same parser, round pairing,
// tick-rate check and player props); feature building happens in backend/cs2_agent/movement_model.py.
//   node window.cjs rounds <demo>              -> {map, rate, rounds:[{start,end,plants:[tick]}]}
//   node window.cjs ticks <demo> <t1,t2,...>   -> {rows:{tick:[player rows]}}
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const PROPS=['X','Y','Z','yaw','pitch','team_num','is_alive','health','armor_value','duck_amount','flash_duration','total_rounds_played'];
function rounds(file){
  const ev=n=>p.parseEvent(file,n,[],['total_rounds_played','is_warmup_period']).filter(x=>x.is_warmup_period===false);
  const starts=ev('round_freeze_end'),ends=ev('round_end'),plants=ev('bomb_planted');
  const {rounds}=pairRounds(starts,ends);
  const a=[...new Map(p.parseTicks(file,['game_time'],starts.slice(0,5).map(x=>x.tick)).filter(x=>finite(x.game_time)).map(x=>[x.tick,x])).values()].sort((a,b)=>a.tick-b.tick);
  const rate=a.length>1?(a[1].tick-a[0].tick)/(a[1].game_time-a[0].game_time):null;
  return {map:p.parseHeader(file).map_name,rate,rounds:rounds.map(({start,end})=>({start:start.tick,end:end.tick,plants:plants.filter(x=>x.tick>=start.tick&&x.tick<=end.tick).map(x=>x.tick)}))};
}
function ticks(file,list){
  const out={};for(const r of p.parseTicks(file,PROPS,list)){(out[r.tick]??=[]).push(Object.fromEntries(['steamid',...PROPS].map(k=>[k,r[k]])))}
  return {rows:out};
}
if(require.main===module){
  const [mode,file,arg]=process.argv.slice(2);
  const res=mode==='rounds'?rounds(file):mode==='ticks'?ticks(file,arg.split(',').map(Number)):null;
  if(!res){console.error('usage: window.cjs rounds|ticks <demo> [ticks]');process.exit(2)}
  process.stdout.write(JSON.stringify(res));
}
module.exports={rounds,ticks,PROPS};
