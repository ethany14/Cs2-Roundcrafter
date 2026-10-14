// Conditional known-plant scenario. Future data only enters weak labels, never inputs.
const fs=require('node:fs'),p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const NAMES=['hp','armor','equipment','kit','kit_known','ct_alive','t_alive','mate_nearest','mate_near_count','bomb_known','bomb_age','bomb_distance_lower_bound','bomb_height','mates_near_bomb','self_smokes','self_flashes','self_fire_grenades','self_flash','seen_count','seen_age','seen_distance','seen_valid','footstep_candidates','other_sound_candidates','round_age','history_valid'];
const distance=(a,b)=>Math.hypot(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
function label(now,future,bomb,defuse=false){
 if(defuse)return {label:0,reason:'observed_defuse_attempt'};
 if(!future||!future.is_alive)return {label:-1,reason:'missing_or_dead_before_horizon'};
 const delta=distance(future,bomb)-distance(now,bomb),moved=distance(now,future);
 if(delta<=-192)return {label:0,reason:'approach_at_least_192_units'};
 if(delta>=192&&distance(future,bomb)>=1200)return {label:2,reason:'withdraw_at_least_192_units_and_far'};
 if(moved<=128&&Math.abs(delta)<=96)return {label:1,reason:'limited_net_displacement'};
 return {label:-1,reason:'ambiguous_motion'};
}
function features(all,actor,t,start,plant,observations,events){
 const ct=all.filter(x=>x.team_num===3&&x.is_alive),en=all.filter(x=>x.team_num===2&&x.is_alive),mates=ct.filter(x=>x.steamid!==actor.steamid),known=t>=plant.tick+128,bomb={X:plant.user_X,Y:plant.user_Y,Z:plant.user_Z};
 const seen=new Map();for(const x of observations)if(x.tick<=t&&x.tick>=start&&x.team_num===2&&x.is_alive&&(x.approximate_spotted_by||[]).map(String).includes(String(actor.steamid)))seen.set(String(x.steamid),x);
 const last=[...seen.values()].sort((a,b)=>b.tick-a.tick)[0];const sounds=events.filter(e=>e.tick<=t&&e.tick>Math.max(start,t-128)&&String(e.user_steamid)!==String(actor.steamid)&&e.radius>0&&Number.isFinite(e.user_X)&&Math.hypot(e.user_X-actor.X,e.user_Y-actor.Y,e.user_Z-actor.Z)<e.radius);
 const inv=actor.inventory||[];const count=re=>inv.filter(x=>re.test(x)).length;
 return [actor.health/100,actor.armor_value/100,actor.current_equip_value/10000,Number(actor.has_defuser===true),Number(typeof actor.has_defuser==='boolean'),ct.length/5,en.length/5,Math.min(6000,Math.min(...mates.map(x=>distance(x,actor)),6000))/6000,mates.filter(x=>distance(x,actor)<600).length/4,Number(known),known?(t-plant.tick)/2560:0,known?distance(actor,bomb)/6000:0,known?(bomb.Z-actor.Z)/1000:0,known?mates.filter(x=>distance(x,bomb)<800).length/4:0,count(/smoke/i)/2,count(/flash/i)/2,count(/molotov|incendiary/i)/2,Math.min(5,actor.flash_duration||0)/5,seen.size/5,last?Math.min(120,(t-last.tick)/64)/120:0,last?distance(actor,last)/6000:0,Number(!!last),Math.min(8,sounds.filter(e=>e.step).length)/8,Math.min(8,sounds.filter(e=>!e.step).length)/8,(t-start)/64/180,1];
}
function main(file,out){
 const ev=n=>p.parseEvent(file,n,['X','Y','Z'],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
 const {rounds}=pairRounds(ev('round_freeze_end'),ev('round_end'));const plants=ev('bomb_planted'),defuses=ev('bomb_begindefuse');const sounds=p.parseEvent(file,'player_sound',['X','Y','Z'],[]);const jobs=[];const ticks=new Set();
 for(const {start,end} of rounds){const plant=plants.find(x=>x.tick>=start.tick&&x.tick<end.tick);if(!plant||!['user_X','user_Y','user_Z'].every(k=>Number.isFinite(plant[k])))continue;
  const anchors=[2,8,14,20,26,32].map(s=>plant.tick+s*64).filter(t=>t<end.tick);
  const rt=[];for(let t=start.tick;t<end.tick;t+=128){ticks.add(t);rt.push(t);}for(const t of anchors)for(let k=-6;k<=3;k++){const tick=t+k*128;if(tick>=start.tick&&tick<end.tick)ticks.add(tick);}
  jobs.push({start,end,plant,anchors,rt});
 }
 const props=['X','Y','Z','team_num','is_alive','health','armor_value','current_equip_value','has_defuser','inventory','flash_duration','approximate_spotted_by'];const raw=p.parseTicks(file,props,[...ticks]);const by=new Map();for(const x of raw){if(!by.has(x.tick))by.set(x.tick,[]);by.get(x.tick).push(x);}
 const rows=[];
 for(const job of jobs){const {start,end,plant,anchors}=job;const observations=raw.filter(x=>x.tick>=start.tick&&x.tick<end.tick).sort((a,b)=>a.tick-b.tick);const bomb={X:plant.user_X,Y:plant.user_Y,Z:plant.user_Z};
  for(const t of anchors){const now=by.get(t)||[];if(now.length!==10)continue;
   for(const actor of now.filter(x=>x.team_num===3&&x.is_alive)){
    const h=[];for(let k=-6;k<=0;k++){const tick=t+k*128;const all=by.get(tick)||[];const self=all.find(x=>x.steamid===actor.steamid&&x.is_alive);h.push(self?features(all,self,tick,start.tick,plant,observations,sounds):Array(NAMES.length).fill(0));}
    if(h.flat().some(x=>!Number.isFinite(x)))continue;
    const future=(by.get(t+384)||[]).find(x=>x.steamid===actor.steamid);const df=defuses.some(x=>x.tick>t&&x.tick<=t+384&&x.tick<end.tick&&String(x.user_steamid)===String(actor.steamid));const target=t+384<end.tick?label(actor,future,bomb,df):{label:-1,reason:'round_ends_before_horizon'};
    const xyz=x=>[x.X,x.Y,x.Z];const spotted=new Map();for(const x of observations)if(x.tick<=t&&x.team_num===2&&x.is_alive&&(x.approximate_spotted_by||[]).map(String).includes(String(actor.steamid)))spotted.set(String(x.steamid),x);
    const view={self:xyz(actor),bomb:xyz(bomb),teammates:now.filter(x=>x.team_num===3&&x.is_alive&&x.steamid!==actor.steamid).map(x=>({position:xyz(x),hp:x.health,kit:x.has_defuser})),last_seen_enemies:[...spotted.values()].map(x=>({position:xyz(x),age_seconds:(t-x.tick)/64}))};
    rows.push({round:start.total_rounds_played+1,tick:t,plant_tick:plant.tick,h,view,...target});
   }
  }
 }
 fs.writeFileSync(out,JSON.stringify({schema:1,names:NAMES,map:p.parseHeader(file).map_name,scenario:'plant_position_disclosed_to_CT_at_plant_plus_2s; not reconstructed team communication',rows}));console.log(JSON.stringify({rows:rows.length,labels:rows.reduce((a,r)=>(a[r.label]=(a[r.label]||0)+1,a),{})}));
}
if(require.main===module)main(process.argv[2],process.argv[3]);module.exports={features,label,NAMES};
