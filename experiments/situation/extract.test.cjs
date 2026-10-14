const {test}=require('node:test');
const assert=require('node:assert/strict');
const {pairRounds}=require('./extract.cjs');
test('new normalized ends do not shift a round label',()=>{
 const starts=[{tick:100,total_rounds_played:0},{tick:900,total_rounds_played:1}];
 const ends=[{tick:0,winner:null},{tick:700,total_rounds_played:1,winner:'CT'},{tick:1500,total_rounds_played:2,winner:'T'}];
 const r=pairRounds(starts,ends).rounds;
 assert.deepEqual(r.map(x=>[x.start.total_rounds_played,x.end.winner]),[[0,3],[1,2]]);
});
test('old numeric ends retain their winner',()=>{
 assert.equal(pairRounds([{tick:100,total_rounds_played:0}],[{tick:500,total_rounds_played:0,winner:2}]).rounds[0].end.winner,2);
});
test('aborted rounds cannot borrow next rounds winner',()=>{
 const r=pairRounds([{tick:100,total_rounds_played:0},{tick:200,total_rounds_played:0}],[{tick:500,winner:'T'}]);
 assert.equal(r.skips.length,1);assert.equal(r.rounds[0].start.tick,200);
});
test('multiple competing end events are rejected',()=>{
 assert.equal(pairRounds([{tick:100}],[{tick:300,winner:'T'},{tick:400,winner:'CT'}]).rounds.length,0);
});
