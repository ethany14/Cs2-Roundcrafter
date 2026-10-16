// Exercise the actual form serializer without sending requests or calling a model.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/research-workspace.js','utf8');
const html=fs.readFileSync('web/demo-review.html','utf8');
const requestSource=source.slice(source.indexOf('function request(){'),source.indexOf('function render(data)'));
const values={query:'补齐整套战术',map:'de_nuke',side:'T',economy:'force',origin:'',motion:'',party:'',alive:'','util-smoke':'','util-flash':'','util-fire':'','util-he':''};
const context={$:selector=>({value:values[selector.slice(1)]}),sourceCase:null};
vm.createContext(context);vm.runInContext(requestSource,context);
let request=JSON.parse(JSON.stringify(context.request()));
assert.equal(request.mode,'rag');assert.ok(!('party_size' in request));assert.ok(!('alive_players' in request));assert.ok(!('utility' in request));
values.party='3';values.alive='5';values['util-smoke']='0';values['util-flash']='2';
request=JSON.parse(JSON.stringify(context.request()));
assert.equal(request.party_size,3);assert.equal(request.alive_players,5);assert.deepEqual(request.utility,{smoke:0,flash:2});
context.sourceCase='case-identifier';assert.equal(context.request().source_case,'case-identifier');
assert.ok(!html.includes('name="mode"'));
console.log('PASS: unified mode, unknown omissions, explicit zero, separate counts, case context. No network calls.');
