// Evidence extraction only. Proximity is NOT line-of-sight or tradeability.
const fs=require('node:fs'),crypto=require('node:crypto');
const parser=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('./extract.cjs');
const finite=Number.isFinite;
const dist=(a,b)=>Math.hypot(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
function extract(file){
 const event=n=>parser.parseEvent(file,n,[],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
 const starts=event('round_freeze_end'),{rounds}=pairRounds(starts,event('round_end'));
 const deaths=event('player_death'),plants=event('bomb_planted');
 const smokes=event('smokegrenade_detonate'),smokeEnds=event('smokegrenade_expired');
 const blasts=event('hegrenade_detonate'),shots=event('fire_bullets');
 // Current parser exposes the voxel field as a scalar, NOT a decoded volume.
 const grenadeRows=parser.parseGrenades(file,['Grenade.m_nVoxelUpdate','Grenade.m_nVoxelFrameDataSize','Grenade.m_VoxelFrameData'],false);
 const smokeUpdates=new Map();
 for(const r of grenadeRows){if(r.grenade_type!=='CSmokeGrenadeProjectile'||!r.m_nVoxelFrameDataSize)continue;
  const list=smokeUpdates.get(r.grenade_entity_id)||[],prev=list.at(-1);
  if(!prev||prev.revision!==r.m_nVoxelUpdate||prev.bytes!==r.m_nVoxelFrameDataSize)list.push({tick:r.tick,revision:r.m_nVoxelUpdate,bytes:r.m_nVoxelFrameDataSize,volume_decoded:false});
  smokeUpdates.set(r.grenade_entity_id,list);
 }
 const anchors=[...new Map(parser.parseTicks(file,['game_time'],starts.slice(0,5).map(s=>s.tick)).map(r=>[r.tick,r])).values()].sort((a,b)=>a.tick-b.tick);
 const rates=anchors.slice(1).map((r,i)=>(r.tick-anchors[i].tick)/(r.game_time-anchors[i].game_time));
 const rate=rates[0];if(!finite(rate)||rate<30||rate>256||rates.some(r=>!finite(r)||Math.abs(r-rate)>.1))throw Error('Invalid tick rate');
 const candidates=deaths.flatMap(d=>{const round=rounds.find(r=>d.tick>r.start.tick+3*rate&&d.tick<r.end.tick);return round?[{d,round,tick:d.tick-Math.round(2*rate)}]:[];});
 const historyTicks=c=>Array.from({length:11},(_,i)=>c.tick-Math.round(i*rate/2)).filter(t=>t>=c.round.start.tick).reverse();
 const ticks=[...new Set(candidates.flatMap(historyTicks))];
 const rows=parser.parseTicks(file,['X','Y','Z','yaw','pitch','team_num','is_alive','health','current_equip_value','total_rounds_played','approximate_spotted_by','duck_amount','flash_duration','flash_max_alpha','inventory','active_weapon_name','CCSPlayerPawn.m_MoveType','CCSPlayerPawn.CCSPlayer_MovementServices.m_nLadderSurfacePropIndex'],ticks);
 const snapshots=new Map();for(const row of rows){if(!snapshots.has(row.tick))snapshots.set(row.tick,[]);snapshots.get(row.tick).push(row);}
 const sha=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 const anon=id=>crypto.createHash('sha256').update(sha+String(id)).digest('hex').slice(0,12);
 const cases=[];let skipped=0;
 for(const {d,round,tick} of candidates){
  const all=(snapshots.get(tick)||[]).filter(p=>[2,3].includes(p.team_num));
  const actor=all.find(p=>String(p.steamid)===String(d.user_steamid));
  if(all.length!==10||new Set(all.map(p=>String(p.steamid))).size!==10||all.some(p=>p.total_rounds_played!==round.start.total_rounds_played)||!actor?.is_alive||all.some(p=>![p.X,p.Y,p.Z,p.health,p.current_equip_value].every(finite))){skipped++;continue;}
  const alive=all.filter(p=>p.is_alive),friends=alive.filter(p=>p.team_num===actor.team_num&&p!==actor),enemies=alive.filter(p=>p.team_num!==actor.team_num);
  if(!enemies.length){skipped++;continue;}
  friends.sort((a,b)=>dist(actor,a)-dist(actor,b));
  const past=(snapshots.get(tick-Math.round(rate))||[]).find(p=>String(p.steamid)===String(actor.steamid));
  const pack=p=>({player:anon(p.steamid),side:p.team_num===3?'CT':'T',alive:p.is_alive,position:[p.X,p.Y,p.Z],yaw:p.yaw,pitch:p.pitch,hp:p.health,equipment:p.current_equip_value,duck_amount:p.duck_amount??null,flash_duration:p.flash_duration??null,flash_max_alpha:p.flash_max_alpha??null,inventory:p.inventory??[],weapon:p.active_weapon_name??null,move_type:p['CCSPlayerPawn.m_MoveType']!=null?Number(p['CCSPlayerPawn.m_MoveType']):null,ladder_surface_index:p['CCSPlayerPawn.CCSPlayer_MovementServices.m_nLadderSurfacePropIndex']??null,approximate_spotted_by:Array.isArray(p.approximate_spotted_by)?p.approximate_spotted_by.map(anon):null});
  const history=historyTicks({tick,round}).map(t=>({tick:t,players:(snapshots.get(t)||[]).filter(p=>[2,3].includes(p.team_num)).map(pack)}));
  const smokeHistory=smokes.filter(s=>s.tick>=round.start.tick&&s.tick<=tick).map(s=>({entity_id:s.entityid,start_tick:s.tick,position:[s.x,s.y,s.z],expired_tick:smokeEnds.find(e=>e.entityid===s.entityid&&e.tick>=s.tick&&e.tick<=tick)?.tick??null,voxel_updates:(smokeUpdates.get(s.entityid)||[]).filter(u=>u.tick>=s.tick&&u.tick<=tick)}));
  const disturbances={he:blasts.filter(e=>e.tick>=tick-2*rate&&e.tick<=tick).map(e=>({tick:e.tick,position:[e.x,e.y,e.z]})),shots:shots.filter(e=>e.tick>=tick-rate&&e.tick<=tick).map(e=>({tick:e.tick,origin:[e.origin_x,e.origin_y,e.origin_z],angles:[e.angles_x,e.angles_y],spread:e.spread,inaccuracy:e.inaccuracy}))};
  const killEvents=deaths.filter(e=>e.tick>=tick-3*rate&&e.tick<=Math.min(round.end.tick,d.tick+5*rate)).map(e=>({tick:e.tick,attacker:anon(e.attacker_steamid),victim:anon(e.user_steamid),weapon:e.weapon,through_smoke:e.thrusmoke,penetrated_surfaces:e.penetrated??null,attacker_blind:e.attackerblind}));
  const retaliations=deaths.filter(e=>e.tick>d.tick&&e.tick<=Math.min(round.end.tick,d.tick+5*rate)&&String(e.user_steamid)===String(d.attacker_steamid)&&friends.some(p=>String(p.steamid)===String(e.attacker_steamid)));
  cases.push({id:sha.slice(0,16)+'-'+d.tick+'-'+anon(actor.steamid),demo_sha256:sha,map:parser.parseHeader(file).map_name,round:round.start.total_rounds_played+1,tick,death_tick:d.tick,tick_rate:rate,
   actor:anon(actor.steamid),side:actor.team_num===3?'CT':'T',features:{elapsed:(tick-round.start.tick)/rate,own_alive:friends.length+1,enemy_alive:enemies.length,equipment:actor.current_equip_value,bomb_planted:plants.some(p=>p.tick>=round.start.tick&&p.tick<=tick),position:[actor.X,actor.Y,actor.Z],nearest_teammate:friends.length?dist(actor,friends[0]):null,movement_last_second:past?dist(actor,past):null},
   evidence:{snapshot:all.map(pack),history,smokes:smokeHistory,smoke_disturbances:disturbances,nearby_teammates:friends.map(p=>({player:anon(p.steamid),distance_units:dist(actor,p)})),events:killEvents,subsequent_killer_death_within_5s:retaliations.map(e=>e.tick)},
   perspective:'spectator_global',selection:'two_seconds_before_death; outcome-selected, not representative of all decisions',review_status:'unreviewed',limitations:['No map occlusion or navigation check','No reconstruction of player-known enemies, audio or team communication','Nearby teammate does not establish tradeability','Subsequent killer death does not establish a coordinated trade','Professional action is not a correctness label']});
 }
 return {schema:1,sha256:sha,tick_rate:rate,cases,skipped};
}
if(require.main===module){const result=extract(process.argv[2]);fs.writeFileSync(process.argv[3],JSON.stringify(result));console.log(JSON.stringify({cases:result.cases.length,skipped:result.skipped}));}
module.exports={extract};
