const assert=require('node:assert/strict');
const cycle=require('../maintenance_cycle.cjs');
assert.throws(()=>cycle.parse(['merge','--state-dir','/tmp/state','--admin','yes']),/Unknown/);
assert.throws(()=>cycle.parse(['release','--state-dir','/tmp/state']),/Use start/);
assert.throws(()=>cycle.parse(['merge','--state-dir','/tmp/state','--reviewed-head','short']),/exact/);
assert.match(cycle.nextAction({reason:'new_unapproved_path'}),/continue other PRs/);
const sha='a'.repeat(40);
const runs=['ci.yml','codeql.yml'].map((f,i)=>({id:i+1,path:'.github/workflows/'+f,head_sha:sha,head_branch:'main',event:'push',status:'completed',conclusion:'success'}));
assert.equal(cycle.proofForRuns(runs,sha).length,2);
for(const mutation of [{head_sha:'b'.repeat(40)},{event:'pull_request'},{head_branch:'topic'},{status:'in_progress'},{conclusion:'failure'}]) {
 const invalid=[{...runs[0],...mutation},runs[1]];
 assert.throws(()=>cycle.proofForRuns(invalid,sha),/missing, pending or failed/);
}
assert.throws(()=>cycle.proofForRuns([...runs,{...runs[0],id:10,conclusion:'failure'}],sha),/failed/);
const batch=require('../merge_batch.cjs');
const results=batch.prepareBatch('/unused','owner/repo',[1,2],{dryRun:true}, {
 load:(_,__,n)=>({number:n,headRefOid:sha}),
 approve:(_,__,pr)=>{if(pr.number===1)throw Error('blocked path'); return {approvedRuns:[]};}
});
assert.equal(results[0].status,'blocked');assert.equal(results[1].prepared,true);
console.log('maintenance cycle fail-closed completion and independent intake passed');

const behind=batch.prepareBatch('/unused','owner/repo',[1,2],{dryRun:true},{
 load:(_,__,n)=>({number:n,headRefOid:sha,mergeStateStatus:n===1?'BEHIND':'CLEAN'}),
 approve:(_,__,pr)=>{assert.equal(pr.number,2,'do not approve/wait on stale head');return {approvedRuns:[]};}
});
assert.equal(behind[0].status,'blocked');assert.match(behind[0].reason,/BEHIND/);assert.equal(behind[1].prepared,true);
