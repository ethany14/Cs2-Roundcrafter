import * as T from '/vendor/three.module.js';
import {OrbitControls} from '/vendor/OrbitControls.js';
const modeLabels={stand_left:t('站立投掷'),jump_left:t('原地跳投'),w_jump_left:t('W 点按跳投'),crouch_jump_left:t('蹲稳跳投'),run_jump_left:t('助跑跳投')};
const $=id=>document.getElementById(id),v=p=>new T.Vector3(p[0]/100,p[2]/100,-p[1]/100),game=p=>[p.x*100,-p.z*100,p.y*100];
const scene=new T.Scene();scene.background=new T.Color('#090a0c');scene.add(new T.HemisphereLight(0xc4e2ff,0x334455,2));
const light=new T.DirectionalLight(0xffffff,2);light.position.set(20,70,20);scene.add(light);
const renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.localClippingEnabled=true;$('viewport').append(renderer.domElement);
const perspective=new T.PerspectiveCamera(60,1,.1,2000),ortho=new T.OrthographicCamera(-40,40,40,-40,.1,2000);
let camera=ortho,controls,mesh,edges,bounds,radar,radarMeta,radarBounds,radarUpper,radarLower,token='',pick='origin',points={origin:null,target:null},history=[],job='',result=null,pollTimer,loadVersion=0,currentCandidate=null;
const overlay=new T.Group();scene.add(overlay);const plane=new T.Plane(new T.Vector3(0,-1,0),1000),ray=new T.Raycaster();
function status(s){$('status').textContent=s}
async function api(url,body){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(t(d.error)||t('请求失败'));return d}
function setControls(){const previousTarget=controls?.target.clone();controls?.dispose();controls=new OrbitControls(camera,renderer.domElement);if(previousTarget)controls.target.copy(previousTarget);controls.enableRotate=camera===perspective;controls.screenSpacePanning=true;controls.enableDamping=true;controls.mouseButtons.LEFT=camera===perspective?T.MOUSE.ROTATE:(pick?null:T.MOUSE.PAN);controls.mouseButtons.RIGHT=T.MOUSE.PAN;}
function activeBounds(){return camera===ortho&&radarBounds?radarBounds:bounds}
function resize(){const w=$('viewport').clientWidth,h=$('viewport').clientHeight;renderer.setSize(w,h);perspective.aspect=w/h;perspective.updateProjectionMatrix();if(bounds){const bb=radarBounds||bounds;const half=Math.max((bb.max.x-bb.min.x)*h/w,bb.max.z-bb.min.z)/2+1;ortho.left=-half*w/h;ortho.right=half*w/h;ortho.top=half;ortho.bottom=-half;ortho.updateProjectionMatrix()}}
new ResizeObserver(resize).observe($('viewport'));setControls();renderer.setAnimationLoop(()=>{controls.update();
  // keep point markers a small constant on-screen size up close (aim view stands right next to them)
  for(const o of overlay.children)if(o.geometry?.type==='SphereGeometry')o.scale.setScalar(camera===perspective?Math.min(1,o.position.distanceTo(camera.position)*.02):1);
  renderer.render(scene,camera)});
function reset(){$('crosshair').hidden=true;if(!bounds)return;const bb=activeBounds(),c=bb.getCenter(new T.Vector3()),span=Math.max(bb.max.x-bb.min.x,bb.max.z-bb.min.z);controls.target.copy(c);camera.zoom=1;camera.up.set(0,1,0);if(camera===ortho){camera.up.set(0,0,-1);camera.position.set(c.x,bounds.max.y+span,c.z)}else camera.position.copy(c).add(new T.Vector3(span*.4,span*.55,span*.4));camera.updateProjectionMatrix();controls.update()}
function view(is3){camera=is3?perspective:ortho;renderer.domElement.style.display=is3?'':'none';c2.style.display=is3?'none':'';if(mesh)mesh.visible=is3;if(edges)edges.visible=is3;if(radar)radar.visible=!is3;setControls();$('view2').setAttribute('aria-pressed',!is3);$('view3').setAttribute('aria-pressed',is3);resize();reset();updateHint();if(!is3){fit2()}}
function clearOverlay(){overlay.traverse(o=>{o.geometry?.dispose();o.material?.dispose()});overlay.clear()}
function dot(p,color,size=.45){const m=new T.Mesh(new T.SphereGeometry(size,12,8),new T.MeshBasicMaterial({color,depthTest:false}));m.position.copy(v(p));m.renderOrder=10;overlay.add(m)}
function line(ps,color){const l=new T.Line(new T.BufferGeometry().setFromPoints(ps.map(v)),new T.LineBasicMaterial({color,depthTest:false}));l.renderOrder=9;overlay.add(l)}
function draw(){draw2d();clearOverlay();if(points.origin)dot(points.origin,0x82d68f);if(points.target){dot(points.target,0x69baff);const ring=new T.Mesh(new T.RingGeometry(Number($('radius').value)/100-.02,Number($('radius').value)/100+.02,64),new T.MeshBasicMaterial({color:0x69baff,side:T.DoubleSide,depthTest:false}));ring.rotation.x=-Math.PI/2;ring.position.copy(v(points.target));overlay.add(ring)}if(!currentCandidate&&result?.diagnostic_trajectory)line(result.diagnostic_trajectory,0xe58b73);if(currentCandidate){const c=currentCandidate,n=Math.max(2,Math.ceil(c.trajectory.length*Number($('timeline').value)/100));line(c.trajectory.slice(0,n),0xffd17b);dot(c.trajectory[Math.min(n-1,c.trajectory.length-1)],0xffd17b,.2);if(c.launch_assumptions?.ground_path?.length>1){line(c.launch_assumptions.ground_path,0xffa34d);dot(c.launch_assumptions.jump_point,0xffa34d,.6)}const aim=c.aim_point||c.aim_direction_point;dot(aim,0xfa8fbb,.35);line([[c.position[0],c.position[1],c.position[2]+(c.aim_eye_height||64)],aim],0xfa8fbb)}}
function sync(){for(const k of ['origin','target'])$(k).value=points[k]?.map(x=>x.toFixed(2)).join(', ')||'';$('solve').disabled=!points.origin||!points.target||!!job;draw()}
function invalidate(){$('modeSummary').textContent='';result=null;currentCandidate=null;$('candidate').replaceChildren(new Option(t('等待计算'),''));$('command').value='';$('copy').disabled=true;$('aim').disabled=true;$('detail').textContent=t('选点已更新，请重新计算。');$('aimNote').textContent=''}
function saveHistory(){history.push(structuredClone(points));if(history.length>50)history.shift()}
function updateHint(){const action=pick==='origin'?t('单击地面放置站位'):pick==='target'?t('单击地面放置落点'):t('浏览地图');$('hint').textContent=is2d()?t('{0}；拖动平移，滚轮缩放。',[action]):camera===perspective?t('{0}；左键拖动旋转，右键拖动平移，滚轮缩放。',[action]):t('{0}；右键拖动平移，滚轮缩放。',[action])}
function setPick(k){pick=k;setControls();for(const [id,key] of [['pickOrigin','origin'],['pickTarget','target'],['navigate',null]])$(id).setAttribute('aria-pressed',k===key);updateHint()}
// A drag rotates the camera but must never become a placement click on release.
let pointerGesture=null;
renderer.domElement.addEventListener('pointerdown',e=>{pointerGesture={id:e.pointerId,x:e.clientX,y:e.clientY,moved:false,button:e.button}},true);
renderer.domElement.addEventListener('pointermove',e=>{if(pointerGesture?.id===e.pointerId&&Math.hypot(e.clientX-pointerGesture.x,e.clientY-pointerGesture.y)>5)pointerGesture.moved=true},true);
renderer.domElement.addEventListener('pointercancel',()=>{pointerGesture=null},true);
let surfaceRows=[],surfaceKey=null,pickingVersion=0;
renderer.domElement.addEventListener('click',async e=>{
 const gesture=pointerGesture;pointerGesture=null;
 if(!gesture||gesture.moved||gesture.button!==0||e.button!==0||e.ctrlKey||e.shiftKey||e.metaKey||!pick||!mesh||job)return;
 const rect=renderer.domElement.getBoundingClientRect();ray.setFromCamera(new T.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
 const hit=camera===ortho?ray.intersectObject(radar)[0]:ray.intersectObject(mesh).find(h=>h.point.y<=plane.constant+.001&&h.face.normal.y>.7);
 if(!hit){status(t('此处没有地图表面，请调整视角。'));return}
 await placeAt(game(hit.point));
});
async function placeAt(p){
 if(!pick||!mesh||job)return;const version=++pickingVersion,key=pick,map=$('map').value;status(t('正在检查选点处的地面与站立空间…'));
 try{
  const lower=radarMeta.floor_split_z!==null&&Number($('cut').value)<=radarMeta.floor_split_z;
  const d=await api('/api/lab/surface',{map,x:p[0],y:p[1],ceiling:Number($('cut').value),floor:lower?bounds.min.y*100:radarMeta.floor_split_z??bounds.min.y*100});
  if(version!==pickingVersion||map!==$('map').value||job)return;
  surfaceRows=d.surfaces.filter(s=>key==='target'||s.standable);surfaceKey=key;
  $('surface').replaceChildren();surfaceRows.forEach((s,i)=>$('surface').append(new Option(`Z ${s.position[2].toFixed(1)} · ${s.standable?t('可站立'):t('仅落点表面')}`,i)));
  if(!surfaceRows.length){saveHistory();points[key]=null;invalidate();sync();$('surface').append(new Option(t('没有可用地面'),''));status(t('此处未找到可用地面，请避开墙边或切换楼层。'));return}
  let index=camera===perspective&&!is2d()?surfaceRows.reduce((best,s,i)=>Math.abs(s.position[2]-p[2])<Math.abs(surfaceRows[best].position[2]-p[2])?i:best,0):0;
  $('surface').value=index;saveHistory();points[key]=surfaceRows[index].position;invalidate();sync();
  status((key==='origin'?t('站位'):t('落点'))+t('已设置')+(surfaceRows.length>1?t('；此处有多层，请核对“选点表面 / 高度”。'):t('；已核对静态地面。')));
  if(key==='origin')setPick('target');
 }catch(e){status(e.message)}
}

/* ---- 2D view: the same canvas radar renderer as the demo review (monochrome radar, pan/zoom, click to place) ---- */
const c2=document.createElement('canvas');c2.className='lab2d';$('viewport').append(c2);
let v2=[0,0,1024],drag2=null,img2={};
function is2d(){return camera===ortho}
function px2(p){return [(p[0]-radarMeta.pos_x)/radarMeta.scale,(radarMeta.pos_y-p[1])/radarMeta.scale]}
function g2(){const d=devicePixelRatio||1,W=c2.clientWidth,H=c2.clientHeight;if(c2.width!==Math.round(W*d)||c2.height!==Math.round(H*d)){c2.width=Math.round(W*d);c2.height=Math.round(H*d)}const s=Math.min(W,H)/v2[2];return {d,W,H,s,ox:(W-v2[2]*s)/2-v2[0]*s,oy:(H-v2[2]*s)/2-v2[1]*s}}
function fit2(){if(!radarMeta)return;const [l,tp,r,b]=radarMeta.content_bounds.map(x=>x*1024);const size=Math.max(r-l,b-tp)*1.04;v2=[(l+r-size)/2,(tp+b-size)/2,size];draw2d()}
function lowerActive(){return radarMeta?.lower_url&&radarMeta.floor_split_z!==null&&Number($('cut').value)<=radarMeta.floor_split_z}
function draw2d(){if(!is2d()||!radarMeta)return;const ctx=c2.getContext('2d'),g=g2();ctx.setTransform(g.d,0,0,g.d,0,0);ctx.fillStyle='#090a0c';ctx.fillRect(0,0,g.W,g.H);
 ctx.setTransform(g.d*g.s,0,0,g.d*g.s,g.d*g.ox,g.d*g.oy);const k=1/g.s,S=radarMeta.scale,im=lowerActive()?img2.lower:img2.upper;
 if(im?.complete&&im.naturalWidth){ctx.filter='grayscale(1) sepia(.15) brightness(.55) contrast(.95)';ctx.drawImage(im,0,0,1024,1024);ctx.filter='none'}
 const poly=(pts,col,w,dash)=>{if(!pts?.length)return;ctx.beginPath();pts.forEach((q,i)=>{const [u,v]=px2(q);i?ctx.lineTo(u,v):ctx.moveTo(u,v)});ctx.strokeStyle=col;ctx.lineWidth=w*k;ctx.setLineDash(dash?[5*k,4*k]:[]);ctx.stroke();ctx.setLineDash([])};
 const dotc=(p,col,r,ring)=>{const [u,v]=px2(p);ctx.beginPath();ctx.arc(u,v,r*k,0,6.283);ctx.fillStyle=col;ctx.fill();ctx.strokeStyle=ring||'#0a0b0d';ctx.lineWidth=1.6*k;ctx.stroke()};
 if(!currentCandidate&&result?.diagnostic_trajectory)poly(result.diagnostic_trajectory,'#e58b73',1.6,true);
 if(currentCandidate){const c=currentCandidate,n=Math.max(2,Math.ceil(c.trajectory.length*Number($('timeline').value)/100));
  if(c.launch_assumptions?.ground_path?.length>1){poly(c.launch_assumptions.ground_path,'#ffa34d',2);dotc(c.launch_assumptions.jump_point,'#ffa34d',4.5)}
  poly(c.trajectory.slice(0,n),'#ffd17b',2.2);dotc(c.trajectory[Math.min(n-1,c.trajectory.length-1)],'#ffd17b',3.2);
  const aim=c.aim_point||c.aim_direction_point;poly([c.position,aim],'#fa8fbb',1.4,true);dotc(aim,'#fa8fbb',3.5)}
 if(points.target){const [u,v]=px2(points.target);ctx.beginPath();ctx.arc(u,v,Number($('radius').value)/S,0,6.283);ctx.fillStyle='rgba(105,186,255,.12)';ctx.fill();ctx.strokeStyle='#69baff';ctx.lineWidth=1.5*k;ctx.stroke();dotc(points.target,'#69baff',5.5)}
 if(points.origin)dotc(points.origin,'#82d68f',6,'#0a0b0d');
}
function at2(e){const r=c2.getBoundingClientRect(),g=g2();return [(e.clientX-r.left-g.ox)/g.s,(e.clientY-r.top-g.oy)/g.s]}
c2.addEventListener('wheel',e=>{e.preventDefault();const [u,v]=at2(e),f=e.deltaY>0?1.15:.87,size=Math.min(1600,Math.max(80,v2[2]*f)),q=size/v2[2];v2=[u-(u-v2[0])*q,v-(v-v2[1])*q,size];draw2d()},{passive:false});
c2.onpointerdown=e=>{drag2={x:e.clientX,y:e.clientY,v:[...v2],moved:false};c2.setPointerCapture(e.pointerId)};
c2.onpointermove=e=>{if(!drag2)return;const g=g2(),dx=(e.clientX-drag2.x)/g.s,dy=(e.clientY-drag2.y)/g.s;if(Math.abs(e.clientX-drag2.x)+Math.abs(e.clientY-drag2.y)>4)drag2.moved=true;if(drag2.moved){v2=[drag2.v[0]-dx,drag2.v[1]-dy,v2[2]];draw2d()}};
c2.onpointerup=async e=>{const d=drag2;drag2=null;if(!d||d.moved||e.button!==0||!pick)return;const [u,v]=at2(e);await placeAt([u*radarMeta.scale+radarMeta.pos_x,radarMeta.pos_y-v*radarMeta.scale,0])};
new ResizeObserver(()=>draw2d()).observe($('viewport'));
$('surface').onchange=()=>{if(job||!surfaceKey||!surfaceRows[$('surface').value])return;saveHistory();points[surfaceKey]=surfaceRows[$('surface').value].position;invalidate();sync();status(t('已切换选点高度，请在 3D 中核对。'))};

// Match the review maps: monochrome, slightly warm radar so the coloured markers carry the meaning.
function mono(tex){const img=tex.image,c=document.createElement('canvas');c.width=img.width;c.height=img.height;const ctx=c.getContext('2d');ctx.filter='grayscale(1) sepia(.18) brightness(.62) contrast(.95)';ctx.drawImage(img,0,0);tex.dispose();const out=new T.CanvasTexture(c);out.colorSpace=T.SRGBColorSpace;return out}
async function loadMap(){const version=++loadVersion;$('solve').disabled=true;status(t('正在加载地图碰撞几何…'));const name=$('map').value;const meta=await api('/api/lab/radar/'+name);const loader=new T.TextureLoader();const upper=mono(await loader.loadAsync(meta.upper_url));const lower=meta.lower_url?mono(await loader.loadAsync(meta.lower_url)):null;const response=await fetch('/lab-maps/'+name+'.bin');if(!response.ok)throw Error(t('地图加载失败'));const buf=await response.arrayBuffer();if(version!==loadVersion){upper.dispose();lower?.dispose();return}radarMeta=meta;if(radar){scene.remove(radar);radar.geometry.dispose();radar.material.dispose();radarUpper.dispose();radarLower?.dispose()}radarUpper=upper;radarLower=lower;const span=meta.scale*1024;radar=new T.Mesh(new T.PlaneGeometry(span/100,span/100),new T.MeshBasicMaterial({map:upper,alphaTest:.05,depthTest:false,depthWrite:false}));radar.rotation.x=-Math.PI/2;radar.position.set((meta.pos_x+span/2)/100,0,(-meta.pos_y+span/2)/100);radar.renderOrder=-10;radar.visible=false;scene.add(radar);img2={};for(const [k2,u2] of [['upper',meta.upper_url],['lower',meta.lower_url]])if(u2){const im=new Image();im.onload=draw2d;im.src=u2;img2[k2]=im}const cb=meta.content_bounds;const inset={left:cb[0],top:cb[1],right:1-cb[2],bottom:1-cb[3]};radarBounds=new T.Box3(new T.Vector3((meta.pos_x+span*inset.left)/100,0,(-meta.pos_y+span*inset.top)/100),new T.Vector3((meta.pos_x+span*(1-inset.right))/100,0,(-meta.pos_y+span*(1-inset.bottom))/100));const f=new Float32Array(buf);for(let i=0;i<f.length;i+=3){const y=f[i+1];f[i]/=100;f[i+1]=f[i+2]/100;f[i+2]=-y/100}if(mesh){scene.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();scene.remove(edges);edges.geometry.dispose();edges.material.dispose()}const g=new T.BufferGeometry();g.setAttribute('position',new T.BufferAttribute(f,3));g.computeVertexNormals();g.computeBoundingBox();bounds=g.boundingBox;mesh=new T.Mesh(g,new T.MeshLambertMaterial({color:0x8d877b,side:T.DoubleSide,clippingPlanes:[plane]}));scene.add(mesh);edges=new T.LineSegments(new T.EdgesGeometry(g,25),new T.LineBasicMaterial({color:0x2d2a25,clippingPlanes:[plane]}));scene.add(edges);mesh.visible=camera===perspective;edges.visible=camera===perspective;$('cut').min=Math.floor(bounds.min.y*100);$('cut').max=Math.ceil(bounds.max.y*100)+10;$('cut').value=$('cut').max;$('floor').value='all';if(name==='de_nuke'){$('floor').value='upper';$('cut').value=80}cut();resize();reset();sync();if(is2d()){renderer.domElement.style.display='none';fit2()}status(t('游戏雷达图已就绪。XY 使用官方标定，高度由碰撞地面确定。'))}
function cut(){plane.constant=Number($('cut').value)/100;if(radar){const lower=radarLower&&radarMeta.floor_split_z!==null&&Number($('cut').value)<=radarMeta.floor_split_z;radar.material.map=lower?radarLower:radarUpper;radar.material.needsUpdate=true}$('cutValue').textContent=$('cut').value+t(' 单位');draw2d()}
$('cut').oninput=()=>{$('floor').value='custom';cut()};$('floor').onchange=()=>{const mode=$('floor').value;if(mode==='custom')return;const isNuke=$('map').value==='de_nuke';$('cut').value=mode==='all'?$('cut').max:isNuke?(mode==='upper'?80:radarMeta.floor_split_z):(mode==='upper'?Number($('cut').max)*.75:(Number($('cut').min)+Number($('cut').max))/2);cut()};
$('view2').onclick=()=>view(false);$('view3').onclick=()=>view(true);$('reset').onclick=()=>{reset();if(is2d())fit2()};$('pickOrigin').onclick=()=>setPick('origin');$('pickTarget').onclick=()=>setPick('target');$('navigate').onclick=()=>setPick(null);
$('map').onchange=async()=>{if(job)return;pickingVersion++;surfaceRows=[];$('surface').replaceChildren(new Option(t('点击地图后选择实际地面'),''));points={origin:null,target:null};history=[];invalidate();try{await loadMap()}catch(e){status(e.message)}};
$('undo').onclick=()=>{if(job)return;if(history.length){points=history.pop();invalidate();sync()}};
$('apply').onclick=()=>{if(job)return;try{const next={};for(const k of ['origin','target']){next[k]=$(k).value.split(/[,，\s]+/).filter(Boolean).map(Number);if(next[k].length!==3||next[k].some(n=>!Number.isFinite(n)||Math.abs(n)>30000))throw Error(t('请填写三个有效坐标，以逗号分隔'))}saveHistory();points=next;invalidate();sync();status(t('坐标已应用。'))}catch(e){status(e.message)}};
function busy(value){$('map').disabled=value;$('mode').disabled=value;$('runDistance').disabled=value;$('apply').disabled=value;$('undo').disabled=value;$('load').disabled=value;$('cancel').disabled=!value;$('solve').disabled=value||!points.origin||!points.target}
const names={experimental_candidates:t('已计算出实验候选 · 未实投'),no_solution_in_bounded_search:t('有限搜索内未找到命中投法'),budget_exhausted:t('计算预算已耗尽 · 暂无命中'),cancelled:t('实验已取消'),jump_blocked:t('头顶空间不足，无法原地跳投'),invalid_origin:t('站位无法站立'),failed:t('计算失败')};
$('runDistance').onchange=()=>{if(!job){invalidate();sync()}};
$('mode').onchange=()=>{if(!job){invalidate();sync()}};
function choose(){currentCandidate=result?.candidates[Number($('candidate').value)]||null;$('aim').disabled=!currentCandidate;$('copy').disabled=!currentCandidate;$('command').value=currentCandidate?.practice_command||'';if(currentCandidate){const c=currentCandidate;$('detail').textContent=t('{0} · 俯仰 {1}° · 朝向 {2}° · 落点误差 {3} 单位 · 飞行 {4} 秒 · {5} 次较强反弹',[modeLabels[c.mode]||c.mode,c.pitch.toFixed(2),c.yaw.toFixed(2),c.distance.toFixed(1),c.flight_seconds.toFixed(2),c.bounces]);$('aimNote').textContent=c.aim_point?t('粉色点：视线与静态几何的交点，可进入瞄准视角检查。'):t('视线没有撞上几何：这是朝向天空的角度，没有可指认的墙面瞄点。')}if(result?.mode_decision)$('detail').textContent=t(result.mode_decision.message)+' '+$('detail').textContent;if(currentCandidate?.execution_steps)$('detail').textContent+=t(' 步骤：')+currentCandidate.execution_steps.map(x=>t(x)).join(' → ');draw()}
const difficultyRank={stand_left:1,jump_left:2,crouch_jump_left:3,w_jump_left:4,run_jump_left:5};
function renderCandidates(preserve=false){
 const old=preserve?$('candidate').value:null;
 const rows=(result?.candidates||[]).map((c,i)=>({c,i}));
 const rank=c=>c.difficulty_rank||difficultyRank[c.mode]||9;
 rows.sort((a,b)=>$('sortCandidates').value==='error'?(a.c.distance-b.c.distance||rank(a.c)-rank(b.c)):(rank(a.c)-rank(b.c)||a.c.distance-b.c.distance));
 $('candidate').replaceChildren();
 for(const {c,i} of rows)$('candidate').append(new Option(t('{0} · 难度 {1}/5 · 误差 {2}',[modeLabels[c.mode]||c.mode,rank(c),c.distance.toFixed(1)]),i));
 if(preserve&&rows.some(r=>String(r.i)===old))$('candidate').value=old;
 const state={experimental_candidates:t('有候选'),budget_exhausted:t('分配预算耗尽'),no_solution_in_bounded_search:t('本轮未命中'),not_started:t('未计算'),invalid_origin:t('站位不可用'),jump_blocked:t('起跳空间不足'),cancelled:t('已取消')};
 $('modeSummary').textContent=(result?.mode_checks||[]).map(x=>t('{0}：{1}{2}{3}（{4} 次）',[t(x.label)||modeLabels[x.mode],state[x.status]||x.status,x.candidate_count!==undefined?' '+x.candidate_count+t(' 个候选'):'',x.stop_reason==='budget_exhausted'?t('，阶段预算已用尽'):'',x.simulations])).join(t('；'));
}
$('sortCandidates').onchange=()=>{if(result?.candidates?.length){renderCandidates(true);choose()}};
async function poll(){try{const d=await api('/api/lab/job?id='+job);status((names[d.status]||(t('正在检查')+(modeLabels[d.searching_mode||d.request?.mode]||t('站立投掷'))))+t(' · {0}/{1} 次模拟',[d.simulations||0,d.request?.max_simulations||180])+(d.nearest?t(' · 最近误差 {0}',[d.nearest.distance.toFixed(1)]):''));if(d.status==='running'){pollTimer=setTimeout(poll,1000);return}result=d;job='';busy(false);renderCandidates();if(!d.candidates.length){$('candidate').append(new Option(t('未找到候选'),''));$('detail').textContent=t(d.reason)||t('可尝试调整站位、落点、容差或时限；有限搜索不是无解证明。')}choose();if(d.diagnostics){const x=d.diagnostics;$('detail').textContent+=t('。水平距离 {0}，站立投掷理想直达参考约 {1} 单位（非实投结论）。',[x.horizontal_distance,x.ideal_unobstructed_range]) }if(!d.candidates.length&&d.diagnostic_trajectory)$('aimNote').textContent=t('橙红线为最接近的失败轨迹，未命中目标，不提供练习指令。')}catch(e){status(e.message);pollTimer=setTimeout(poll,2500)}}
$('solve').onclick=async()=>{invalidate();busy(true);try{const d=await api('/api/lab/start',{map:$('map').value,...points,radius:Number($('radius').value),seconds:Number($('seconds').value),max_simulations:$('mode').value==='auto'?180:400,mode:$('mode').value,run_distance:Number($('runDistance').value)});job=d.id;window.history.replaceState(null,'','/lab?run='+job);localStorage.setItem('cs2-free-lab-run',job);status(t('开始本地物理计算…'));poll()}catch(e){job='';busy(false);status(e.message)}};
$('cancel').onclick=async()=>{try{await api('/api/lab/cancel',{id:job});status(t('正在取消；当前单条轨迹结束后停止。'));$('cancel').disabled=true}catch(e){status(e.message)}};
$('candidate').onchange=choose;$('timeline').oninput=draw;$('radius').oninput=()=>{if(!job){invalidate();draw()}};
$('aim').onclick=()=>{const c=currentCandidate;if(!c)return;view(true);$('crosshair').hidden=false;$('cut').value=$('cut').max;$('floor').value='all';cut();camera.position.copy(v([c.position[0],c.position[1],c.position[2]+(c.aim_eye_height||64)]));controls.target.copy(v(c.aim_point||c.aim_direction_point));controls.update();$('hint').textContent=t('当前为实验站位的瞄准视角。粉色为瞄准方向；点击复位返回全图。')};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('command').value);status(t('已复制实验定位指令。'))}catch{$('command').select();status(t('请手动复制选中的指令。'))}};
function layouts(){try{return JSON.parse(localStorage.getItem('cs2-free-lab-layouts')||'[]')}catch{return []}}
function listSaved(){const rows=layouts();$('saved').replaceChildren(new Option(t('选择本机保存的布局'),''));rows.forEach((r,i)=>$('saved').append(new Option(r.name,i)))}
$('save').onclick=()=>{if(!points.origin||!points.target){status(t('先设置两个点再保存。'));return}const rows=layouts();rows.push({name:$('name').value.trim()||t('实验 ')+new Date().toLocaleString(),map:$('map').value,points:structuredClone(points),mode:$('mode').value,runDistance:Number($('runDistance').value),radius:Number($('radius').value),cut:Number($('cut').value)});localStorage.setItem('cs2-free-lab-layouts',JSON.stringify(rows));listSaved();status(t('布局已保存到当前浏览器。'))};
$('load').onclick=async()=>{if(job||$('saved').value==='')return;const row=layouts()[Number($('saved').value)];if(!row)return;try{$('map').value=row.map;await loadMap();points=row.points;$('mode').value=row.mode||'auto';$('runDistance').value=row.runDistance||128;$('radius').value=row.radius;$('name').value=row.name;$('cut').value=row.cut;cut();invalidate();sync();status(t('已读取布局；重新计算以生成候选。'))}catch(e){status(e.message)}};
try{const [s,d]=await Promise.all([api('/api/status'),api('/api/lab/maps')]);token=s.token;d.maps.forEach(m=>$('map').append(new Option(m.replace('de_','').toUpperCase(),m)));listSaved();const last=new URLSearchParams(location.search).get('run')||localStorage.getItem('cs2-free-lab-run');let prior=null;if(last){try{prior=await api('/api/lab/job?id='+last)}catch{}}if(prior){$('map').value=prior.request.map;$('mode').value=prior.request.mode||'stand_left';$('runDistance').value=prior.request.run_distance||128;points={origin:prior.request.origin,target:prior.request.target};$('radius').value=prior.request.radius}await loadMap();if(prior){job=last;busy(true);poll()}}catch(e){status(e.message)}
