/* Movement prediction panel (review view). Local GRU inference via /api/movement/*.
   Shows the model's predicted XY path for one player from the current replay moment and, separately,
   the real future track from the demo for comparison. Labelled as a model prediction, never a best route. */
(()=>{
const E=id=>document.getElementById(id);
const M={info:null,pred:null,showActual:true,showVelocity:false,busy:false,err:null};
const COL={hist:'rgba(200,205,214,.75)',pred:'#ffb23f',actual:'#5fd38a',vel:'rgba(120,190,255,.85)'};
function el(tag,cls,text){const x=document.createElement(tag);if(cls)x.className=cls;if(text!=null)x.textContent=text;return x}
const fmt=v=>v==null?'—':v.toFixed(0);
async function get(path){const r=await fetch(path);const d=await r.json().catch(()=>({error:t('请求失败')}));if(!r.ok){const e=Error(t(d.error||'请求失败'));e.code=d.code;throw e}return d}
const current=()=>typeof round!=='undefined'&&round&&typeof match!=='undefined'?{match,round:round.number}:null;
function alivePlayers(){return (engine.state(seconds)||[]).filter(p=>p.alive)}

async function predict(){
  const c=current(),pid=E('mvPlayer')?.value;if(!c||!pid)return;
  M.busy=true;M.err=null;M.pred=null;draw();
  try{M.pred=await get(`/api/movement/predict?id=${c.match}&round=${c.round}&t=${seconds.toFixed(3)}&player=${pid}`);
    // put the map on the start point's floor (Nuke etc.)
    if(radar?.lower_url){E('floor').value=M.pred.start[2]<radar.floor_split_z?'lower':'upper'}
    engine.selected=pid;
  }catch(e){M.err=e}
  M.busy=false;draw();dirty=true;updateUi(true);
}
function replayWindow(){if(!M.pred)return;clip={start:Math.max(0,M.pred.seconds-2),end:M.pred.seconds+2,players:[M.pred.player]};seconds=clip.start;playing=true;board=null;window.render?window.render():render()}

function draw(){
  const root=E('movePanel');if(!root)return;root.replaceChildren();
  const head=el('div','mv-head');head.append(el('h2',null,t('移动预测')),el('span','mv-badge',t('模型预测 · 非最优路线')));root.append(head);
  if(M.info&&!M.info.ready){root.append(el('p','wb-note warn',t('模型不可用，缺少：')+M.info.missing.join(', ')));return}
  if(!current()){root.append(el('p','wb-note',t('先打开一场比赛的回放。')));return}
  const form=el('div','mv-form'),sel=el('select');sel.id='mvPlayer';sel.setAttribute('aria-label',t('玩家'));
  const names=engine.names||{},alive=alivePlayers(),prev=M.pred?.player||engine.selected;
  for(const p of alive)sel.append(new Option((names[p.id]||p.id)+' · '+p.side,p.id));
  if(prev&&alive.some(p=>p.id===prev))sel.value=prev;
  const go=el('button','mc-primary',M.busy?t('推理中…'):t('预测当前时刻'));go.disabled=M.busy||!alive.length;go.onclick=predict;
  form.append(sel,go);root.append(form);
  root.append(el('p','wb-note',t('从回放当前时刻（对齐到 0.5 秒）读取该玩家过去 2 秒状态，预测之后 0.5 / 1 / 2 秒位置。')));
  if(!alive.length)root.append(el('p','wb-note warn',t('此刻没有存活玩家。')));
  if(M.err){const box=el('div','mv-error');box.append(el('b',null,t('无法预测')),el('p',null,M.err.message));root.append(box)}
  const P=M.pred;
  if(P&&current()?.round===P.round){
    const who=(names[P.player]||P.player);
    root.append(el('p','mv-sub',`${who} · R${P.round} · t = ${P.seconds.toFixed(1)} s`));
    if(P.training_split==='train'||P.training_split==='validation')root.append(el('p','wb-note warn',t('这场 demo 在模型的训练/验证数据中，下面的误差偏乐观，不代表新比赛表现。')));
    else if(P.training_split==='test')root.append(el('p','wb-note',t('这场 demo 属于模型的测试集（训练时未使用，但之前已被查看过）。')));
    const lg=el('div','mv-legend');
    for(const [k,label] of [['hist',t('过去 2 秒')],['pred',t('模型预测')],['actual',t('真实后续')]]){const s=el('span');const i=el('i');i.style.background=COL[k];s.append(i,label);lg.append(s)}
    root.append(lg);
    const tog=(label,key)=>{const l=el('label','wb-check');const c=el('input');c.type='checkbox';c.checked=M[key];c.onchange=()=>{M[key]=c.checked;dirty=true;updateUi(true)};l.append(c,label);return l};
    root.append(tog(t('显示 demo 真实后续轨迹'),'showActual'),tog(t('显示匀速外推基准'),'showVelocity'));
    const er=P.errors,tb=el('table','mv-table'),hr=el('tr');
    for(const h of [t('误差（游戏单位）'),'+0.5s','+1s','+2s',t('平均')])hr.append(el('th',null,h));tb.append(hr);
    for(const [label,arr,avg] of [[t('模型预测'),er.model,er.ADE],[t('匀速外推'),er.velocity,er.velocity_ADE],[t('原地不动'),er.stationary,er.stationary_ADE]]){
      const tr=el('tr');tr.append(el('td',null,label));for(const v of arr)tr.append(el('td',null,fmt(v)));tr.append(el('td',null,fmt(avg)));tb.append(tr)}
    root.append(tb);
    if(radar?.lower_url){const fl=z=>z<radar.floor_split_z;if(P.actual.track.some(p=>p&&fl(p[2])!==fl(P.start[2])))root.append(el('p','wb-note warn',t('真实轨迹跨越楼层：另一层的部分需切换楼层查看；模型不预测高度，预测点仍画在起点楼层。')))}
    if(er.ADE==null)root.append(el('p','wb-note',t('真实后续不完整（阵亡、回合结束或位置跳变），只计算可用时间点。')));
    const bar=el('div','toolbar');const rp=el('button',null,t('▶ 回放这 4 秒'));rp.onclick=replayWindow;bar.append(rp);root.append(bar);
    root.append(el('p','wb-note',t('只预测水平位置；高度不预测，预测点按起点楼层显示。真实轨迹仅用于展示和计算误差，不进入模型输入。')));
  }
  const d=el('details','wb-sec');d.append(el('summary',null,t('模型说明与限制')));
  if(M.info?.ready){const I=M.info,kv=el('dl','wb-kv');
    for(const [k,v] of [[t('模型'),I.name],[t('版本'),I.version],[t('输入'),t('过去 2 秒自身轨迹（相对朝向）、高度、转向、俯仰、蹲、闪光；血甲、阵营、回合时间、双方存活数、下包、最近两名队友位置')],[t('输出'),t('+0.5 / +1 / +2 秒的水平位移')],[t('地图'),I.maps.map(m=>m.replace('de_','')).join(', ')],
      [t('测试集 ADE'),`${I.test.numeric.ADE} · ${t('匀速基准')} ${I.test.tuned_velocity.ADE} · ${t('不动')} ${I.test.stationary.ADE}`],[t('2 秒终点误差'),`${I.test.numeric.FDE_2s} · ${t('匀速基准')} ${I.test.tuned_velocity.FDE_2s}`]]){kv.append(el('dt',null,k),el('dd',null,v))}
    d.append(kv);
    for(const s of [t('预测的是职业选手的典型移动，不是最优路线或决策建议。'),t('不使用敌人隐藏位置、地图几何或道具效果；路径可能穿墙。'),t('仅在 64 tick、10 人对局、玩家过去 2 秒持续存活时可用；缺少输入时直接拒绝，不补零。'),t('开枪/道具预测未展示：开枪预测不如“重复上一动作”基准，道具正样本过少（测试集 0–23 个）。')])d.append(el('p','wb-note',s))}
  root.append(d);
}

function overlay(ctx,eng,tm,k){
  const P=M.pred;if(!P||!eng.radar||current()?.round!==P.round)return;
  const on=z=>eng.onFloor(z),px=p=>eng.px(p[0],p[1]);
  const line=(pts,color,width,dash)=>{ctx.save();ctx.strokeStyle=color;ctx.lineWidth=width*k;ctx.setLineDash(dash.map(x=>x*k));ctx.beginPath();let st=false;
    for(const p of pts){if(!p||!on(p[2])){st=false;continue}const [u,v]=px(p);if(!st){ctx.moveTo(u,v);st=true}else ctx.lineTo(u,v)}ctx.stroke();ctx.restore()};
  const dot=(p,color,r,label)=>{if(!p||!on(p[2]))return;const [u,v]=px(p);ctx.fillStyle=color;ctx.strokeStyle='#0a0b0d';ctx.lineWidth=1.2*k;ctx.beginPath();ctx.arc(u,v,r*k,0,6.283);ctx.fill();ctx.stroke();
    if(label){ctx.font=`600 ${8.5*k}px "Space Mono",monospace`;const w=ctx.measureText(label).width;ctx.fillStyle='rgba(8,9,11,.82)';ctx.fillRect(u+5*k,v-5*k,w+5*k,10*k);ctx.fillStyle=color;ctx.fillText(label,u+7.5*k,v+3*k)}};
  line(P.history,COL.hist,1.6,[3,3]);for(const p of P.history.slice(0,-1))dot(p,COL.hist,1.8);
  if(M.showVelocity){line([P.start,...P.baseline_velocity],COL.vel,1.4,[2,4]);P.baseline_velocity.forEach(p=>dot(p,COL.vel,2))}
  if(M.showActual){line([P.start,...P.actual.track],COL.actual,2.2,[]);P.actual.at_horizons.forEach((p,i)=>dot(p,COL.actual,3,null))}
  line([P.start,...P.predicted],COL.pred,2.4,[6,4]);
  P.predicted.forEach((p,i)=>dot(p,COL.pred,3.4,i===P.predicted.length-1?'+'+P.horizons[i]+'s':null));
  if(on(P.start[2])){const [u,v]=px(P.start);ctx.strokeStyle=COL.pred;ctx.lineWidth=2*k;ctx.beginPath();ctx.arc(u,v,11*k,0,6.283);ctx.stroke();
    ctx.font=`600 ${9*k}px "Space Mono",monospace`;const label=t('模型预测')+' · '+t('起点');const w=ctx.measureText(label).width;ctx.fillStyle='rgba(8,9,11,.85)';ctx.fillRect(u-w/2-4*k,v+13*k,w+8*k,12*k);ctx.fillStyle=COL.pred;ctx.fillText(label,u-w/2,v+22*k)}
}

async function init(){
  if(typeof engine==='undefined'||!E('moveTab'))return;
  engine.overlay=overlay;
  E('moveTab').onclick=async()=>{showPanel('move');if(!M.info)M.info=await get('/api/movement/info').catch(e=>({ready:false,missing:[e.message]}));draw()};
  // refresh the player list as the replay moves; drop a prediction from another round
  let last='';setInterval(()=>{if(E('movePanel').hidden||M.busy)return;const c=current();const key=(c?.match||'')+':'+(c?.round||'')+':'+alivePlayers().map(p=>p.id).join(',');
    if(M.pred&&c&&(c.round!==M.pred.round||c.match!==M.pred.match))M.pred=null;
    if(key!==last){last=key;draw()}},400);
}
init();
window.MovementPanel={state:M,draw};
})();
