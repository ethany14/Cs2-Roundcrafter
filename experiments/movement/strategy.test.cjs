const assert=require('node:assert/strict');const {features,label,NAMES}=require('./extract_strategy.cjs');
const a={steamid:'1',team_num:3,is_alive:true,X:1000,Y:0,Z:0,health:100,armor_value:100,current_equip_value:4000,has_defuser:true,inventory:[]};const e={...a,steamid:'2',team_num:2,approximate_spotted_by:[]};const bomb={tick:200,user_X:0,user_Y:0,user_Z:0};
const before=features([a,e],a,128,0,bomb,[],[]);
const changed=features([a,{...e,X:9999,health:1}],a,128,0,{...bomb,user_X:8000},[{...e,tick:129,approximate_spotted_by:['1']}],[{tick:129,radius:1100,user_X:1000,user_Y:0,user_Z:0,step:true}]);
assert.deepEqual(before,changed);assert.equal(before.length,NAMES.length);assert.equal(before[9],0);
const last={...e,X:1200,tick:64,approximate_spotted_by:['1']};assert.deepEqual(features([a,e],a,128,0,bomb,[last],[]),features([a,{...e,X:9999}],a,128,0,bomb,[last],[]));
assert.equal(label(a,{...a,X:700},{X:0,Y:0,Z:0}).label,0);assert.equal(label(a,{...a,X:1400},{X:0,Y:0,Z:0}).label,2);assert.equal(label(a,{...a,X:1005},{X:0,Y:0,Z:0}).label,1);assert.equal(label(a,{...a,is_alive:false},{X:0,Y:0,Z:0}).label,-1);
console.log('4 groups passed: future/hidden isolation, stale sighting, disclosure boundary, weak label boundaries');
