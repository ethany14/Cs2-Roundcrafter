import * as THREE from '/vendor/three.module.js';
import {OrbitControls} from '/vendor/OrbitControls.js';

const $=id=>document.getElementById(id);
let clip,selected=0,branch='continue',time=0,playing=false,mode='overview',token='',busy=false,loadVersion=0;
let actualView,alternativeView,geometry,materials,mapInfo;
const branchNames={continue:'延续行为',cooperate:'积极协同',counter:'对手反制'};
const point=p=>new THREE.Vector3(p[0]/100,p[2]/100,-p[1]/100);
const error=message=>{$('error').textContent=message;$('error').hidden=!message;};
async function api(url,options){const response=await fetch(url,options);const value=await response.json();if(!response.ok)throw Error(value.error||'请求未完成');return value;}
function lerp(a,b,t){return a.map((v,i)=>v+(b[i]-v)*t);}
function angle(a,b,t){return a+(((b-a+540)%360)-180)*t;}
function along(path,progress){
  if(path.length<2)return path[0];const lengths=path.slice(1).map((p,i)=>Math.hypot(...p.map((v,j)=>v-path[i][j])));const total=lengths.reduce((a,b)=>a+b,0);
  if(total<.01)return path[0];let distance=Math.min(1,progress)*total;
  for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]&&lengths[i]>0)return lerp(path[i],path[i+1],distance/lengths[i]);distance-=lengths[i];}return path.at(-1);
}
function effectiveResponse(player,plan){
  const choices=clip.responses[player.player]||[];
  const picked=plan.responses?.[branch]?.find(r=>r.player===player.player);
  if(picked)return choices.find(r=>r.id===picked.route_id)||choices[0];
  // Local candidates expose their deterministic assumptions. AI omissions mean hold.
  if(plan.responses)return choices[0];
  const id=branch==='cooperate'&&player.role==='ally'?'support_'+plan.route_id:branch==='counter'&&player.role==='enemy'?'counter':branch==='continue'?'continue':'hold';
  return choices.find(r=>r.id===id)||choices[0];
}
function actualPlayers(t){
  const frames=$('information').value==='spectator'&&clip.spectator?clip.spectator:clip.actual;const i=Math.min(frames.length-1,Math.floor(t*4));const a=frames[i],b=frames[Math.min(i+1,frames.length-1)];
  return a.players.map(p=>{const next=b.players.find(n=>n.player===p.player);const q=Math.min(1,Math.max(0,(t-a.time)*4));
    if(!next||!p.alive||(p.role==='enemy'&&$('information').value==='known'))return p;
    return {...p,position:lerp(p.position,next.position,q),yaw:angle(p.yaw,next.yaw,q),pitch:p.pitch+(next.pitch-p.pitch)*q};});
}
function simulatedPlayers(t){
  const plan=clip.plans[selected],route=clip.routes.find(r=>r.id===plan.route_id);
  const result=clip.initial.map(p=>{const action=p.role==='self'?route:effectiveResponse(p,plan);if(!action||!p.alive)return p;
    return {...p,position:along(action.path,t/action.duration),yaw:angle(p.yaw,action.yaw,Math.min(1,t/1.2))};});
  const source=$('enemy-reference').value;
  if(source!=='known'&&clip.spectator){const frame=source==='initial'?clip.spectator[0]:clip.spectator[Math.min(clip.spectator.length-1,Math.floor(t*4))];
    const ids=new Set(result.map(p=>p.player));for(const p of frame.players)if(p.role==='enemy'&&!ids.has(p.player))result.push({...p,reference:true});}
  return result;
}
const labelTextures=new Map();
function typeLabel(text,color){
 let texture=labelTextures.get(text);if(!texture){const canvas=document.createElement('canvas');canvas.width=320;canvas.height=80;const ctx=canvas.getContext('2d');ctx.fillStyle='#15212be6';ctx.fillRect(0,0,320,80);ctx.font='bold 34px Microsoft YaHei';ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(text,160,52);texture=new THREE.CanvasTexture(canvas);labelTextures.set(text,texture);}
 const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false}));sprite.scale.set(1.8,.45,1);sprite.renderOrder=10;return sprite;
}
const utilityKind=kind=>kind.includes('Smoke')||kind.includes('smoke')?'smoke':kind.includes('Flash')||kind.includes('flash')?'flash':kind.includes('Molotov')||kind.includes('inferno')?'fire':'he';
const utilityStyle={smoke:{name:'☁ 烟雾弹',color:0xa8b7c5,css:'#c4d1de'},flash:{name:'✦ 闪光弹',color:0xffffff,css:'#ffffff'},fire:{name:'🔥 燃烧弹',color:0xff8c35,css:'#ffb45c'},he:{name:'● 高爆手雷',color:0xff5555,css:'#ff8585'}};
const shared={body:new THREE.CapsuleGeometry(.16,.34,4,8),head:new THREE.SphereGeometry(.125,10,8),ring:new THREE.TorusGeometry(.30,.024,5,24),cone:new THREE.ConeGeometry(.13,.36,3)};
function makePerson(role){
  const color=role==='self'?0xc6ef86:role==='ally'?0x67bae9:0xef9887;
  const material=new THREE.MeshStandardMaterial({color,roughness:.6,emissive:color,emissiveIntensity:.16});
  const group=new THREE.Group(),body=new THREE.Mesh(shared.body,material);body.position.y=.35;group.add(body);
  const head=new THREE.Mesh(shared.head,material);head.position.y=.68;group.add(head);
  const ring=new THREE.Mesh(shared.ring,new THREE.MeshBasicMaterial({color,depthTest:false}));ring.rotation.x=-Math.PI/2;ring.position.y=.035;ring.renderOrder=4;group.add(ring);
  const arrow=new THREE.Mesh(shared.cone,new THREE.MeshBasicMaterial({color,depthTest:false}));arrow.rotation.z=-Math.PI/2;arrow.position.set(.56,.04,0);arrow.renderOrder=4;group.add(arrow);
  return {group,material,body};
}
class View{
  constructor(id){
    this.element=$(id);this.people=new Map();this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x1a252f);
    this.scene.fog=new THREE.Fog(0x1a252f,65,140);this.camera=new THREE.PerspectiveCamera(47,1,.05,250);
    this.renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));this.renderer.localClippingEnabled=true;
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.setClearColor(0x1a252f);this.element.appendChild(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;this.controls.dampingFactor=.1;this.controls.minDistance=3;this.controls.maxDistance=90;this.controls.maxPolarAngle=Math.PI*.49;
    this.scene.add(new THREE.HemisphereLight(0xcbe4f5,0x53604d,2.6));const sun=new THREE.DirectionalLight(0xffedca,2.0);sun.position.set(-25,60,20);this.scene.add(sun);
    this.cut=new THREE.Plane(new THREE.Vector3(0,-1,0),100);
    const mats=materials.map(m=>{const mat=m.clone();mat.clippingPlanes=[this.cut];return mat;});this.map=new THREE.Mesh(geometry,mats);this.scene.add(this.map);
    this.professional=new THREE.Group();this.scene.add(this.professional);this.effects=new THREE.Group();this.scene.add(this.effects);this.responsePaths=new THREE.Group();this.scene.add(this.responsePaths);this.route=new THREE.Group();this.scene.add(this.route);this.clouds=new THREE.Group();this.scene.add(this.clouds);
    this.risk=new THREE.Group();const riskRing=new THREE.Mesh(new THREE.RingGeometry(.9,1.02,48),new THREE.MeshBasicMaterial({color:0xe3af6f,side:THREE.DoubleSide,transparent:true,opacity:.8,depthTest:false}));riskRing.rotation.x=-Math.PI/2;riskRing.position.y=.08;this.risk.add(riskRing);this.risk.visible=false;this.scene.add(this.risk);
    this.resize=new ResizeObserver(()=>{const w=this.element.clientWidth,h=this.element.clientHeight;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();});this.resize.observe(this.element);
    this.element.querySelector('.loading').remove();
  }
  focus(){const actor=clip.initial.find(p=>p.role==='self'),p=point(actor.position);this.controls.target.copy(p).add(new THREE.Vector3(0,.5,0));this.camera.position.copy(p).add(new THREE.Vector3(8,13,12));this.controls.update();this.cut.constant=p.y+3.8;}
  clear(group){for(const child of [...group.children]){group.remove(child);child.geometry?.dispose();if(Array.isArray(child.material))child.material.forEach(m=>m.dispose());else child.material?.dispose();}}
  setClip(){
    for(const p of this.people.values()){this.scene.remove(p.group);p.material.dispose();}this.people.clear();this.clear(this.clouds);this.clear(this.effects);this.clear(this.responsePaths);this.focus();
    for(const cloud of (this.element.id==='alternative-view'?clip.smokes:[])){
      const count=cloud.voxels.length;if(!count)continue;
      const material=new THREE.MeshBasicMaterial({color:cloud.phase?0xa7b5bd:0xadb8bf,transparent:true,opacity:cloud.phase?.09:.18,depthWrite:false});
      const voxels=new THREE.InstancedMesh(new THREE.SphereGeometry(.15,5,4),material,count),matrix=new THREE.Matrix4();
      cloud.voxels.forEach((p,i)=>{matrix.makeTranslation(...point(p).toArray());voxels.setMatrixAt(i,matrix);});voxels.instanceMatrix.needsUpdate=true;this.clouds.add(voxels);
    }
  }
  showProfessional(){
    this.clear(this.professional);if(this.element.id!=='alternative-view')return;
    for(const ref of clip.professional_paths||[]){for(let i=1;i<ref.samples.length;i++)this.line(this.professional,ref.samples[i-1].position.map((v,j)=>v+(j===2?12:0)),ref.samples[i].position.map((v,j)=>v+(j===2?12:0)),0xc99cff,false);}
  }
  showRoute(path){this.clear(this.route);const points=path.map(p=>point(p).add(new THREE.Vector3(0,.08,0)));
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0xc5ec85,dashSize:.16,gapSize:.12,depthTest:false}));line.computeLineDistances();line.renderOrder=3;this.route.add(line);
    for(const p of [points[0],points.at(-1)]){const mark=new THREE.Mesh(new THREE.RingGeometry(.17,.23,24),new THREE.MeshBasicMaterial({color:0xc5ec85,side:THREE.DoubleSide,depthTest:false}));mark.rotation.x=-Math.PI/2;mark.position.copy(p);mark.renderOrder=4;this.route.add(mark);}
  }
  line(group,a,b,color,dashed=false){
    const mat=dashed?new THREE.LineDashedMaterial({color,dashSize:.15,gapSize:.12,depthTest:false,transparent:true,opacity:.65}):new THREE.LineBasicMaterial({color,depthTest:false});
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints([point(a),point(b)]),mat);if(dashed)line.computeLineDistances();line.renderOrder=5;group.add(line);
  }
  responseRoutes(){
    this.clear(this.responsePaths);
    for(const p of clip.initial.filter(p=>p.alive&&p.role!=='self')){
      const r=effectiveResponse(p,clip.plans[selected]);if(!r)continue;
      for(let i=1;i<r.path.length;i++)this.line(this.responsePaths,r.path[i-1].map((v,j)=>v+(j===2?8:0)),r.path[i].map((v,j)=>v+(j===2?8:0)),0x67bae9,true);
      const dot=new THREE.Mesh(new THREE.SphereGeometry(.16,8,6),new THREE.MeshBasicMaterial({color:0x67bae9,wireframe:true,depthTest:false}));dot.position.copy(point(r.path.at(-1))).add(new THREE.Vector3(0,.3,0));dot.renderOrder=6;this.responsePaths.add(dot);
    }
  }
  drawEffects(players,simulation){
    this.clear(this.effects);
    for(const p of players.filter(p=>p.alive)){
      const yaw=p.yaw*Math.PI/180,pitch=p.pitch*Math.PI/180,a=p.position.map((v,i)=>v+(i===2?64:0));
      this.line(this.effects,a,[a[0]+Math.cos(yaw)*Math.cos(pitch)*220,a[1]+Math.sin(yaw)*Math.cos(pitch)*220,a[2]-Math.sin(pitch)*220],p.role==='enemy'?0xef9887:0x67bae9,true);
    }
    if(simulation)return;
    const known=new Set(players.map(p=>p.player));
    for(const g of clip.grenade_trajectories||[]){
      if($('information').value==='known'&&!known.has(g.player))continue;
      const samples=g.samples.filter(s=>s.time<=time&&time-s.time<2);if(!samples.length||time-samples.at(-1).time>.16)continue;
      const style=utilityStyle[utilityKind(g.kind)],color=style.color;const label=typeLabel(style.name,style.css);label.position.copy(point(samples.at(-1).position)).add(new THREE.Vector3(0,.6,0));label.scale.multiplyScalar(Math.max(1,this.camera.position.distanceTo(label.position)/14));this.effects.add(label);
      const path=new THREE.Line(new THREE.BufferGeometry().setFromPoints(samples.map(s=>point(s.position))),new THREE.LineBasicMaterial({color,depthTest:false}));path.renderOrder=7;this.effects.add(path);
      const ball=new THREE.Mesh(new THREE.SphereGeometry(.10,8,6),new THREE.MeshBasicMaterial({color,depthTest:false}));ball.position.copy(point(samples.at(-1).position));ball.renderOrder=8;this.effects.add(ball);
    }
    for(const e of clip.replay_events||[]){
      if(!['weapon_fire','smokegrenade_detonate','flashbang_detonate','hegrenade_detonate','inferno_startburn'].includes(e.kind))continue;
      const age=time-e.time,life=e.kind==='weapon_fire'?.35:e.duration||(e.kind==='flashbang_detonate'?1.4:1.0);if(age<0||age>life)continue;
      if($('information').value==='known'&&!known.has(e.player))continue;
      if(e.end){this.line(this.effects,e.position,e.end,0xffe59a);continue;}
      const kind=utilityKind(e.kind),style=utilityStyle[kind],position=point(e.position),fade=Math.min(1,(life-age)/1.5);
      const label=typeLabel(style.name+' · '+Math.ceil(life-age)+'s',style.css);label.position.copy(position).add(new THREE.Vector3(0,2.3,0));label.scale.multiplyScalar(Math.max(1,this.camera.position.distanceTo(label.position)/14));this.effects.add(label);
      if(kind==='smoke'){
        const growth=Math.min(1,age/.8);
        for(let j=0;j<12;j++){const a=j*2.399,r=.35+(j%3)*.25;const puff=new THREE.Mesh(new THREE.SphereGeometry(.78*growth,10,8),new THREE.MeshBasicMaterial({color:style.color,transparent:true,opacity:.28*fade,depthWrite:false}));puff.position.copy(position).add(new THREE.Vector3(Math.cos(a)*r,.55+(j%3)*.45,Math.sin(a)*r));this.effects.add(puff);}
      }else if(kind==='fire'){
        for(let j=0;j<13;j++){const a=j*2.399,r=j?Math.sqrt(j/13)*1.1:0,h=.3+.25*(1+Math.sin(age*9+j));const flame=new THREE.Mesh(new THREE.ConeGeometry(.18,h,5),new THREE.MeshBasicMaterial({color:j%2?0xffbf39:0xff6d22,transparent:true,opacity:.8*fade,depthWrite:false}));flame.position.copy(position).add(new THREE.Vector3(Math.cos(a)*r,h/2,Math.sin(a)*r));this.effects.add(flame);}
      }else{
        const burst=new THREE.Mesh(new THREE.SphereGeometry(.15+age*(kind==='flash'?2:1.4),12,8),new THREE.MeshBasicMaterial({color:style.color,transparent:true,opacity:Math.max(0,1-age/life)*.75,depthWrite:false}));burst.position.copy(position);this.effects.add(burst);
      }
    }
  }

  render(players,isSimulation){
    const visible=new Set();let actor;
    for(const p of players){visible.add(p.player);if(p.role==='self')actor=p;let visual=this.people.get(p.player);
      if(!visual){visual=makePerson(p.role);this.people.set(p.player,visual);this.scene.add(visual.group);}
      visual.material.depthTest=!(p.role==='enemy'&&mode==='overview');visual.group.renderOrder=p.role==='enemy'?4:0;visual.material.transparent=!!p.reference;visual.material.opacity=p.reference?.60:1;visual.material.wireframe=!!p.reference;visual.group.visible=true;visual.group.position.copy(point(p.position));visual.group.rotation.y=p.yaw*Math.PI/180;
      visual.group.scale.y=p.duck_amount>.5?.72:1;visual.material.color.setHex(p.alive?(p.role==='self'?0xc6ef86:p.role==='ally'?0x67bae9:0xef9887):0x66717c);
      visual.group.visible=p.alive||p.role==='self';visual.body.rotation.z=p.alive?0:Math.PI/2;
    }
    for(const [id,p] of this.people)p.group.visible&&=visible.has(id);
    this.controls.enabled=mode==='overview';
    if(mode==='pov'&&actor){const position=point(actor.position);position.y+=(64-18*(actor.duck_amount||0))/100;this.camera.position.copy(position);
      const yaw=actor.yaw*Math.PI/180,pitch=actor.pitch*Math.PI/180;this.camera.lookAt(position.clone().add(new THREE.Vector3(Math.cos(yaw)*Math.cos(pitch),-Math.sin(pitch),-Math.sin(yaw)*Math.cos(pitch))));this.cut.constant=100;
      this.people.get(actor.player).group.visible=false;
    }else this.controls.update();
    const unknown=clip.knowledge.alive.enemy-clip.initial.filter(p=>p.role==='enemy'&&p.alive).length;
    this.risk.visible=isSimulation&&branch==='counter'&&unknown>0;
    if(this.risk.visible){const r=clip.routes.find(r=>r.id===clip.plans[selected].route_id);this.risk.position.copy(point(r.path.at(-1)));this.risk.rotation.y=time*.2;}
    this.professional.visible=$('show-professional').checked;this.drawEffects(players,isSimulation);this.renderer.render(this.scene,this.camera);
  }
}
function renderPlans(){
  $('plans').replaceChildren();$('plan-count').textContent=String(clip.plans.length).padStart(2,'0');
  clip.plans.forEach((plan,i)=>{const button=document.createElement('button');button.className='plan-card'+(i===selected?' selected':'');button.setAttribute('aria-pressed',i===selected?'true':'false');
    const top=document.createElement('div');top.className='plan-top';const letter=document.createElement('span');letter.className='plan-letter';letter.textContent=String.fromCharCode(65+i);
    const check=document.createElement('span');check.className='plan-check';const route=clip.routes.find(r=>r.id===plan.route_id);check.textContent=route.check==='stationary'?'原地操作':'路线已粗筛';top.append(letter,check);
    const h=document.createElement('h3');h.textContent=plan.objective||plan.title;const p=document.createElement('p');p.textContent=plan.reason+(plan.objective?' 目标：'+plan.objective+' 执行：'+plan.trigger+' 放弃：'+plan.abort_condition:'');button.append(top,h,p);button.onclick=()=>{selected=i;time=0;updatePlan();};$('plans').append(button);
  });
}
function updatePlan(){
  renderPlans();const plan=clip.plans[selected],route=clip.routes.find(r=>r.id===plan.route_id);$('alternative-title').textContent=plan.objective||plan.title;
  alternativeView.showRoute(route.path);alternativeView.responseRoutes();$('response-detail').textContent=plan.response_notes[branch];
  for(const [id,items] of [['assumptions',plan.assumptions],['risks',plan.risks]]){$(id).replaceChildren(...items.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));}
  $('branch-caption').textContent=branch==='counter'&&!clip.initial.some(p=>p.role==='enemy'&&p.alive)?'未知敌人：黄色圈是路线风险区，不是敌人位置':branchNames[branch]+' · 响应路线均为假设';
}
async function selectClip(id){
  const version=++loadVersion;playing=false;error('');$('agent-status').textContent='正在加载片段…';
  try{const next=await api('/api/clips/'+id);if(version!==loadVersion)return;clip=next;selected=0;time=0;$('timeline').max=clip.duration;branch='continue';
    document.querySelectorAll('.clip').forEach(b=>b.classList.toggle('active',b.dataset.id===id));document.querySelectorAll('[data-branch]').forEach(b=>b.classList.toggle('selected',b.dataset.branch===branch));
    $('match').textContent=clip.title;$('case-meta').textContent='MOUZ vs Spirit · '+clip.side;$('alive').textContent=clip.knowledge.alive.own+' vs '+clip.knowledge.alive.enemy;
    $('known').textContent='已发现敌人 '+clip.initial.filter(p=>p.role==='enemy'&&p.alive).length;$('source').href=clip.source;
    $('plan-source').textContent=clip.plan_source==='ai_hypotheses'?'AI 条件推演 · 待验证':'本地候选 · 非 AI 结论';
    actualView.setClip();alternativeView.setClip();alternativeView.showProfessional();if(mode==='overview')$('fight').click();$('professional-note').textContent=clip.professional_paths?.length?'已匹配 '+clip.professional_paths.length+' 条职业真实后续路线；原始坐标，不代表最优。':'暂无满足当前筛选条件的职业参考路线';updatePlan();$('agent-status').textContent=clip.plan_source==='ai_hypotheses'?'Agent 方案已载入，未经实战效果验证。'+(clip.fact_corrections?.length?' 已依真实人数校正模型笔误。':''):'本地候选已准备。点击生成，让 Agent 分析多方取舍。';
  }catch(e){error(e.message);}
}
const eventNames={weapon_fire:'开火方向（非弹道）',smokegrenade_detonate:'烟雾弹展开',flashbang_detonate:'闪光弹爆炸',hegrenade_detonate:'手雷爆炸',inferno_startburn:'燃烧区域生成'};
let resultKey='';
function updateResults(){
 const key=[clip.id,selected,branch,Math.floor(time*10),$('information').value,$('enemy-reference').value].join(':');if(key===resultKey)return;resultKey=key;
 const now=simulatedPlayers(time),self=now.find(p=>p.role==='self');let movers=0;
 $('response-actors').replaceChildren(...now.filter(p=>p.alive&&p.role!=='self').map(p=>{
   const original=clip.initial.find(x=>x.player===p.player)||clip.spectator[0].players.find(x=>x.player===p.player),distance=Math.hypot(...p.position.map((v,i)=>v-original.position[i])),r=effectiveResponse(p,clip.plans[selected]);if(distance>1)movers++;
   const near=Math.hypot(...p.position.map((v,i)=>v-self.position[i]));const li=document.createElement('li');li.textContent=(p.role==='ally'?'队友 ':p.reference?'敌方参照 ':'敌人 ')+p.player.slice(0,4)+' · '+(p.reference?($('enemy-reference').value==='replay'?'沿用真实回放（非反制预测）':'起始站位保持'):r?.id.startsWith('support')?'靠拢支援':r?.id==='continue'?'延续移动':r?.id==='counter'?'换位反制':'保持站位')+' · 已移动 '+distance.toFixed(0)+' 单位 · 距你 '+near.toFixed(0)+' 单位';return li;
 }));
 $('response-result').textContent='推演至 '+time.toFixed(1)+' 秒：'+movers+' 人发生位移。'+(time>6?'自身首步动作已结束，尚未重新决策。':'')+'蓝色虚线与空心球标出响应路线及终点；不等于已形成补枪或完成击杀。';
 const events=(clip.replay_events||[]).filter(e=>eventNames[e.kind]&&e.time<=time&&time-e.time<(e.duration||1.3)&&($('information').value==='spectator'||actualPlayers(time).some(p=>p.player===e.player)));
 $('event-detail').textContent=events.map(e=>(e.time>=0?'+':'')+e.time.toFixed(1)+' 秒 '+(eventNames[e.kind]||e.kind)+(e.duration?' · 剩余约 '+Math.max(0,e.duration-(time-e.time)).toFixed(1)+' 秒':'')).join('；')||'当前时刻没有可展示的新事件。';
}
let last=performance.now();function animate(now){const dt=Math.min(.1,(now-last)/1000);last=now;
  if(clip){if(playing){time+=dt*Number($('speed').value);if(time>=clip.duration){time=clip.duration;playing=false;}}
    actualView.render(actualPlayers(time),false);alternativeView.render(simulatedPlayers(time),true);
    updateResults();$('timeline').value=time;$('time').replaceChildren(document.createTextNode(time.toFixed(1).padStart(4,'0')+' '),Object.assign(document.createElement('span'),{textContent:'/ '+clip.duration.toFixed(1)}));$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'暂停':'播放');
    $('branch-caption').textContent=$('enemy-reference').value==='replay'?'敌方沿用真实回放作对照，未响应你的替代行动':$('enemy-reference').value==='initial'?'敌方按真实起始站位保持，是全知条件假设':'仅已知敌人参与动作推演';const actor=actualPlayers(time).find(p=>p.role==='self');$('actual-caption').textContent=actor?.alive?'真实操作 · +'+time.toFixed(1)+' 秒':'真实记录：玩家已阵亡 · +'+time.toFixed(1)+' 秒';
  }requestAnimationFrame(animate);
}
$('fight').onclick=()=>{mode='overview';const players=(clip.spectator?.[0]?.players||clip.initial).filter(p=>p.alive);const box=new THREE.Box3().setFromPoints(players.map(p=>point(p.position))),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());const d=Math.max(8,size.x,size.z)*1.1;for(const v of [actualView,alternativeView]){v.controls.target.copy(center);v.camera.position.copy(center).add(new THREE.Vector3(d*.4,d,d*.8));v.controls.update();}};
$('play').onclick=()=>{if(time>=clip.duration)time=0;playing=!playing;};$('reset').onclick=()=>{time=0;playing=false;};$('timeline').oninput=e=>{time=Number(e.target.value);playing=false;};
$('overview').onclick=()=>{mode='overview';$('overview').classList.add('selected');$('pov').classList.remove('selected');actualView.focus();alternativeView.focus();};
$('pov').onclick=()=>{mode='pov';$('pov').classList.add('selected');$('overview').classList.remove('selected');};$('focus').onclick=()=>{$('overview').click();};
document.querySelectorAll('[data-branch]').forEach(b=>b.onclick=()=>{branch=b.dataset.branch;document.querySelectorAll('[data-branch]').forEach(x=>x.classList.toggle('selected',x===b));if(clip)updatePlan();});
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName)){e.preventDefault();$('play').click();}});
$('generate').onclick=async()=>{
  if(!clip||busy)return;busy=true;$('generate').disabled=true;const id=clip.id;error('');
  try{await api('/api/generate',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify({case_id:id,use_configured_model:true})});
    $('agent-status').textContent='Agent 正在推演，请稍候…';
    while(true){await new Promise(r=>setTimeout(r,1500));const job=await api('/api/jobs/'+id);if(job.status==='done'){if(clip.id===id)await selectClip(id);break;}if(job.status==='error')throw Error(job.message);if(clip.id===id)$('agent-status').textContent=job.message;}
  }catch(e){error(e.message);$('agent-status').textContent='生成未完成，仍可比较本地候选。';}finally{busy=false;$('generate').disabled=false;}
};
async function boot(){
  try{
    const [status,clips,meta,response]=await Promise.all([api('/api/status'),api('/api/clips'),api('/assets/map.json'),fetch('/assets/map.bin')]);token=status.token;mapInfo=meta;
    const buffer=await response.arrayBuffer(),header=new Uint32Array(buffer,0,2),vertices=new Float32Array(buffer,8,header[0]*3),indices=new Uint32Array(buffer,8+header[0]*12,header[1]);
    geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(vertices,3));geometry.setIndex(new THREE.BufferAttribute(indices,1));geometry.computeVertexNormals();
    materials=meta.groups.map((g,i)=>{geometry.addGroup(g.start,g.count,i);const color=/wood/.test(g.material)?0x776f58:/metal/.test(g.material)?0x667681:/dirt|sand/.test(g.material)?0x827d64:/glass/.test(g.material)?0x718d97:0x7c8590;return new THREE.MeshStandardMaterial({color,roughness:1,side:THREE.DoubleSide});});
    actualView=new View('actual-view');alternativeView=new View('alternative-view');
    $('clip-count').textContent=clips.length;$('clips').replaceChildren(...clips.map((c,i)=>{const button=document.createElement('button');button.className='clip';button.dataset.id=c.id;const icon=document.createElement('span');icon.className='clip-icon';icon.textContent='◈';const text=document.createElement('span'),h=document.createElement('strong'),small=document.createElement('small');h.textContent=c.title+(c.id.includes('-3233-')?' · 道具交战':'');small.textContent=c.side+' · '+c.own_alive+'v'+c.enemy_alive+' · '+(c.duration||6)+' 秒';text.append(h,small);button.append(icon,text);button.onclick=()=>selectClip(c.id);return button;}));
    $('generate').disabled=!status.ai.configured;$('model-note').textContent=status.ai.configured?'使用 '+status.ai.host+' · 每次最多 5 次模型调用':'请先在项目 .env 中配置模型';
    await selectClip((clips.find(c=>c.title.includes('长残局'))||clips[0]).id);requestAnimationFrame(animate);
  }catch(e){error('3D 工作区加载失败：'+e.message);document.querySelectorAll('.loading').forEach(x=>x.textContent='无法载入地图。请检查本地服务或 WebGL 支持。');}
}
boot();
