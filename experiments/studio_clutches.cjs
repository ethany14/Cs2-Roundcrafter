// Select long 1vN phases by alive counts and duration, never by winner.
const fs=require('node:fs'),crypto=require('node:crypto');
const p=require('../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('./situation/extract.cjs');
const file='data/demos/mouz-vs-spirit-m1-dust2.dem';
const event=n=>p.parseEvent(file,n,[],['total_rounds_played','is_warmup_period']).filter(e=>e.is_warmup_period===false);
const {rounds}=pairRounds(event('round_freeze_end'),event('round_end')),deaths=event('player_death'),plants=event('bomb_planted'),smokes=event('smokegrenade_detonate'),ends=event('smokegrenade_expired');
const fields=['X','Y','Z','yaw','pitch','team_num','is_alive','health','armor_value','has_defuser','inventory','active_weapon_name','current_equip_value','duck_amount','approximate_spotted_by'];
const ticks=[...new Set(deaths.map(d=>d.tick+1))],rows=p.parseTicks(file,fields,ticks),byTick=new Map();
for(const r of rows){if(!byTick.has(r.tick))byTick.set(r.tick,[]);byTick.get(r.tick).push(r);}
const candidates=[];
for(const tick of ticks){const all=(byTick.get(tick)||[]).filter(r=>[2,3].includes(r.team_num)),round=rounds.find(r=>r.start.tick<tick&&r.end.tick>tick);if(!round||all.length!==10)continue;
 for(const team of [2,3]){const own=all.filter(r=>r.is_alive&&r.team_num===team),enemy=all.filter(r=>r.is_alive&&r.team_num!==team);if(own.length!==1||enemy.length<1)continue;
 const actor=own[0],death=deaths.find(d=>d.tick>tick&&String(d.user_steamid)===String(actor.steamid));const duration=Math.min(35,(Math.min(round.end.tick,death?.tick??Infinity)-tick)/64);
 if(duration>=18)candidates.push({tick,all,round,actor,duration:Math.floor(duration),enemy:enemy.length});}}
candidates.sort((a,b)=>b.duration-a.duration||b.enemy-a.enemy);const selected=[];for(const c of candidates){if(selected.some(x=>x.round.start.tick===c.round.start.tick))continue;selected.push(c);if(selected.length===2)break;}
const pastTicks=[...new Set(selected.flatMap(c=>Array.from({length:11},(_,i)=>c.tick-i*32).filter(t=>t>=c.round.start.tick)))];
const past=p.parseTicks(file,fields,pastTicks),sha=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),anon=id=>crypto.createHash('sha256').update(sha+String(id)).digest('hex').slice(0,12);
const pack=r=>({player:anon(r.steamid),side:r.team_num===3?'CT':'T',alive:r.is_alive,position:[r.X,r.Y,r.Z],yaw:r.yaw,pitch:r.pitch,duck_amount:r.duck_amount??0,hp:r.health,armor:r.armor_value,has_defuser:r.has_defuser,inventory:r.inventory||[],weapon:r.active_weapon_name,equipment:r.current_equip_value,approximate_spotted_by:(r.approximate_spotted_by||[]).map(anon)});
const base=JSON.parse(fs.readFileSync('data/studio/selected.json'))[0];
const result=selected.map(c=>{const plant=plants.filter(x=>x.tick>=c.round.start.tick&&x.tick<=c.tick).at(-1);return {
 ...base,id:sha.slice(0,16)+'-clutch-'+c.tick+'-'+anon(c.actor.steamid),tick:c.tick,death_tick:null,round:c.round.start.total_rounds_played+1,actor:anon(c.actor.steamid),side:c.actor.team_num===3?'CT':'T',duration:c.duration,
 selection:'long_clutch_duration_selected; not a success label',
 features:{elapsed:(c.tick-c.round.start.tick)/64,own_alive:1,enemy_alive:c.enemy,bomb_planted:!!plant,bomb_age:plant?(c.tick-plant.tick)/64:null,position:[c.actor.X,c.actor.Y,c.actor.Z],equipment:c.actor.current_equip_value,nearest_teammate:null},
 evidence:{snapshot:c.all.map(pack),history:pastTicks.filter(t=>t<=c.tick&&t>=c.tick-320).sort((a,b)=>a-b).map(t=>({tick:t,players:past.filter(p=>p.tick===t&&[2,3].includes(p.team_num)).map(pack)})),
 smokes:smokes.filter(s=>s.tick>=c.round.start.tick&&s.tick<=c.tick).map(s=>({entity_id:s.entityid,start_tick:s.tick,position:[s.x,s.y,s.z],expired_tick:ends.find(e=>e.entityid===s.entityid&&e.tick>=s.tick&&e.tick<=c.tick)?.tick??null})),events:[]}
 };});
fs.writeFileSync('data/studio/clutches.json',JSON.stringify(result));console.log(JSON.stringify(result.map(c=>({id:c.id,round:c.round,duration:c.duration,side:c.side,enemy:c.features.enemy_alive}))));
