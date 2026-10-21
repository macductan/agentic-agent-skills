const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync,spawnSync}=require('node:child_process');
const cli=path.resolve(__dirname,'../maintenance_validate.cjs');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'aas-validation-cli-'));
function fixture(label,scripts={}) {
 const repo=path.join(directory,label);fs.mkdirSync(repo);
 const git=(...args)=>execFileSync('git',args,{cwd:repo,stdio:'pipe'}).toString().trim();
 git('init');git('config','user.email','fixture@example.test');git('config','user.name','fixture');
 fs.writeFileSync(path.join(repo,'package.json'),JSON.stringify({name:'fixture',version:'1.0.0',scripts}));git('add','.');git('commit','-m','base');
 const base=git('rev-parse','HEAD');
 return {repo,git,base};
}
function change(f,file,executable=false) {
 fs.mkdirSync(path.dirname(path.join(f.repo,file)),{recursive:true});fs.writeFileSync(path.join(f.repo,file),'fixture');f.git('add','.');
 if(executable)f.git('update-index','--chmod=+x',file);
 f.git('commit','-m','change');
}
function run(f,plan) {
 const result=spawnSync(process.execPath,[cli,'--repo',f.repo,'--base',f.base,'--head','HEAD',...(plan?['--plan']:[])],{encoding:'utf8',env:process.env});
 const index=result.stdout.indexOf('{\n  "schemaVersion"');
 return {...result,receipt:index<0?null:JSON.parse(result.stdout.slice(index))};
}
try {
 for(const [label,file,executable,expected] of [['catalog','skills/example/SKILL.md',false,'catalog'],['unknown','new-unknown.config',false,'full'],['executable','skills/example/check.sh',true,'full'],['runtime','tools/bin/install.js',false,'runtime']]) {
  const f=fixture(label);change(f,file,executable);const r=run(f,true);assert.equal(r.status,0,r.stderr);assert.equal(r.receipt.profile,expected);assert.equal(r.receipt.passed,undefined,'planning is not validation evidence');
 }
 for(const [label,scripts] of [['failing',{validate:'node -e "process.exit(7)"','check:warning-budget':'node -e "require(\'node:fs\').writeFileSync(\'later-check\',\'unexpected\')"'}],['missing',{}]]) {
  const f=fixture(label,scripts);change(f,'tools/bin/install.js');const r=run(f,false);
  assert.notEqual(r.status,0);assert.equal(r.receipt.passed,false);assert.equal(r.receipt.results.length,1);assert.notEqual(r.receipt.results[0].exitCode,0);
  assert.equal(fs.existsSync(path.join(f.repo,'later-check')),false,'a failed prerequisite must prevent later commands');
 }
 console.log('Real validation CLI: unknown/executable inputs select full checks; missing/failing commands never return a successful receipt');
} finally {fs.rmSync(directory,{recursive:true,force:true});}
