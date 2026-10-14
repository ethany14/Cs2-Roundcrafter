// Actual future playback is exported separately and never supplied to the planner.
const fs=require('node:fs'),crypto=require('node:crypto');
const parser=require('../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const [demo,input,output]=process.argv.slice(2),cases=JSON.parse(fs.readFileSync(input));
const sha=crypto.createHash('sha256').update(fs.readFileSync(demo)).digest('hex');
const anon=id=>crypto.createHash('sha256').update(sha+String(id)).digest('hex').slice(0,12);
const wanted=[...new Set(cases.flatMap(c=>Array.from({length:Math.floor((c.duration||6)*4)+1},(_,i)=>c.tick+i*16)))];
const rows=parser.parseTicks(demo,['X','Y','Z','yaw','pitch','team_num','is_alive','duck_amount','approximate_spotted_by'],wanted);
const snapshots=new Map();for(const r of rows){if(!snapshots.has(r.tick))snapshots.set(r.tick,[]);snapshots.get(r.tick).push(r);}
const result={};for(const c of cases){result[c.id]=Array.from({length:Math.floor((c.duration||6)*4)+1},(_,i)=>{
 const tick=c.tick+i*16,all=snapshots.get(tick)||[];
 return {time:i/4,players:all.filter(p=>[2,3].includes(p.team_num)).map(p=>({player:anon(p.steamid),side:p.team_num===3?'CT':'T',alive:p.is_alive,position:[p.X,p.Y,p.Z],yaw:p.yaw,pitch:p.pitch,duck_amount:p.duck_amount??0,approximate_spotted_by:Array.isArray(p.approximate_spotted_by)?p.approximate_spotted_by.map(anon):[]}))};
 });}
fs.writeFileSync(output,JSON.stringify(result));console.log(JSON.stringify({clips:cases.length,frames:wanted.length}));
