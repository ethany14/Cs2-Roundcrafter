const fs=require('node:fs'),parser=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');const {extract}=require('./extract.cjs');
const file=process.argv[2],ids=new Set(JSON.parse(fs.readFileSync(process.argv[3]))),chosen=[];
extract(file,(index,r,seq,t,start)=>{if(ids.has(index))chosen.push({index,actor:String(r.steamid),tick:t,start:start.tick,ticks:seq.slice(0,5).map(x=>x.tick)});});
const ticks=[...new Set(chosen.flatMap(x=>x.ticks))];
const raw=parser.parseTicks(file,['X','Y','Z','yaw','pitch','team_num','is_alive','duck_amount','flash_duration','flash_max_alpha','approximate_spotted_by','active_weapon_name'],ticks).map(({name,...r})=>r);
const events=parser.parseEvents(file,['player_sound','weapon_fire','smokegrenade_detonate','smokegrenade_expired','inferno_startburn','inferno_expire'],['X','Y','Z','team_num'],[]).filter(e=>chosen.some(x=>e.tick<=x.tick&&e.tick>=x.start&&(e.event_name.includes('smoke')||e.event_name.includes('inferno')||e.tick>x.tick-128))).map(({user_name,...e})=>e);
fs.writeFileSync(process.argv[4],JSON.stringify({chosen,frames:raw,events}));console.log(JSON.stringify({samples:chosen.length,frames:raw.length,events:events.length,sounds:events.filter(e=>e.event_name==='player_sound').length}));
