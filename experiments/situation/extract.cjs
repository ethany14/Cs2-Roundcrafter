// Reuse the installed parser; no LLM requests and no player identifiers in output.
const fs=require('node:fs'), crypto=require('node:crypto');
const parser=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const OFFSETS=[15,35,55,75,95,115,135,155];
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const winner=e=>({CT:3,T:2}[e.winner]||e.winner);
function pairRounds(starts,ends){
  const rounds=[],skips=[];
  starts=[...starts].sort((a,b)=>a.tick-b.tick);
  for(let i=0;i<starts.length;i++){
    const start=starts[i],next=starts[i+1]?.tick??Infinity;
    // New parser-normalized ends increment total_rounds_played, older ends do not.
    // Pair by time boundaries; counters alone would silently shift labels.
    const end=ends.filter(e=>e.tick>start.tick&&e.tick<next&&[2,3].includes(winner(e)));
    if(end.length!==1){skips.push({round:start.total_rounds_played+1,reason:'missing_or_ambiguous_end'});continue;}
    rounds.push({start,end:{...end[0],winner:winner(end[0])}});
  }
  return {rounds,skips};
}

function extract(file){
  const event=name=>parser.parseEvent(file,name,[],['total_rounds_played','is_warmup_period'])
    .filter(e=>e.is_warmup_period===false);
  const starts=event('round_freeze_end'),ends=event('round_end'),plants=event('bomb_planted');
  const header=parser.parseHeader(file);
  const anchors=parser.parseTicks(file,['game_time'],starts.slice(0,5).map(e=>e.tick));
  const unique=[...new Map(anchors.filter(a=>finite(a.game_time)).map(a=>[a.tick,a])).values()].sort((a,b)=>a.tick-b.tick);
  const rates=unique.slice(1).map((b,i)=>(b.tick-unique[i].tick)/(b.game_time-unique[i].game_time));
  const rate=rates[0];
  if(!finite(rate)||rate<30||rate>256||rates.some(x=>!finite(x)||Math.abs(x-rate)>.1))throw Error('Cannot reliably infer tick rate');
  const {rounds,skips}=pairRounds(starts,ends);
  const ticks=[...new Set(rounds.flatMap(({start,end})=>OFFSETS.map(s=>start.tick+Math.round(s*rate)).filter(t=>t<end.tick)))];
  const rows=ticks.length?parser.parseTicks(file,['team_num','is_alive','health','armor_value','current_equip_value','game_time','total_rounds_played'],ticks):[];
  const snapshots=new Map();for(const row of rows){if(!snapshots.has(row.tick))snapshots.set(row.tick,[]);snapshots.get(row.tick).push(row);}
  const states=[];
  for(const {start,end} of rounds)for(const seconds of OFFSETS){
    const tick=start.tick+Math.round(seconds*rate);if(tick>=end.tick)continue;
    const all=(snapshots.get(tick)||[]).filter(p=>[2,3].includes(p.team_num));
    if(all.length!==10||new Set(all.map(p=>p.steamid)).size!==10||all.some(p=>p.total_rounds_played!==start.total_rounds_played)){
      skips.push({tick,reason:'incomplete_5v5_snapshot'});continue;
    }
    const alive=all.filter(p=>p.is_alive===true),ct=alive.filter(p=>p.team_num===3),t=alive.filter(p=>p.team_num===2);
    if(!ct.length||!t.length)continue; // exclude already-resolved elimination states
    if(alive.some(p=>!finite(p.health)||!finite(p.armor_value)||!finite(p.current_equip_value))) {skips.push({tick,reason:'missing_features'});continue;}
    const sum=(team,k)=>team.reduce((a,p)=>a+p[k],0);
    const pastPlants=plants.filter(p=>p.tick>=start.tick&&p.tick<=tick);
    const plant=pastPlants.at(-1);
    states.push({round:start.total_rounds_played+1,tick,round_start_tick:start.tick,round_end_tick:end.tick,
      features:{ct_alive:ct.length,t_alive:t.length,ct_health:sum(ct,'health'),t_health:sum(t,'health'),
        ct_armor:sum(ct,'armor_value'),t_armor:sum(t,'armor_value'),ct_equipment:sum(ct,'current_equip_value'),t_equipment:sum(t,'current_equip_value'),
        elapsed_seconds:seconds,bomb_planted:plant?1:0,bomb_age_seconds:plant?(tick-plant.tick)/rate:0},
      label_ct_win:end.winner===3?1:0});
  }
  return {schema:1,kind:'demo',map:header.map_name,tick_rate:rate,
    demo_sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
    perspective:'spectator_global_not_player_knowledge',sampling_seconds:OFFSETS,states,skips};
}
if(require.main===module){try{const result=extract(process.argv[2]);fs.writeFileSync(process.argv[3],JSON.stringify(result));console.log(JSON.stringify({map:result.map,states:result.states.length,skips:result.skips.length}));}catch(e){console.error(e.message);process.exitCode=1;}}
module.exports={extract,pairRounds};
