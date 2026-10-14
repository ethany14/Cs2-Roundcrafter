// Extract observed projectile paths; no physics simulation or external media.
const fs=require('fs'),p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const dir='data/knowledge/metastack/extracted';fs.mkdirSync(dir,{recursive:true});
const demos=JSON.parse(fs.readFileSync('data/movement/dataset.json')).filter(d=>d.map==='de_nuke');
for(const d of demos){
 const out=`${dir}/${d.sha256}.json`;if(fs.existsSync(out)){console.log('cached '+d.member);continue;}
 const events=p.parseEvents(d.path,['smokegrenade_detonate','flashbang_detonate','hegrenade_detonate','inferno_startburn','round_freeze_end','round_end'],[],['total_rounds_played','is_warmup_period']);
 const starts=events.filter(e=>e.event_name==='round_freeze_end'&&e.is_warmup_period===false);
 const ends=events.filter(e=>e.event_name==='round_end'&&e.is_warmup_period===false);
 const groups=new Map(),tracks=[];
 for(const g of p.parseGrenades(d.path,[],true)){
  if(![g.x,g.y,g.z].every(Number.isFinite))continue;
  const key=g.grenade_entity_id;let tr=groups.get(key);
  if(!tr||g.tick-tr.last>64||tr.owner!==String(g.steamid)||tr.type!==g.grenade_type){tr={entity:key,type:g.grenade_type,owner:String(g.steamid),start:g.tick,last:g.tick,points:[]};groups.set(key,tr);tracks.push(tr);}
  tr.last=g.tick;if(!tr.points.length||g.tick%4===0)tr.points.push([g.tick,g.x,g.y,g.z]);
 }
 const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);const cases=[];
 for(const e of events.filter(e=>/detonate|startburn/.test(e.event_name)&&e.is_warmup_period===false)){
  const type={smokegrenade_detonate:'smoke',flashbang_detonate:'flash',hegrenade_detonate:'he',inferno_startburn:'fire'}[e.event_name];if(!type||![e.x,e.y,e.z].every(Number.isFinite))continue;
  const start=starts.filter(s=>s.tick<=e.tick).at(-1);if(!start)continue;const end=ends.find(x=>x.tick>start.tick);if(!end||e.tick>end.tick)continue;
  const candidates=tracks.filter(t=>t.start>=start.tick&&t.start<=e.tick&&e.tick-t.start<64*20&&(type==='fire'?/Molotov/.test(t.type)&&Math.abs(t.last-e.tick)<=16&&dist(t.points.at(-1).slice(1),[e.x,e.y,e.z])<180:t.entity===e.entityid&&t.last>=e.tick-8));
  candidates.sort((a,b)=>b.start-a.start);if(candidates.length!==1)continue;const t=candidates[0],path=t.points.filter(pt=>pt[0]<=e.tick);if(path.length<3)continue;
  cases.push({id:d.sha256.slice(0,12)+'-'+e.tick+'-'+t.entity,demo:d.member,demo_sha256:d.sha256,map:d.map,round:start.total_rounds_played+1,type,owner:t.owner,throw_tick:t.start,effect_tick:e.tick,round_start_tick:start.tick,clock_at_throw:115-(t.start-start.tick)/64,effect_position:[e.x,e.y,e.z],path,join:type==='fire'?'unique_nearby_molotov_end':'unique_entity_id_and_time'});
 }
 const ticks=new Set();for(const c of cases)for(let tick=c.throw_tick-128;tick<=c.throw_tick+64;tick+=8)if(tick>=c.round_start_tick)ticks.add(tick);
 const rows=p.parseTicks(d.path,['X','Y','Z','yaw','pitch','last_place_name','team_num','is_alive','inventory'],[...ticks]);
 const by=new Map();const anchors=new Map();for(const r of rows){const key=String(r.steamid);if(!by.has(key))by.set(key,[]);by.get(key).push(r);if(r.last_place_name&&r.is_alive){const cell=[r.last_place_name,Math.round(r.X/96),Math.round(r.Y/96),Math.round(r.Z/64)].join(':');anchors.set(cell,{position:[r.X,r.Y,r.Z],name:r.last_place_name});}}
 for(const c of cases){const actor=(by.get(c.owner)||[]).filter(r=>r.tick>=c.throw_tick-128&&r.tick<=c.throw_tick+64).sort((a,b)=>a.tick-b.tick);const release=actor.find(r=>r.tick===c.throw_tick);c.team=release?.team_num;c.release=release?{position:[release.X,release.Y,release.Z],yaw:release.yaw,pitch:release.pitch,area:release.last_place_name,inventory:release.inventory}:null;c.actor=actor.map(r=>({tick:r.tick,position:[r.X,r.Y,r.Z],yaw:r.yaw,pitch:r.pitch,area:r.last_place_name}));delete c.owner;}
 fs.writeFileSync(out,JSON.stringify({demo:d.member,sha256:d.sha256,tickrate:64,tickrate_note:'CS2 demo sampling assumption',cases:cases.filter(c=>c.release),anchors:[...anchors.values()]}));console.log(JSON.stringify({demo:d.member,cases:cases.length,anchors:anchors.size}));
}
