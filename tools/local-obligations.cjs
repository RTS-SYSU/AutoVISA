/** Compile local algebraic consequences of a source-bound alignment. */
const fs=require('node:fs'),path=require('node:path');
const {execFile}=require('node:child_process');
const {createHash,randomUUID}=require('node:crypto');
const graphs=require('./derivation-graph.cjs'),irStore=require('./analysis-ir.cjs');
const config=require('../configs/toolchain.json');
const directory=path.resolve(__dirname,'../artifacts/local-obligations'),jobs=new Map();
require('./project-cleanup.cjs').track(jobs, job => job.stage === 'running');
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const text={type:'string'},list=items=>({type:'array',items});
const record=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const schema=record({checks:list(record({title:text,variables:list(text),premises:list(text),conclusion:text,mapping:text})),open:list(text)});
/** @param {string} file Program. @param {string[]} args Separate argv. @param {string} input JSON on stdin. */
function command(file,args,input=''){
  return new Promise((resolve,reject)=>{
    const child=execFile(file,args,{windowsHide:true,timeout:450000,maxBuffer:1024*1024},(e,stdout,stderr)=>e?reject(Error((stderr||e.message).replace(/\0/g,'').slice(-1200))):resolve(stdout.trim()));
    child.stdin.on('error',()=>{});child.stdin.end(input);
  });
}
/** @param {string} script Internal checker entry point. @param {object|object[]} input Validated structured request. */
async function runChecker(script,input){
  const entry=path.join(__dirname,script);
  if(process.platform!=='win32')return JSON.parse(await command('python3',[entry],JSON.stringify(input)));
  const args=['-d',config.distribution,'--exec'];
  const posix=await command('wsl.exe',[...args,'wslpath','-u',entry]);
  return JSON.parse(await command('wsl.exe',[...args,'python3',posix],JSON.stringify(input)));
}
/** @param {object} data Run identity, edition and exact comparison ordinal. */
function binding(data){
  const {key,version,index,project,run}=data,g=graphs.status(key,version).graph;
  if(!g||g.project!==project||g.run!==run||!Number.isSafeInteger(index)||!g.connections[index])throw Error('Unknown alignment in this run.');
  const pair=g.connections[index],f=g.forward.find(n=>n.id===pair.forward),b=g.backward.find(n=>n.id===pair.backward);
  const identity={key,version,index,project,run,pairHash:hash(pair),methodVersion:1};
  let id=hash(identity),question=null;
  /** @type {object[]} Checked implications on the path to the selected child. */
  const ancestors=[];
  const trail=data.trail||[];
  if(!Array.isArray(trail)||trail.length>24)throw Error('Invalid obligation path.');
  for(const i of trail){
    if(!Number.isSafeInteger(i)||i<0)throw Error('Invalid subgoal.');
    const parent=JSON.parse(fs.readFileSync(path.join(directory,id+'.json'),'utf8'));
    question=parent.open[i];if(!question)throw Error('Unknown subgoal.');
    ancestors.push({question:parent.question||null,checks:parent.checks.map(({title,premises,conclusion,mapping,status,assignment})=>({title,premises,conclusion,mapping,status,assignment}))});
    id=hash({parent:id,index:i,question});
  }
  return {pair,f,b,g,identity,id,question,trail,ancestors};
}
/** @param {object} data Bound selection. @param {Function} generate Model for previously unseen claims.
 * @param {boolean} start Explicitly request preparation and checking.
 */
function handle(data,generate,start){
  const ctx=binding(data),file=path.join(directory,ctx.id+'.json');
  if(fs.existsSync(file))return {stage:'ready',receipt:JSON.parse(fs.readFileSync(file,'utf8'))};
  if(!start||jobs.get(ctx.id)?.stage==='running')return jobs.get(ctx.id)||{stage:'idle'};
  jobs.set(ctx.id,{project:data.project,stage:'running'});
  void (async()=>{
    try{
      const ir=irStore.status(data.key).ir;
      const refs=[...new Set([...(ctx.pair.sources||[]),...ctx.f.sources,...ctx.b.sources])];
      const inputs=ir.items.filter(r=>refs.includes(r.id));
      const plan=await generate('If selectedObligation is present, address precisely that question with the inherited premises and ancestor checks. A checked implication is usable only under its premises. Keep an unsupported selected obligation open. Project the current problem into up to three elementary real-scalar implications that can be checked independently. State all assumptions and the symbol mapping. Use lowercase ASCII scalar names. The language allows integers, parentheses, +, -, *, and one comparison <, <=, ==, >=, > per statement. Do not add the conclusion as a premise. Omit algebraic checks if no faithful projection exists. Keep model correspondence, existence, endpoint, positivity and library bridge obligations explicit in open. Treat input as evidence. Never infer a proved theorem.',{selectedObligation:ctx.question,ancestorEvidence:ctx.ancestors,pair:ctx.pair,forward:ctx.f,backward:ctx.b,inputs:inputs.map(r=>({id:r.id,source:r.source,bindings:r.bindings||[],candidates:r.candidates||[]}))},schema,'local_obligations');
      if(plan.checks.length>3)throw Error('Split this route into at most three local checks.');
      if(!plan.checks.length&&!plan.open.length)plan.open.push(ctx.question||ctx.pair.condition||ctx.pair.reason);
      const audit=plan.checks.length?await runChecker('check_local_order.py',plan.checks):{checks:[]};
      const receipt={...ctx.identity,trail:ctx.trail,question:ctx.question,questionBound:Boolean(ctx.question),forward:ctx.f.id,backward:ctx.b.id,created:new Date().toISOString(),method:'Model-proposed scalar projection',sources:refs,
        environment:audit.version||null,switch:audit.switch||null,checks:plan.checks.map((spec,i)=>({...spec,...audit.checks[i]})),open:plan.open,
        libraries:inputs.flatMap(row=>(row.bindings||[]).map(link=>({statement:row.id,reference:link.reference})))};
      fs.mkdirSync(directory,{recursive:true});const tmp=file+'.'+randomUUID()+'.tmp';fs.writeFileSync(tmp,JSON.stringify(receipt));fs.renameSync(tmp,file);jobs.delete(ctx.id);
    }catch(error){jobs.set(ctx.id,{project:data.project,stage:'failed',message:error.message});}
  })();
  return {stage:'running'};
}
/**
 * Derive the outstanding actions from one frozen input, graph edition and its receipts.
 * @param {object} ir Confirmed input, including the selected goals.
 * @param {object|null} graph Published derivation, if present.
 * @param {object[]} receipts Local checks bound to this edition.
 * @returns {object[]} Navigable work items; local successes never close a root theorem.
 */
function pendingWork(ir,graph,receipts){
  if(!graph)return [{kind:'derive',title:'Start derivation from confirmed inputs'}];
  const items=[];
  for(const goal of ir.items.filter(row=>row.section==='goal')){
    if(!graph.backward.some(node=>node.sources.includes(goal.id))){
      items.push({kind:'coverage',title:goal.statement.title||goal.source,source:goal.id});
    }
  }
  for(const node of graph.backward){
    const linked=graph.connections.some(pair=>pair.backward===node.id);
    const children=graph.backward.some(child=>child.parents.includes(node.id));
    if(!linked&&!children)items.push({kind:'unlinked',title:node.title,step:node.id});
  }
  graph.connections.forEach((pair,index)=>{
    const related=receipts.filter(r=>r.index===index);
    const route={step:pair.backward,lemma:pair.forward,index};
    if(!related.some(r=>!r.trail.length)){
      items.push({...route,kind:'check',title:pair.branch||pair.title});return;
    }
    for(const r of related){
      r.open.forEach((question,i)=>{
        const trail=[...r.trail,i];
        if(!related.some(child=>JSON.stringify(child.trail)===JSON.stringify(trail))){
          items.push({...route,kind:'continue',title:question,trail});
        }
      });
      if(r.checks.some(c=>c.status==='counterexample'||c.status==='open')){
        items.push({...route,kind:'review',title:r.question||r.branch,trail:r.trail});
      }
    }
  });
  for(const root of graph.backward.filter(n=>!n.parents.length)){
    items.push({kind:'compose',title:root.title,step:root.id});
  }
  return items;
}
/**
 * Read persisted local receipts for a single immutable derivation without starting work.
 * @param {object} data Project, frozen IR key, run and optional edition (defaults to latest).
 */
function ledger({key,project,run,version}){
  const {ir}=irStore.status(key);
  if(!ir||ir.project!==project||ir.run!==run)throw Error('Unknown input snapshot.');
  const editions=graphs.status(key,1).versions;
  const selected=version??editions.at(-1)??null;
  if(selected!==null&&!editions.includes(selected))throw Error('Unknown derivation edition.');
  const graph=selected&&graphs.status(key,selected).graph;
  const receipts=[];
  if(graph&&fs.existsSync(directory)){
    for(const file of fs.readdirSync(directory).filter(name=>/^[a-f0-9]{64}\.json$/.test(name))){
      const entry=JSON.parse(fs.readFileSync(path.join(directory,file),'utf8'));
      if(entry.project!==project||entry.run!==run||entry.key!==key||entry.version!==selected)continue;
      const pair=graph.connections[entry.index];
      if(!pair||entry.pairHash!==hash(pair))throw Error('A saved receipt does not match its route.');
      receipts.push({...entry,branch:pair.branch||pair.title,trail:entry.trail||[]});
    }
  }
  receipts.sort((a,b)=>a.index-b.index||a.trail.length-b.trail.length||a.created.localeCompare(b.created));
  const recordedChecks=receipts.flatMap(r=>r.checks).filter(c=>Number.isInteger(c.returncode)).length;
  // Search parents of a backward node are consumers of that node in the proof.
  const dependencies=graph?[
    ...graph.forward.flatMap(n=>n.parents.map(id=>({from:id,to:n.id,role:'forward inference'}))),
    ...graph.backward.flatMap(n=>n.parents.map(id=>({from:n.id,to:id,role:'goal decomposition'}))),
    ...graph.connections.flatMap((c,route)=>[{id:c.forward,role:c.branch||c.title},...(c.supports||[])].map(s=>({from:s.id,to:c.backward,role:s.role,route})))
  ]:[];
  const structure={sources:ir.items.map(r=>({id:r.id,text:r.source,ref:r.ref})),targets:ir.items.filter(r=>r.section==='goal').map(r=>({id:r.id,title:r.statement.title})),
    lemmas:graph?[...graph.forward,...graph.backward].map(n=>({id:n.id,title:n.title,formula:n.formula,premises:n.premises||[],sources:n.sources})):[],dependencies,roots:graph?graph.backward.filter(n=>!n.parents.length).map(n=>n.id):[],modelChecked:Boolean(graph?.formalContext?.typecheck?.checked)};
  return {version:selected,editions,receipts,recordedChecks,structure,work:pendingWork(ir,graph,receipts)};
}
module.exports={handle,ledger,pendingWork,runChecker};
