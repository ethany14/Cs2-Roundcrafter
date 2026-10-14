const fs=require('node:fs'),path=require('node:path'),p=require('../../outputs/cs2-coach-prototype/node_modules/@laihoe/demoparser2');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'outputs/movement/strategy/review');fs.mkdirSync(out,{recursive:true});
const cases=JSON.parse(fs.readFileSync(path.join(root,'outputs/movement/strategy/blind-review.json'))),ds=JSON.parse(fs.readFileSync(path.join(root,'data/movement/dataset.json')));const index=[];
const finite=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
for(const hash of new Set(cases.map(c=>c.demo_sha256))){
 const group=cases.filter(c=>c.demo_sha256===hash),demo=ds.find(d=>d.sha256===hash);const fields=['X','Y','Z','yaw','pitch','team_num','is_alive','health','armor_value','has_defuser','inventory','active_weapon_name','current_equip_value','balance','start_balance','cash_spent_this_round','approximate_spotted_by'];
 const parsed=p.parseTicks(demo.path,fields,[...new Set(group.map(c=>c.tick))]);
 for(const c of group){
  const all=parsed.filter(x=>x.tick===c.tick&&[2,3].includes(x.team_num)).sort((a,b)=>String(a.steamid).localeCompare(String(b.steamid)));if(all.length!==10)throw Error('Incomplete roster '+c.id);
  const actors=all.filter(x=>x.team_num===3&&Math.hypot(x.X-c.view.self[0],x.Y-c.view.self[1],x.Z-c.view.self[2])<.1);if(actors.length!==1)throw Error('Ambiguous actor '+c.id);const actor=actors[0];
  const pack=x=>({id:(x.team_num===3?'CT':'T')+(all.filter(a=>a.team_num===x.team_num).indexOf(x)+1),side:x.team_num===3?'CT':'T',self:x===actor,alive:!!x.is_alive,position:[x.X,x.Y,x.Z],yaw:finite(x.yaw),pitch:finite(x.pitch),hp:finite(x.health),armor:finite(x.armor_value),kit:typeof x.has_defuser==='boolean'?x.has_defuser:null,weapon:x.active_weapon_name||null,inventory:x.inventory||[],cash:finite(x.balance),start_cash:finite(x.start_balance),spent_this_round:finite(x.cash_spent_this_round),equipment:finite(x.current_equip_value)});
  const team=all.filter(x=>x.team_num===3).map(pack),sum=k=>team.every(x=>x[k]!==null)?team.reduce((s,x)=>s+x[k],0):null,alive=team.filter(x=>x.alive);
  const known=all.filter(x=>x.team_num===2&&x.is_alive&&(x.approximate_spotted_by||[]).map(String).includes(String(actor.steamid))).map(x=>({id:pack(x).id,position:[x.X,x.Y,x.Z],yaw:finite(x.yaw),evidence:'self_spotted_flag_approximate',age_seconds:0}));
  const data={id:c.id,sample_index:c.sample_index,map:c.map,round:c.round,tick:c.tick,scenario:c.scenario,actor:pack(actor).id,bomb:c.view.bomb,team,economy:{team_cash:sum('cash'),team_start_cash:sum('start_cash'),team_spent_this_round:sum('spent_this_round'),alive_equipment:alive.every(x=>x.equipment!==null)?alive.reduce((s,x)=>s+x.equipment,0):null,loss_bonus:null,next_round_income:null},known_enemies:known,last_seen_enemies:c.view.last_seen_enemies,ct_alive:alive.length,t_alive:all.filter(x=>x.team_num===2&&x.is_alive).length,options:c.options,limits:['Bomb position supplied by scenario.','Enemy spotting is approximate, old positions are not refreshed.','Static collision geometry only, no dynamic door or smoke rendering.','Loss bonus and next-round income are unknown.']};
  fs.writeFileSync(path.join(out,c.id+'.json'),JSON.stringify(data));fs.writeFileSync(path.join(out,c.id+'-observer.json'),JSON.stringify({id:c.id,mode:'spectator_only_not_player_knowledge',enemies:all.filter(x=>x.team_num===2&&x.is_alive).map(x=>{const r=pack(x);return {id:r.id,position:r.position,yaw:r.yaw};})}));
  index.push({id:c.id,map:c.map,round:c.round,ct_alive:data.ct_alive,t_alive:data.t_alive,sample_index:c.sample_index});
 }
}
index.sort((a,b)=>a.ct_alive-b.ct_alive||a.map.localeCompare(b.map));fs.writeFileSync(path.join(out,'index.json'),JSON.stringify(index));console.log('Built',index.length,'review scenes');
