const fs=require('fs'),p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const file='data/knowledge/metastack/teaching.json',data=JSON.parse(fs.readFileSync(file)),demos=JSON.parse(fs.readFileSync('data/movement/dataset.json'));
const fields=['X','Y','Z','yaw','pitch','Grenade.m_flThrowStrength','Grenade.m_bJumpThrow','Grenade.m_fThrowTime','CCSPlayerPawn.CCSPlayer_MovementServices.m_flDuckAmount'];
for(const hash of new Set(Object.values(data.cases).map(c=>c.demo_sha256))){
 const d=demos.find(d=>d.sha256===hash),cs=Object.values(data.cases).filter(c=>c.demo_sha256===hash),ticks=new Set();for(const c of cs)for(let t=c.throw_tick-128;t<=c.throw_tick+32;t++)ticks.add(t);
 const rows=p.parseTicks(d.path,fields,[...ticks]);
 for(const c of cs){const candidates=rows.filter(r=>r.tick===c.throw_tick&&Math.hypot(r.X-c.release.position[0],r.Y-c.release.position[1],r.Z-c.release.position[2])<.1);if(candidates.length!==1)continue;
  const actor=rows.filter(r=>r.steamid===candidates[0].steamid&&r.tick>=c.throw_tick-128&&r.tick<=c.throw_tick+32).sort((a,b)=>a.tick-b.tick);
  const evidence=actor.filter(r=>r.tick<=c.throw_tick&&r.tick>=c.throw_tick-16&&r['Grenade.m_fThrowTime']>0).at(-1);
  c.method={status:evidence?'observed_active_grenade_fields':'unknown',sample_tick:evidence?.tick??null,jump_throw:evidence?.['Grenade.m_bJumpThrow']??null,strength:evidence?.['Grenade.m_flThrowStrength']??null,raw_throw_time:evidence?.['Grenade.m_fThrowTime']??null,duck_amount:candidates[0]['CCSPlayerPawn.CCSPlayer_MovementServices.m_flDuckAmount']??null,physical_key_sequence:null};
  c.actor=actor.map(r=>({tick:r.tick,position:[r.X,r.Y,r.Z],yaw:r.yaw,pitch:r.pitch,duck:r['CCSPlayerPawn.CCSPlayer_MovementServices.m_flDuckAmount']??null}));
 }
 console.log(d.member+' enriched '+cs.length);
}
fs.writeFileSync(file,JSON.stringify(data));
