/* Bilingual UI layer. Source strings are the Chinese originals; English lives in i18n-en.js.
   t('已加载 {0}/{1} 回合',[a,b]) fills {n} placeholders. Switching language reloads the page so
   every string (including ones computed at load time) is rebuilt; page state lives in URL/localStorage. */
(()=>{
  const KEY='cs2-lang';
  let lang='zh';
  try{lang=localStorage.getItem(KEY)||((navigator.language||'').toLowerCase().startsWith('zh')?'zh':'en')}catch{}
  if(lang!=='zh'&&lang!=='en')lang='zh';
  const fill=(s,args)=>args==null?s:String(s).replace(/\{(\d+)\}/g,(m,i)=>args[i]===undefined||args[i]===null?'':String(args[i]));
  function t(s,args){
    if(s==null)return s;
    if(args!==undefined&&!Array.isArray(args))args=[args];
    const dict=window.I18N_EN||{};
    if(lang!=='en')return fill(s,args);
    if(Object.prototype.hasOwnProperty.call(dict,s))return fill(dict[s],args);
    // Server text with embedded numbers/names: ordered regex patterns, first match wins.
    if(typeof s==='string'&&/[　-鿿＀-￯]/.test(s))
      for(const [re,out] of PATTERNS)if(re.test(s))return fill(s.replace(re,out),args);
    return fill(s,args);
  }
  const PATTERNS=(window.I18N_EN_PATTERNS||[]).map(([src,out])=>[new RegExp('^'+src+'$'),out]);
  // Structured server evidence (routes, event lists): exact/pattern first, then a term glossary. Not for model prose.
  const GLOSS=(window.I18N_EN_GLOSS||[]).slice().sort((a,b)=>b[0].length-a[0].length);
  function gloss(s){
    if(lang!=='en'||typeof s!=='string'||!/[　-鿿＀-￯]/.test(s))return s;
    const r=t(s);if(r!==s)return r;
    let out=s;for(const [zh,en] of GLOSS)if(out.includes(zh))out=out.split(zh).join(en);
    return out.replace(/ {2,}/g,' ').trim();
  }
  function translateNode(root){
    if(lang==='zh'||!root)return;
    const dict=window.I18N_EN||{};
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement&&!['SCRIPT','STYLE','TEXTAREA'].includes(n.parentElement.tagName)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});
    const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    for(const n of nodes){const raw=n.nodeValue,key=raw.trim();if(key&&Object.prototype.hasOwnProperty.call(dict,key))n.nodeValue=raw.replace(key,dict[key])}
    for(const el of root.querySelectorAll?root.querySelectorAll('[placeholder],[title],[aria-label]'):[])
      for(const a of ['placeholder','title','aria-label']){const v=el.getAttribute(a);if(v&&Object.prototype.hasOwnProperty.call(dict,v.trim()))el.setAttribute(a,dict[v.trim()])}
  }
  function setLang(next){if(next===lang)return;try{localStorage.setItem(KEY,next)}catch{}location.reload()}
  function mountToggles(){
    for(const box of document.querySelectorAll('[data-lang-toggle]')){
      box.replaceChildren();
      for(const [code,label] of [['zh','中'],['en','EN']]){
        const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-pressed',String(code===lang));
        b.title=code==='zh'?'切换到中文':'Switch to English';b.onclick=()=>setLang(code);box.append(b);
      }
    }
  }
  window.t=t;
  window.I18N={get lang(){return lang},t,gloss,setLang,apply(root=document.body){translateNode(root);if(lang==='en'){document.title=t(document.title.trim())}document.documentElement.lang=lang==='zh'?'zh-CN':'en';mountToggles()}};
  document.addEventListener('DOMContentLoaded',()=>window.I18N.apply());
})();
