const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const batch=require('../merge_batch.cjs');
const {readWithRetry,describeFailure}=require('../../lib/maintenance-failures');
const {openStore}=require('../../lib/maintenance-state');
const sha='a'.repeat(40), app={id:15368};
const spec=[{label:'ci',aliases:['ci','legacy-ci'],appId:15368}];
const old={id:1,name:'legacy-ci',app,status:'completed',conclusion:'success',created_at:'2026-01-01T00:00:00Z'};
let cases=0;
assert.match(require('../maintenance_cycle.cjs').nextAction({prepared:true,reviewAttested:true}),/existing exact-head attestation/);cases++;
for(const [status,conclusion,expected] of [['completed','failure','failed'],['completed','cancelled','failed'],['completed','timed_out','failed'],['completed','skipped','failed'],['completed',null,'failed'],['in_progress',null,'pending'],['queued',null,'pending'],['completed','success','success']]) {
  const newer={...old,id:2,name:'ci',status,conclusion,created_at:'2026-01-01T00:01:00Z'};
  for(const order of [[old,newer],[newer,old]]) {assert.equal(batch.summarizeRequiredCheckRuns(order,spec)[0].state,expected);cases++;}
}
assert.equal(batch.summarizeRequiredCheckRuns([{...old,name:'ci'},{...old,id:2,name:'ci',app:{id:999},conclusion:'failure'}],spec)[0].state,'success');cases++;
let pagination;
assert.deepEqual(batch.listCheckRuns('/unused','o/r',sha,{runGhApiJson:(_root,_args,options)=>{pagination=options;return [{check_runs:[old]},{check_runs:[{...old,id:2}]}];}}).map(r=>r.id),[1,2]);
assert.deepEqual(pagination,{paginate:true,slurp:true});cases++;
for(const payload of [null,{},[],[{}],[{check_runs:[]},null]]) {
  assert.throws(()=>batch.listCheckRuns('/unused','o/r',sha,{runGhApiJson:()=>payload}),e=>e.failureCode==='INVALID_RESPONSE');cases++;
}
for(const [message,code,retries] of [['HTTP 503','NETWORK_UNAVAILABLE',3],['ECONNRESET','NETWORK_UNAVAILABLE',3],['HTTP 401','AUTH_REQUIRED',1],['HTTP 403','AUTH_REQUIRED',1],['HTTP 429','RATE_LIMITED',1],['HTTP 403 API rate limit exceeded','RATE_LIMITED',1],['invalid JSON','UNKNOWN_STOP',1]]) {
  let calls=0;const delays=[];
  assert.throws(()=>readWithRetry(()=>{calls++;throw Error(message);},{sleep:ms=>delays.push(ms)}));
  assert.equal(calls,retries);assert.equal(describeFailure(Error(message)).failureCode,code);
  assert.deepEqual(delays,retries===3?[1000,3000]:[]);cases++;
}
let transient=0;
assert.equal(readWithRetry(()=>{if(++transient<3)throw Error('HTTP 502');return 'recovered';},{sleep:()=>{}}),'recovered');cases++;
for(const outcome of ['lost','bad-json','null','{}','{"merged":true}']) {
  let writes=0;
  assert.throws(()=>batch.mergePullRequestImmediately('/unused','o/r',{number:1,title:'fix: example',body:'test',headRefOid:sha},{runCommand:(_cmd,_args,_root,o)=>{writes++;assert.equal(JSON.parse(o.input).sha,sha);if(outcome==='lost')throw Error('ECONNRESET');return outcome==='bad-json'?'{':outcome;}}),e=>e.failureCode==='WRITE_UNCERTAIN');
  assert.equal(writes,1,'an uncertain merge is never blindly retried');cases++;
}
assert.throws(()=>batch.runCommand(process.execPath,['-e','setTimeout(()=>{},10000)'],process.cwd(),{capture:true,timeoutMs:50}),e=>e.code==='ETIMEDOUT');cases++;
const directory=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'aas-lock-fault-'));
try {
  const first=openStore(directory,process.cwd()), second=openStore(directory,process.cwd());
  const release=first.acquireLock('cycle');
  first.writeBatch('cycle',{startedAt:'original',attempts:[]});
  assert.throws(()=>second.acquireLock('cycle'),e=>e.failureCode==='STATE_LOCKED');
  assert.equal(second.readBatch('cycle').startedAt,'original');
  release();second.acquireLock('cycle')();cases++;
} finally {fs.rmSync(directory,{recursive:true,force:true});}
(async()=>{
  const log=console.log;console.log=()=>{};
  try {
    let reads=0,sleeps=0;
    await assert.rejects(batch.waitForRequiredChecks('/unused','o/r',sha,spec,20,3,null,{listCheckRuns:()=>{reads++;return [];},sleep:()=>{sleeps++;}}),e=>e.failureCode==='CI_WAIT_TIMEOUT');
    assert.equal(reads,3);assert.equal(sleeps,2);cases++;
    await assert.rejects(batch.waitForRequiredChecks('/unused','o/r',sha,spec,20,3,null,{listCheckRuns:()=>[{...old,conclusion:'failure'}],sleep:()=>assert.fail('must not wait after failure')}),e=>e.failureCode==='CI_FAILED');cases++;
    await assert.rejects(batch.waitForRequiredChecks('/unused','o/r',sha,spec,20,3,null,{listCheckRuns:()=>{throw Error('HTTP 503');},sleep:()=>assert.fail('no stale green on network failure')}),/503/);cases++;
  } finally {console.log=log;}
  console.log(`maintenance fault scenarios passed: ${cases}`);
})().catch(e=>{console.error(e);process.exitCode=1;});
