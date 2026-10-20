const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'../../..');
const scripts=require('../../../package.json').scripts;
const canonical='skills/antigravity-maintainer-batch-release';
for(const name of ['maintenance-cycle.md','maintenance-contract.md','component-validation.md']) {
 assert.equal(fs.readFileSync(path.join(root,canonical,'references',name),'utf8'),fs.readFileSync(path.join(root,'docs/maintainers',name),'utf8'),name+' must match canonical instructions');
}
const files=['AGENTS.md','.github/MAINTENANCE.md',canonical+'/SKILL.md',...fs.readdirSync(path.join(root,canonical,'references')).map(n=>canonical+'/references/'+n),'docs/maintainers/maintainer-sweep.md','docs/maintainers/merge-batch.md'];
for(const file of files) {
 const text=fs.readFileSync(path.join(root,file),'utf8');
 for(const match of text.matchAll(/npm run ([a-z][a-z0-9:-]*)/g))assert.ok(scripts[match[1]],file+': missing command '+match[1]);
}
const sweep=fs.readFileSync(path.join(root,'docs/maintainers/maintainer-sweep.md'),'utf8');
assert.doesNotMatch(sweep,/attestation only on Jev/i);
assert.match(sweep,/Review \*\*every\*\* changed skill tree/);
