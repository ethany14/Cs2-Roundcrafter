const assert=require('node:assert/strict');const {kind,eventsBefore,futureTargets,weaponFeatures}=require('./extract_joint.cjs');
assert.equal(kind({event_name:'weapon_fire',weapon:'weapon_knife_butterfly'}),-1);
assert.equal(kind({event_name:'weapon_fire',weapon:'weapon_ak47'}),0);
assert.equal(kind({event_name:'grenade_thrown',weapon:'smokegrenade'}),1);
const events=[{tick:100,event_name:'weapon_fire',weapon:'weapon_ak47'},{tick:132,event_name:'grenade_thrown',weapon:'flashbang'},{tick:133,event_name:'grenade_thrown',weapon:'smokegrenade'},{tick:228,event_name:'grenade_thrown',weapon:'molotov'},{tick:229,event_name:'weapon_fire',weapon:'weapon_ak47'}];
assert.deepEqual(eventsBefore(events,100,0).map(x=>x.tick),[100]);const y=futureTargets(events,100);assert.equal(y[0],0);assert.equal(y[2],1);assert.equal(y[7],1);assert.equal(y[16],1);assert.equal(y[12],0);
const unknown=weaponFeatures({});assert.equal(unknown[9],0);assert.equal(unknown[11],0);const zero=weaponFeatures({'Weapon.m_iClip1':0,'Weapon.m_bInReload':false});assert.equal(zero[9],1);assert.equal(zero[11],1);
assert.deepEqual(eventsBefore([...events,{tick:500,event_name:'weapon_fire'}],100,0),eventsBefore(events,100,0));
console.log('PASS: knife excluded, action classes, causal boundary, nonoverlapping future bins, missingness masks');
