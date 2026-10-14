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

function open(){
  if(dialog){dialog.remove();dialog=null}
  const saved=state?.saved,providers=state?.providers||[];
  let current=providers.find(p=>p.id===saved?.provider)||providers[0];
  const status=el('div',{class:'llm-status',role:'status'},state?.configured?(T('当前使用：')+state.active.model+' @ '+state.active.host+(state.active.source==='env'?T('（来自 .env）'):'')):T('尚未配置模型服务'));
  const setStatus=(msg,kind='')=>{status.textContent=msg;status.className='llm-status'+(kind?' '+kind:'')};
  const url=el('input',{id:'llmBaseUrl',type:'url',spellcheck:'false',autocomplete:'off'});
  const model=el('input',{id:'llmModel',list:'llmModelList',spellcheck:'false',autocomplete:'off',placeholder:T('模型 ID')});
  const list=el('datalist',{id:'llmModelList'});
  const key=el('input',{id:'llmKey',type:'password',spellcheck:'false',autocomplete:'off'});
  const effort=el('select',{id:'llmEffort'},...[['',T('默认')],['low','low'],['medium','medium'],['high','high']].map(([v,l])=>el('option',{value:v},l)));
  const keyLink=el('a',{target:'_blank',rel:'noopener'},T('获取 API Key ↗'));
  const urlNote=el('div',{class:'llm-hint'});
  const keyHint=el('div',{class:'llm-hint'});
  const grid=el('div',{class:'llm-providers',role:'group','aria-label':T('服务商')});
  const show=el('button',{type:'button',class:'llm-act'},T('显示'));
  show.onclick=()=>{const h=key.type==='password';key.type=h?'text':'password';show.textContent=h?T('隐藏'):T('显示')};

  function pick(p,keepValues){
    current=p;for(const b of grid.children)b.setAttribute('aria-pressed',String(b.dataset.id===p.id));
    const same=saved&&saved.provider===p.id;
    url.value=keepValues&&same?saved.base_url:p.base_url;url.placeholder=p.base_url||'https://…/v1';
    model.value=keepValues&&same?saved.model:(p.models[0]||'');
    list.replaceChildren(...p.models.map(m=>el('option',{value:m})));
    key.value='';key.placeholder=same&&saved.has_key?T('已保存')+' '+(saved.key_hint||'')+T('（留空不修改）'):(p.key_optional?T('本地服务可留空'):T('粘贴 API Key'));
    if(p.key_url){keyLink.href=p.key_url;keyLink.hidden=false}else keyLink.hidden=true;
    urlNote.textContent=p.note||(p.id==='custom'?T('任何兼容 OpenAI chat/completions 的服务都可以'):'');
    keyHint.replaceChildren(p.protocol==='anthropic'?T('通过 Anthropic 官方 SDK 连接。'):T('通过 OpenAI 兼容接口连接。'),' ',keyLink);
    effort.value=keepValues&&same?saved.effort||'':'';
  }
  for(const p of providers){const b=el('button',{type:'button','data-id':p.id,'aria-pressed':'false'},p.label);b.onclick=()=>pick(p,true);grid.append(b)}

  const form=()=>({provider:current.id,base_url:url.value.trim(),model:model.value.trim(),api_key:key.value.trim(),effort:effort.value});
  const busy=(btn,fn)=>async()=>{const all=dialog.querySelectorAll('.llm-act');all.forEach(b=>b.disabled=true);
    try{await fn()}catch(e){setStatus(e.message,'bad')}finally{all.forEach(b=>b.disabled=false)}};

  const load=el('button',{type:'button',class:'llm-act'},T('加载模型列表'));
  load.onclick=busy(load,async()=>{setStatus(T('正在向服务商请求模型列表…'));const r=await api('/api/llm/models',form());
    list.replaceChildren(...r.models.map(m=>el('option',{value:m})));setStatus(T('已加载 {0} 个模型；在模型框中输入或选择',[r.models.length]),'ok')});
  const test=el('button',{type:'button',class:'llm-act'},T('测试连接'));
  test.onclick=busy(test,async()=>{setStatus(T('正在测试…'));const r=await api('/api/llm/test',form());
    setStatus(T('连接成功 · {0} · {1} ms',[r.model,r.latency_ms])+' · '+(r.tool_calls?T('支持工具调用'):T('未调用工具：Agent 可能无法正常工作')),r.tool_calls?'ok':'bad')});
  const save=el('button',{type:'button',class:'llm-act llm-primary'},T('保存'));
  save.onclick=busy(save,async()=>{state=await api('/api/llm/settings',form());paintButton();setStatus(T('已保存，正在刷新页面…'),'ok');setTimeout(()=>location.reload(),700)});
  const clear=el('button',{type:'button',class:'llm-act'},T('清除已保存设置'));clear.hidden=!saved;
  clear.onclick=busy(clear,async()=>{state=await api('/api/llm/clear',{});paintButton();setStatus(T('已清除，正在刷新页面…'),'ok');setTimeout(()=>location.reload(),700)});
  const close=el('button',{type:'button',class:'llm-act','aria-label':T('关闭')},'✕');close.onclick=()=>dialog.close();

  dialog=el('dialog',{class:'llm-dialog','aria-labelledby':'llmTitle'},
    el('header',{},el('h2',{id:'llmTitle'},el('small',{},'AGENT · MODEL'),T('模型设置')),close),
    el('div',{class:'llm-body'},
      el('div',{},el('span',{class:'llm-label'},T('服务商')),grid),
      el('div',{class:'llm-two'},
        el('div',{},el('label',{class:'llm-label',for:'llmModel'},T('模型')),el('div',{class:'llm-row'},model,load),list,
          el('div',{class:'llm-hint'},T('列表只是建议，可能过时；点“加载模型列表”获取服务商当前可用的模型。Agent 需要支持工具调用的模型。'))),
        el('div',{},el('label',{class:'llm-label',for:'llmEffort'},T('推理强度')),effort,el('div',{class:'llm-hint'},T('“默认”不发送该参数')))),
      el('div',{},el('label',{class:'llm-label',for:'llmKey'},'API Key'),el('div',{class:'llm-row'},key,show),keyHint),
      el('div',{},el('label',{class:'llm-label',for:'llmBaseUrl'},T('接口地址')),url,urlNote),
      status,
      el('div',{class:'llm-privacy'},T('密钥只保存在本机'),' ',el('code',{},'data/account/llm.json'),T('，不会返回到浏览器。保存后优先于 .env；清除后回到 .env。'))),
    el('footer',{},clear,el('div',{},test,save)));
  document.body.append(dialog);
  pick(current,true);
  dialog.showModal();
}
window.openModelSettings=()=>{if(state)open();else refresh().then(open)};
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
