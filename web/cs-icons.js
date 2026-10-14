/* CS2 equipment icons (decompiled locally from the installed game, served at /icons/<key>.svg).
   Icons are drawn as CSS masks so they take the surrounding text colour. */
(()=>{
const MAP={ak47:'ak47',m4a1s:'m4a1_silencer',m4a1silencer:'m4a1_silencer',m4a4:'m4a1',m4a1:'m4a1',awp:'awp',ssg08:'ssg08',scar20:'scar20',g3sg1:'g3sg1',aug:'aug',sg553:'sg556',sg556:'sg556',
  galilar:'galilar',galil:'galilar',famas:'famas',mp9:'mp9',mac10:'mac10',ump45:'ump45',p90:'p90',mp7:'mp7',mp5sd:'mp5sd',ppbizon:'bizon',bizon:'bizon',
  nova:'nova',xm1014:'xm1014',mag7:'mag7',sawedoff:'sawedoff',m249:'m249',negev:'negev',
  glock18:'glock',glock:'glock',usps:'usp_silencer',uspsilencer:'usp_silencer',p2000:'p2000',hkp2000:'hkp2000',p250:'p250',fiveseven:'fiveseven',tec9:'tec9',cz75auto:'cz75a',cz75a:'cz75a',
  dualberettas:'elite',elite:'elite',deserteagle:'deagle',deagle:'deagle',r8revolver:'revolver',revolver:'revolver',zeusx27:'taser',taser:'taser',
  smokegrenade:'smokegrenade',flashbang:'flashbang',highexplosivegrenade:'hegrenade',hegrenade:'hegrenade',molotov:'molotov',incendiarygrenade:'incgrenade',incgrenade:'incgrenade',decoygrenade:'decoy',decoy:'decoy',
  c4explosive:'c4',c4:'c4',planted_c4:'planted_c4',plantedc4:'planted_c4',kevlar:'kevlar',armor:'armor',armorhelmet:'armor_helmet',helmet:'helmet',defuser:'defuser',defusekit:'defuser',world:'world',inferno:'inferno'};
const KNIFE=/knife|bayonet|karambit|butterfly|daggers|bowie|falchion|navaja|stiletto|talon|ursus|kukri|huntsman|gut|flip|skeleton|nomad|paracord|survival|classic/i;
const GRENADES=new Set(['smokegrenade','flashbang','hegrenade','molotov','incgrenade','decoy']);
const PISTOLS=new Set(['glock','usp_silencer','p2000','hkp2000','p250','fiveseven','tec9','cz75a','elite','deagle','revolver']);
function key(name){if(!name)return null;if(KNIFE.test(name)&&!/c4/i.test(name))return 'knife';const k=String(name).toLowerCase().replace(/^weapon_/,'').replace(/[^a-z0-9]/g,'');return MAP[k]||null}
function el(name,cls='',title){const k=MAP[name]===name?name:key(name);const i=document.createElement('i');i.className='ci '+cls;i.title=title||name||'';
  if(k){i.style.setProperty('--icon',`url(/icons/${k}.svg)`);i.dataset.k=k;i.classList.add('k-'+kind(k))}else{i.classList.add('ci-text');i.textContent=(name||'?').replace(/^weapon_/,'').slice(0,6)}return i}
function kind(k){if(!k)return 'other';if(k==='knife')return 'knife';if(GRENADES.has(k))return 'grenade';if(PISTOLS.has(k))return 'pistol';if(k==='c4')return 'c4';if(k==='taser')return 'taser';return 'primary'}
window.CSIcon={key,el,kind,GRENADES};
})();
