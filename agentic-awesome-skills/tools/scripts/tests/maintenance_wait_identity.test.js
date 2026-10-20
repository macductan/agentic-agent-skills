const assert=require('node:assert/strict');
const batch=require('../merge_batch.cjs');
const sha='a'.repeat(40), base='b'.repeat(40);
const pr={number:1,state:'OPEN',baseRefName:'main',baseRefOid:base,headRefOid:sha,mergeStateStatus:'CLEAN'};
const tuple={baseOid:base,headOid:sha};
for(const ids of ['123oops','1,2x','1.5','0','-1','9007199254740992']) assert.throws(()=>batch.parsePrList(ids),/positive safe integers/);
assert.deepEqual(batch.parsePrList('1, 2 1'),[1,2]);
batch.assertPendingPullRequest(pr,tuple,1);
(async()=>{
 for(const mutation of [{headRefOid:'c'.repeat(40)},{baseRefOid:'c'.repeat(40)},{state:'CLOSED'},{mergeStateStatus:'BEHIND'},{mergeable:'CONFLICTING'}]) {
  let calls=0,sleeps=0;
  await assert.rejects(batch.waitForRequiredChecks('/unused','owner/repo',sha,[{label:'ci',aliases:['ci'],appId:15368}],20,180,
   ()=>batch.assertPendingPullRequest({...pr,...mutation},tuple,1),
   {listCheckRuns:()=>{calls++;return [];},sleep:()=>{sleeps++;}}));
  assert.equal(calls,1,'stop waiting immediately after detecting drift');assert.equal(sleeps,0);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
