// Retrospective event evidence; never infer penetration for nonlethal hits.
const fs=require('node:fs'),crypto=require('node:crypto');
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const [file,out]=process.argv.slice(2);
const hash=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const anon=id=>crypto.createHash('sha256').update(hash+String(id)).digest('hex').slice(0,12);
const hurts=p.parseEvent(file,'player_hurt',['X','Y','Z','armor_value','has_helmet'],['is_warmup_period']).filter(e=>e.is_warmup_period===false);
const deaths=p.parseEvent(file,'player_death',[],['is_warmup_period']).filter(e=>e.is_warmup_period===false);
const key=e=>[e.tick,e.attacker_steamid,e.user_steamid,e.weapon].join(':');
const keyed=new Map();for(const d of deaths){const k=key(d);keyed.set(k,[...(keyed.get(k)||[]),d]);}
const hurtCounts=new Map();for(const h of hurts)hurtCounts.set(key(h),(hurtCounts.get(key(h))||0)+1);
const events=hurts.map(h=>{
 const matches=keyed.get(key(h))||[];
 const d=matches.length===1 && hurtCounts.get(key(h))===1 ? matches[0] : null;
 const a=['X','Y','Z'].map(c=>h['attacker_'+c]),b=['X','Y','Z'].map(c=>h['user_'+c]);
 return {tick:h.tick,attacker:anon(h.attacker_steamid),victim:anon(h.user_steamid),weapon:h.weapon,
  hitgroup:h.hitgroup,health_damage:h.dmg_health,armor_damage:h.dmg_armor,health_after:h.health,
  armor_after:h.armor,helmet_at_event:h.user_has_helmet??null,
  attacker_position:a,victim_position:b,
  foot_distance_units:[...a,...b].every(Number.isFinite)?Math.hypot(...a.map((v,i)=>v-b[i])):null,
  penetrated_surfaces:d?.penetrated??null,penetration_source:d?'unique_same_tick_death_event':'unavailable',
  through_smoke:d?.thrusmoke??null};
});
fs.writeFileSync(out,JSON.stringify({demo_sha256:hash,map:p.parseHeader(file).map_name,
 semantics:'Observed damage, not predicted counterfactual damage. Death-only penetration labels; null is unknown.',events}));
console.log(JSON.stringify({events:events.length,penetration_hits:events.filter(e=>e.penetrated_surfaces>0).length}));
