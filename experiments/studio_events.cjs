const fs=require('node:fs');
const parser=require('../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const demo='data/demos/mouz-vs-spirit-m1-dust2.dem';
const events=parser.parseEvents(demo,['weapon_fire','bullet_impact','smokegrenade_detonate','flashbang_detonate','hegrenade_detonate','inferno_startburn','inferno_expire','smokegrenade_expired'],['X','Y','Z','yaw','pitch'],[]);
fs.writeFileSync('data/studio/events-private.json',JSON.stringify(events));
const grenades=parser.parseGrenades(demo,[],true).filter(g=>g.x!=null&&g.tick%4===0);
fs.writeFileSync('data/studio/grenades-private.json',JSON.stringify(grenades));
console.log(JSON.stringify({events:events.length,grenadeSamples:grenades.length}));
