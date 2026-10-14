/* Model settings: pick a provider and model and paste an API key, instead of editing .env.
   The key goes to the local server (data/account/llm.json) and is never sent back to the page.
   Mounts a "Model" button in the top bar of any page that loads this script. */
(()=>{
const T=(s,a)=>window.t?window.t(s,a):String(s).replace(/\{(\d+)\}/g,(m,i)=>a?.[i]??'');
let token=null,state=null,dialog=null,button=null;

async function api(path,body){
  if(body!==undefined&&!token){const s=await (await fetch('/api/status')).json();token=s.token}
  const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)});
  const d=await r.json();if(!r.ok)throw Error(T(d.error)||T('请求失败'));return d}
function el(tag,attrs={},...kids){const e=document.createElement(tag);
  for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e[k]=v;else if(v!=null&&v!==false)e.setAttribute(k,v===true?'':v)}
  for(const c of kids.flat())if(c!=null)e.append(c);return e}

const CSS=`
.llm-btn{display:inline-flex;align-items:center;gap:8px;font:600 11px var(--mono,ui-monospace,monospace);letter-spacing:.06em;text-transform:none;
  background:transparent;color:var(--ink2,#c9c3b4);border:1px solid var(--line2,#343a43);padding:5px 10px;cursor:pointer;max-width:180px}
@media (max-width:1600px){.mc-status:has(.llm-btn)>span:not(.mc-led){display:none}}
.llm-btn:hover{border-color:var(--amber,#ffb23f);color:var(--ink,#ece6d6)}
.llm-btn span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.llm-btn i{width:7px;height:7px;border-radius:50%;flex:none;background:var(--green,#82d68f);box-shadow:0 0 8px var(--green,#82d68f)}
.llm-btn.off i{background:var(--amber,#ffb23f);box-shadow:0 0 8px var(--amber,#ffb23f)}
.llm-dialog{width:min(760px,calc(100vw - 32px));max-height:calc(100dvh - 32px);padding:0;border:1px solid var(--line2,#343a43);
  background:var(--panel,#111317);color:var(--ink,#ece6d6);font:13px/1.55 var(--body,system-ui,sans-serif)}
.llm-dialog[open]{display:flex;flex-direction:column}
.llm-dialog::backdrop{background:#000a}
.llm-dialog header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line2,#343a43)}
.llm-dialog h2{margin:0;font:700 22px var(--head,"Arial Narrow",sans-serif);letter-spacing:.04em;text-transform:uppercase}
.llm-dialog h2 small{display:block;font:400 10px var(--mono,monospace);letter-spacing:.2em;color:var(--dim,#958f82)}
.llm-body{padding:16px 18px;display:grid;gap:16px;overflow:auto;flex:1 1 auto;min-height:0}
.llm-label{font:700 10px var(--mono,monospace);letter-spacing:.16em;text-transform:uppercase;color:var(--dim,#958f82);margin-bottom:6px;display:block}
.llm-providers{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.llm-providers button{text-align:left;font:600 12px var(--body,sans-serif);letter-spacing:0;text-transform:none;padding:8px 10px;
  background:var(--bg2,#0d0f12);color:var(--ink2,#c9c3b4);border:1px solid var(--line2,#343a43);cursor:pointer}
.llm-providers button:hover{border-color:var(--amber,#ffb23f)}
.llm-providers button[aria-pressed=true]{background:var(--ink,#ece6d6);color:#111;border-color:var(--ink,#ece6d6)}
.llm-row{display:flex;gap:8px;align-items:stretch}
.llm-row input,.llm-row select{flex:1;min-width:0}
.llm-dialog input,.llm-dialog select{font:12px var(--mono,monospace);color:var(--ink,#ece6d6);background:var(--bg2,#0d0f12);border:1px solid var(--line2,#343a43);padding:8px 10px;width:100%}
.llm-dialog .llm-act{font:700 11px var(--mono,monospace);letter-spacing:.08em;text-transform:uppercase;padding:8px 12px;background:transparent;
  color:var(--ink2,#c9c3b4);border:1px solid var(--line2,#343a43);cursor:pointer;white-space:nowrap}
.llm-dialog .llm-act:hover:not(:disabled){border-color:var(--amber,#ffb23f);color:var(--ink,#ece6d6)}
.llm-dialog .llm-act:disabled{opacity:.45;cursor:default}
.llm-dialog .llm-primary{background:var(--red,#fc3d21);border-color:var(--red,#fc3d21);color:#fff}
.llm-dialog .llm-primary:hover:not(:disabled){background:#ff5a3f;color:#fff}
.llm-hint{font-size:11px;color:var(--dim,#958f82);margin-top:6px}
.llm-hint a{color:var(--amber,#ffb23f)}
.llm-two{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:12px}
@media (max-width:600px){.llm-two{grid-template-columns:1fr}}
.llm-status{font:12px var(--mono,monospace);padding:10px 12px;border:1px dashed var(--line2,#343a43);color:var(--ink2,#c9c3b4);min-height:20px}
.llm-status.ok{border-color:var(--green,#82d68f);color:var(--green,#82d68f)}
.llm-status.bad{border-color:var(--red,#fc3d21);color:#ff8a76}
.llm-panel{display:flex;flex-direction:column;min-height:0;flex:1 1 auto}
.llm-panel[hidden]{display:none}
.llm-tabs{display:flex;border-bottom:1px solid var(--line2,#343a43);padding:0 18px}
.llm-tabs button{font:700 11px var(--mono,monospace);letter-spacing:.1em;text-transform:uppercase;background:transparent;border:0;border-bottom:2px solid transparent;
  color:var(--dim,#958f82);padding:10px 12px;cursor:pointer;margin-bottom:-1px}
.llm-tabs button[aria-selected=true]{color:var(--ink,#ece6d6);border-bottom-color:var(--red,#fc3d21)}
.llm-index{border:1px solid var(--line2,#343a43);background:var(--bg2,#0d0f12);font:12px var(--mono,monospace)}
.llm-index div{display:flex;justify-content:space-between;gap:12px;padding:6px 10px;border-bottom:1px solid var(--line,#23272e)}
.llm-index div:last-child{border-bottom:0}
.llm-index b{font-variant-numeric:tabular-nums;color:var(--amber,#ffb23f)}
.llm-index .llm-index-total{color:var(--dim,#958f82)}
.llm-dialog footer{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:center;padding:12px 18px;border-top:1px solid var(--line2,#343a43)}
.llm-dialog footer div{display:flex;gap:8px;flex-wrap:wrap}
.llm-privacy{font-size:11px;color:var(--dim,#958f82);padding:10px 12px;background:var(--bg2,#0d0f12);border-left:2px solid var(--green,#82d68f)}
.llm-privacy code{font:11px var(--mono,monospace);color:var(--amber,#ffb23f)}`;

function label(s){const a=s&&s.active;if(!a)return T('设置模型');return a.model}
function paintButton(){if(!button)return;const on=state&&state.configured;button.classList.toggle('off',!on);
  button.querySelector('span').textContent=on?label(state):T('设置模型');
  button.title=on?T('模型设置')+' · '+state.active.host+(state.active.source==='env'?' (.env)':''):T('尚未配置模型服务')}

function mount(){
  const style=el('style');style.textContent=CSS;document.head.append(style);
  button=el('button',{type:'button',class:'llm-btn off','aria-haspopup':'dialog'},el('i'),el('span',{},T('设置模型')));
  button.onclick=open;
  const host=document.querySelector('[data-llm-settings]')||document.querySelector('.mc-status')||document.querySelector('header nav')||document.querySelector('header');
  if(!host)return;
  const lang=host.querySelector('[data-lang-toggle]');lang?host.insertBefore(button,lang):host.append(button);
  refresh().catch(()=>{});
}
async function refresh(){state=await api('/api/llm/settings');paintButton();return state}

function providerGrid(providers,label,onPick){
  const grid=el('div',{class:'llm-providers',role:'group','aria-label':label});
  for(const p of providers){const b=el('button',{type:'button','data-id':p.id,'aria-pressed':'false'},p.label);b.onclick=()=>onPick(p);grid.append(b)}
  grid.select=id=>{for(const b of grid.children)b.setAttribute('aria-pressed',String(b.dataset.id===id))};return grid}
function keyField(id){
  const key=el('input',{id,type:'password',spellcheck:'false',autocomplete:'off'});
  const show=el('button',{type:'button',class:'llm-act'},T('显示'));
  show.onclick=()=>{const h=key.type==='password';key.type=h?'text':'password';show.textContent=h?T('隐藏'):T('显示')};
  return {key,row:el('div',{class:'llm-row'},key,show)}}
function statusLine(text){const s=el('div',{class:'llm-status',role:'status'},text);
  s.set=(msg,kind='')=>{s.textContent=msg;s.className='llm-status'+(kind?' '+kind:'')};return s}
function busy(status,fn){return async()=>{const all=dialog.querySelectorAll('.llm-act');all.forEach(b=>b.disabled=true);
  try{await fn()}catch(e){status.set(e.message,'bad')}finally{all.forEach(b=>b.disabled=false)}}}

function chatPanel(){
  const saved=state?.saved,providers=state?.providers||[];
  let current=providers.find(p=>p.id===saved?.provider)||providers[0];
  const status=statusLine(state?.configured?(T('当前使用：')+state.active.model+' @ '+state.active.host+(state.active.source==='env'?T('（来自 .env）'):'')):T('尚未配置模型服务'));
  const url=el('input',{id:'llmBaseUrl',type:'url',spellcheck:'false',autocomplete:'off'});
  const model=el('input',{id:'llmModel',list:'llmModelList',spellcheck:'false',autocomplete:'off',placeholder:T('模型 ID')});
  const list=el('datalist',{id:'llmModelList'});
  const {key,row}=keyField('llmKey');
  const effort=el('select',{id:'llmEffort'},...[['',T('默认')],['low','low'],['medium','medium'],['high','high']].map(([v,l])=>el('option',{value:v},l)));
  const keyLink=el('a',{target:'_blank',rel:'noopener'},T('获取 API Key ↗'));
  const urlNote=el('div',{class:'llm-hint'}),keyHint=el('div',{class:'llm-hint'});
  const grid=providerGrid(providers,T('服务商'),p=>pick(p,true));
  function pick(p,keepValues){
    current=p;grid.select(p.id);const same=saved&&saved.provider===p.id;
    url.value=keepValues&&same?saved.base_url:p.base_url;url.placeholder=p.base_url||'https://…/v1';
    model.value=keepValues&&same?saved.model:(p.models[0]||'');
    list.replaceChildren(...p.models.map(m=>el('option',{value:m})));
    key.value='';key.placeholder=same&&saved.has_key?T('已保存')+' '+(saved.key_hint||'')+T('（留空不修改）'):(p.key_optional?T('本地服务可留空'):T('粘贴 API Key'));
    if(p.key_url){keyLink.href=p.key_url;keyLink.hidden=false}else keyLink.hidden=true;
    urlNote.textContent=p.note||(p.id==='custom'?T('任何兼容 OpenAI chat/completions 的服务都可以'):'');
    keyHint.replaceChildren(p.protocol==='anthropic'?T('通过 Anthropic 官方 SDK 连接。'):T('通过 OpenAI 兼容接口连接。'),' ',keyLink);
    effort.value=keepValues&&same?saved.effort||'':'';
  }
  const form=()=>({provider:current.id,base_url:url.value.trim(),model:model.value.trim(),api_key:key.value.trim(),effort:effort.value});
  const load=el('button',{type:'button',class:'llm-act'},T('加载模型列表'));
  load.onclick=busy(status,async()=>{status.set(T('正在向服务商请求模型列表…'));const r=await api('/api/llm/models',form());
    list.replaceChildren(...r.models.map(m=>el('option',{value:m})));status.set(T('已加载 {0} 个模型；在模型框中输入或选择',[r.models.length]),'ok')});
  const test=el('button',{type:'button',class:'llm-act'},T('测试连接'));
  test.onclick=busy(status,async()=>{status.set(T('正在测试…'));const r=await api('/api/llm/test',form());
    status.set(T('连接成功 · {0} · {1} ms',[r.model,r.latency_ms])+' · '+(r.tool_calls?T('支持工具调用'):T('未调用工具：Agent 可能无法正常工作')),r.tool_calls?'ok':'bad')});
  const save=el('button',{type:'button',class:'llm-act llm-primary'},T('保存'));
  save.onclick=busy(status,async()=>{state=await api('/api/llm/settings',form());paintButton();status.set(T('已保存，正在刷新页面…'),'ok');setTimeout(()=>location.reload(),700)});
  const clear=el('button',{type:'button',class:'llm-act'},T('清除已保存设置'));clear.hidden=!saved;
  clear.onclick=busy(status,async()=>{state=await api('/api/llm/clear',{});paintButton();status.set(T('已清除，正在刷新页面…'),'ok');setTimeout(()=>location.reload(),700)});
  const panel=el('div',{class:'llm-panel'},
    el('div',{class:'llm-body'},
      el('div',{},el('span',{class:'llm-label'},T('服务商')),grid),
      el('div',{class:'llm-two'},
        el('div',{},el('label',{class:'llm-label',for:'llmModel'},T('模型')),el('div',{class:'llm-row'},model,load),list,
          el('div',{class:'llm-hint'},T('列表只是建议，可能过时；点“加载模型列表”获取服务商当前可用的模型。Agent 需要支持工具调用的模型。'))),
        el('div',{},el('label',{class:'llm-label',for:'llmEffort'},T('推理强度')),effort,el('div',{class:'llm-hint'},T('“默认”不发送该参数')))),
      el('div',{},el('label',{class:'llm-label',for:'llmKey'},'API Key'),row,keyHint),
      el('div',{},el('label',{class:'llm-label',for:'llmBaseUrl'},T('接口地址')),url,urlNote),
      status,
      el('div',{class:'llm-privacy'},T('密钥只保存在本机'),' ',el('code',{},'data/account/llm.json'),T('，不会返回到浏览器。保存后优先于 .env；清除后回到 .env。'))),
    el('footer',{},clear,el('div',{},test,save)));
  pick(current,true);return panel}

const LIBRARIES={tactic_cards:'战术卡片',reviewed_notes:'已审核笔记',case_library:'你的案例库',lineup_cards:'投掷点卡片',learning_resources:'学习资料'};
function embedPanel(es){
  const saved=es.saved,providers=es.providers;
  let current=providers.find(p=>p.id===saved?.provider)||providers[0];
  const status=statusLine(es.configured?T('当前使用：')+saved.model+' · '+saved.provider:T('尚未配置向量嵌入：检索使用关键词排序'));
  const url=el('input',{id:'embBaseUrl',type:'url',spellcheck:'false',autocomplete:'off'});
  const model=el('input',{id:'embModel',list:'embModelList',spellcheck:'false',autocomplete:'off',placeholder:T('模型 ID')});
  const list=el('datalist',{id:'embModelList'});
  const dims=el('input',{id:'embDims',type:'number',min:'32',max:'8192',step:'1',placeholder:T('默认')});
  const {key,row}=keyField('embKey');
  const keyLink=el('a',{target:'_blank',rel:'noopener'},T('获取 API Key ↗'));
  const urlNote=el('div',{class:'llm-hint'}),keyHint=el('div',{class:'llm-hint'});
  const index=el('div',{class:'llm-index'});
  const paintIndex=ix=>{index.replaceChildren(
    ...(ix.libraries.length?ix.libraries.map(l=>el('div',{},el('span',{},T(LIBRARIES[l.library]||l.library)),el('b',{},String(l.items)))):[el('div',{},el('span',{},T('索引为空：首次检索时会自动建立，也可以点“重建索引”')))]),
    el('div',{class:'llm-index-total'},el('span',{},T('已缓存向量')),el('b',{},String(ix.vectors))))};
  paintIndex(es.index);
  const grid=providerGrid(providers,T('服务商'),p=>pick(p,true));
  function pick(p,keepValues){
    current=p;grid.select(p.id);const same=saved&&saved.provider===p.id;
    url.value=keepValues&&same?saved.base_url:p.base_url;url.placeholder=p.base_url||'https://…/v1';
    model.value=keepValues&&same?saved.model:(p.models[0]||'');
    list.replaceChildren(...p.models.map(m=>el('option',{value:m})));
    dims.value=keepValues&&same&&saved.dimensions?saved.dimensions:'';dims.disabled=!p.dimensions;
    const chatSame=state?.saved?.provider===p.id&&state.saved.has_key;
    key.value='';key.placeholder=same&&saved.has_key?T('已保存')+' '+(saved.key_hint||'')+T('（留空不修改）'):chatSame?T('留空则使用对话模型的同一密钥'):(p.key_optional?T('本地服务可留空'):T('粘贴 API Key'));
    if(p.key_url){keyLink.href=p.key_url;keyLink.hidden=false}else keyLink.hidden=true;
    urlNote.textContent=p.id==='custom'?T('任何兼容 OpenAI /embeddings 的服务都可以'):(p.note?T(p.note):'');
    keyHint.replaceChildren(keyLink);
  }
  const form=()=>({provider:current.id,base_url:url.value.trim(),model:model.value.trim(),api_key:key.value.trim(),dimensions:dims.disabled?'':dims.value});
  const test=el('button',{type:'button',class:'llm-act'},T('测试连接'));
  test.onclick=busy(status,async()=>{status.set(T('正在测试…'));const r=await api('/api/embedding/test',form());
    status.set(T('连接成功 · {0} · {1} 维 · {2} ms · 中英同义句相似度 {3}',[r.model,r.dimensions,r.latency_ms,r.cross_language_similarity]),'ok')});
  const rebuild=el('button',{type:'button',class:'llm-act'},T('重建索引'));rebuild.hidden=!es.configured;
  rebuild.onclick=busy(status,async()=>{status.set(T('正在为资料库生成向量…'));const r=await api('/api/embedding/rebuild',{});
    paintIndex(r.index);status.set(T('索引已更新：{0} 个资料库',[r.rebuilt.length]),'ok')});
  const save=el('button',{type:'button',class:'llm-act llm-primary'},T('保存'));
  const clear=el('button',{type:'button',class:'llm-act'},T('清除已保存设置'));clear.hidden=!saved;
  save.onclick=busy(status,async()=>{const r=await api('/api/embedding/settings',form());paintIndex(r.index);rebuild.hidden=false;clear.hidden=false;
    status.set(T('已保存。检索现在使用向量与关键词混合排序。'),'ok')});
  clear.onclick=busy(status,async()=>{const r=await api('/api/embedding/clear',{});paintIndex(r.index);rebuild.hidden=true;clear.hidden=true;
    status.set(T('已清除：检索回到关键词排序。'),'ok')});
  const panel=el('div',{class:'llm-panel'},
    el('div',{class:'llm-body'},
      el('div',{class:'llm-hint'},T('向量嵌入用于检索：资料库和查询先转成向量，再按语义相似度与关键词混合排序，中英文可以互相匹配。未配置时使用关键词排序。')),
      el('div',{},el('span',{class:'llm-label'},T('服务商')),grid),
      el('div',{class:'llm-two'},
        el('div',{},el('label',{class:'llm-label',for:'embModel'},T('模型')),model,list,el('div',{class:'llm-hint'},T('换模型后需要重新生成向量；旧向量会保留，切回时可直接复用。'))),
        el('div',{},el('label',{class:'llm-label',for:'embDims'},T('向量维度')),dims,el('div',{class:'llm-hint'},T('仅 OpenAI 支持自定义维度')))),
      el('div',{},el('label',{class:'llm-label',for:'embKey'},'API Key'),row,keyHint),
      el('div',{},el('label',{class:'llm-label',for:'embBaseUrl'},T('接口地址')),url,urlNote),
      el('div',{},el('span',{class:'llm-label'},T('向量索引')),index),
      status,
      el('div',{class:'llm-privacy'},T('检索时，资料库文本和查询会发送给向量服务商；职业回合与职业案例库的情境向量在本机计算，不会发送。向量缓存在'),' ',el('code',{},'data/vectors/'),T('。'))),
    el('footer',{},clear,el('div',{},test,rebuild,save)));
  pick(current,true);return panel}

async function open(){
  if(dialog){dialog.remove();dialog=null}
  let es=null;try{es=await api('/api/embedding/settings')}catch{}
  const close=el('button',{type:'button',class:'llm-act','aria-label':T('关闭')},'✕');close.onclick=()=>dialog.close();
  const tabs=el('div',{class:'llm-tabs',role:'tablist'});
  dialog=el('dialog',{class:'llm-dialog','aria-labelledby':'llmTitle'},
    el('header',{},el('h2',{id:'llmTitle'},el('small',{},'AGENT · MODEL'),T('模型设置')),close),tabs);
  document.body.append(dialog);
  const panels=[[T('对话模型'),chatPanel()],...(es?[[T('向量嵌入（检索）'),embedPanel(es)]]:[])];
  for(const [name,panel] of panels){
    const tab=el('button',{type:'button',role:'tab'},name);
    tab.onclick=()=>{for(const [b,p] of tabs.pairs){b.setAttribute('aria-selected',String(b===tab));p.hidden=p!==panel}};
    tabs.append(tab);dialog.append(panel);(tabs.pairs=tabs.pairs||[]).push([tab,panel]);
  }
  tabs.pairs[0][0].click();
  dialog.showModal();
}
window.openModelSettings=()=>{if(state)open();else refresh().then(open)};
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
