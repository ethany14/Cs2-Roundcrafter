// Causal, player-relative movement samples. No enemy coordinates, IDs or future outcomes as inputs.
const fs=require('node:fs');
const p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const {pairRounds}=require('../situation/extract.cjs');
const finite=x=>typeof x==='number'&&Number.isFinite(x);
function extract(file, onSample=null){
 const ev=n=>p.parseEvent(file,n,[],['total_rounds_played','is_warmup_period']).filter(x=>x.is_warmup_period===false);
 const starts=ev('round_freeze_end'),ends=ev('round_end'),plants=ev('bomb_planted');
 const {rounds,skips}=pairRounds(starts,ends);
 const a=[...new Map(p.parseTicks(file,['game_time'],starts.slice(0,5).map(x=>x.tick)).filter(x=>finite(x.game_time)).map(x=>[x.tick,x])).values()].sort((a,b)=>a.tick-b.tick);
 const rate=(a[1].tick-a[0].tick)/(a[1].game_time-a[0].game_time);
 if(!finite(rate)||Math.abs(rate-64)>.1)throw Error('Unsupported tick rate '+rate);
 const ticks=rounds.flatMap(({start,end})=>Array.from({length:Math.floor((end.tick-start.tick)/32)},(_,i)=>start.tick+i*32));
 const props=['X','Y','Z','yaw','pitch','team_num','is_alive','health','armor_value','duck_amount','flash_duration','total_rounds_played'];
 const raw=p.parseTicks(file,props,ticks),byTick=new Map();
 for(const r of raw){if(!byTick.has(r.tick))byTick.set(r.tick,[]);byTick.get(r.tick).push(r);}
 const samples=[];let rejected=0;
 for(const {start,end} of rounds){
  // 2 s history, 2 s future. Centres 2 s apart; train/test separated by entire series.
  for(let t=start.tick+128;t+128<end.tick;t+=128){
   const now=byTick.get(t)||[];
   if(now.length!==10||new Set(now.map(x=>x.steamid)).size!==10)continue;
   for(const r of now.filter(x=>x.is_alive&&[2,3].includes(x.team_num))){
    const seq=Array.from({length:9},(_,i)=>(byTick.get(t+(i-4)*32)||[]).find(x=>x.steamid===r.steamid));
    if(seq.some(x=>!x||!x.is_alive||x.team_num!==r.team_num||x.total_rounds_played!==r.total_rounds_played||['X','Y','Z','yaw','pitch','health','armor_value','duck_amount','flash_duration'].some(k=>!finite(x[k])))){rejected++;continue;}
    if(seq.slice(1).some((x,i)=>Math.hypot(x.X-seq[i].X,x.Y-seq[i].Y)>200)){rejected++;continue;}
    const angle=r.yaw*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
    const local=(x,y)=>[(x*c+y*s)/250,(-x*s+y*c)/250];
    const hist=seq.slice(0,5).map(x=>[...local(x.X-r.X,x.Y-r.Y),(x.Z-r.Z)/250,Math.sin((x.yaw-r.yaw)*Math.PI/180),Math.cos((x.yaw-r.yaw)*Math.PI/180),x.pitch/90,x.duck_amount,Math.min(x.flash_duration,5)/5]);
    const mates=now.filter(x=>x.is_alive&&x.team_num===r.team_num&&x.steamid!==r.steamid&&finite(x.X)&&finite(x.Y)).sort((a,b)=>Math.hypot(a.X-r.X,a.Y-r.Y)-Math.hypot(b.X-r.X,b.Y-r.Y)).slice(0,2);
    const context=[r.health/100,r.armor_value/100,r.team_num===3?1:0,(t-start.tick)/64/120,now.filter(x=>x.is_alive&&x.team_num===r.team_num).length/5,now.filter(x=>x.is_alive&&x.team_num!==r.team_num).length/5];
    const plant=plants.find(x=>x.tick>=start.tick&&x.tick<=t);context.push(plant?1:0,plant?(t-plant.tick)/64/40:0);
    for(let i=0;i<2;i++){const m=mates[i];context.push(...(m?[...local(m.X-r.X,m.Y-r.Y).map(x=>Math.max(-12,Math.min(12,x))),(m.Z-r.Z)/250,1]:[0,0,0,0]));}
    const y=[5,6,8].flatMap(i=>local(seq[i].X-r.X,seq[i].Y-r.Y));
    samples.push({h:hist,c:context,y,round:r.total_rounds_played+1,tick:t});
    if(onSample)onSample(samples.length-1,r,seq,t,start);
   }
  }
 }
 return {schema:1,map:p.parseHeader(file).map_name,rounds:rounds.length,rejected,skipped_rounds:skips.length,samples};
}
if(require.main===module){const data=extract(process.argv[2]);fs.writeFileSync(process.argv[3],JSON.stringify(data));console.log(JSON.stringify({map:data.map,rounds:data.rounds,samples:data.samples.length,rejected:data.rejected}));}
module.exports={extract};
