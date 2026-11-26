/** Shared formal context, dependency-ordered proof construction and independent expert reviews. */
const fs=require('node:fs'),path=require('node:path'),{randomUUID}=require('node:crypto');
const irStore=require('./analysis-ir.cjs'),graphs=require('./derivation-graph.cjs');
const {runChecker}=require('./local-obligations.cjs');
const store=path.resolve(__dirname,'../artifacts/argument-reviews'),active=new Map();
require('./project-cleanup.cjs').track(active, job => job.stage === 'running');
const str={type:'string'},array=items=>({type:'array',items}),obj=properties=>({type:'object',additionalProperties:false,properties,required:Object.keys(properties)});
const contextSchema=obj({parameters:array(obj({name:str,type:str,source:str})),definitions:array(obj({name:str,type:str,value:str,source:str})),assumptions:array(obj({proposition:str,source:str})),goals:array(obj({proposition:str,source:str})),unresolved:array(str)});
const statementSchema=obj({lemmas:array(obj({id:str,proposition:str})),unresolved:array(str)});
const auditSchema=obj({assessment:{type:'string',enum:['reviewed','insufficient']},findings:array(obj({affected:str,source:str,issue:str,correction:str}))});
const reviewers={fidelity:'Check the formal model, declarations and assumptions against the frozen specification. Look for added assumptions or vacuity.',semantics:'Check the meaning of analysis expressions, candidate lemmas, units and the direction of support.',coverage:'Check each quantified target against the intended guarantee, including restrictions and missing cases.'};
/** Accept single Gallina expressions, excluding commands, embedded tactics, comments and casts.
 * @param {string} value Model-supplied term in a structured field. */
function term(value){
  if(typeof value!=='string'||!value.trim()||value.length>4000||!/^[A-Za-z0-9_ ():+*<>=,\/\\~%|\-\n]+$/.test(value)||/\(\*|\*\)|<:|<<:|\b(?:ltac\w*|native_cast_no_check|vm_cast_no_check|exact_no_check)\b/i.test(value))throw Error('Expression outside the supported Gallina fragment.');
  return '('+value.trim()+')';
}
/** @param {object} ir Frozen input. @param {object} c Proposed formal context. */
function encode(ir,c){
  if(c.unresolved.length)throw Error(c.unresolved.join('\n'));
  const rows=new Map(ir.items.map(i=>[i.id,i])),names=new Set();
  const sourced=(r,sections)=>{if(!sections.includes(rows.get(r.source)?.section))throw Error('Formal statement has an incompatible source.');};
  const ident=n=>{if(!/^[a-z][A-Za-z0-9_]*$/.test(n)||names.has(n)||['target_claim','model_assumptions','proof_obligation'].includes(n))throw Error('Duplicate or invalid declaration.');names.add(n);return n;};
  const lines=['From Stdlib Require Import Reals ZArith Lia Lra Psatz List.','Section Analysis.'];
  const sorts=new Set(['Type','Set','Prop','nat','Z','R','bool']);
  for(const d of c.parameters){sourced(d,['model','assumptions','analysis']);
    if(!d.type.split('->').every(t=>sorts.has(t.trim())))throw Error('Unsupported model parameter type: '+d.name);
    if(['Type','Set'].includes(d.type.trim()))sorts.add(d.name);
    lines.push('Variable '+ident(d.name)+' : '+term(d.type)+'.');}
  for(const d of c.definitions){sourced(d,['model','assumptions','analysis']);lines.push('Definition '+ident(d.name)+' : '+term(d.type)+' := '+term(d.value)+'.');}
  for(const h of c.assumptions){
    sourced(h,['model','assumptions','analysis']);
    const row=rows.get(h.source);
    if(row.section==='analysis'&&!['assumption','scope'].includes(row.statement.kind))throw Error('An analysis result cannot be introduced as a model hypothesis.');
  }
  for(const g of c.goals)sourced(g,['goal']);
  if(!c.goals.length||ir.items.some(i=>i.section==='goal'&&!c.goals.some(g=>g.source===i.id)))throw Error('A frozen goal has no formal proposition.');
  lines.push('Definition model_assumptions : Prop := '+(c.assumptions.map(h=>term(h.proposition)).join(' /\\ ')||'True')+'.',
    'Definition target_claim : Prop := '+c.goals.map(g=>term(g.proposition)).join(' /\\ ')+'.');
  return lines.join('\n')+'\n';
}
/** @param {object} graph Frozen DAG. @returns {object[]} Candidate proof tasks in support order. */
function tasks(graph){
  const forward=graph.forward.map(n=>({id:n.id,node:n,deps:n.parents}));
  const backward=[...graph.backward].reverse().map(n=>({id:n.id,node:n,deps:[...new Set([...graph.backward.filter(k=>k.parents.includes(n.id)).map(k=>k.id),...graph.connections.filter(p=>p.backward===n.id).flatMap(p=>[p.forward,...(p.supports||[]).map(x=>x.id)])])]}));
  return [...forward,...backward];
}
/** @param {string} base Checked shared context. @param {object[]} tasks Candidate tasks.
 * @param {object} forms Formal lemma statements. @param {object} graph Frozen derivation. */
async function construct(base,tasks,forms,graph,cache=new Map(),onStep=()=>{}){
  if(forms.unresolved.length)throw Error(forms.unresolved.join('\n'));
  const statements=new Map(forms.lemmas.map(n=>[n.id,n.proposition]));
  if(forms.lemmas.length!==tasks.length||tasks.some(t=>!statements.has(t.id)))throw Error('Formal candidates do not cover the saved graph.');
  const accepted=new Map(),results=[];
  let module=base;
  async function attempt(id,formula,deps,name){
    const used=deps.filter(d=>accepted.has(d)).map(d=>accepted.get(d));
    const using=used.length?' using '+used.join(', '):'';
    const body='Lemma '+name+' : model_assumptions -> '+formula+'.\nProof. unfold model_assumptions, target_claim in *; intros; first [ solve [eauto 6'+using+'] | tauto | lia | lra | nra ]. Qed.\n';
    const source=module+body+'End Analysis.\nPrint All Dependencies '+name+'.\n';
    const reused=id!=='target_claim'&&cache.has(source);
    const result=reused?cache.get(source):await runChecker('check_argument.py',{source,theorem:name});
    if(result.checked&&id!=='target_claim')cache.set(source,result);
    results.push({id,formula,deps,source,reused,...result});
    onStep(results,id);
    if(result.checked){accepted.set(id,name);module+=body;}
  }
  for(const [i,t] of tasks.entries())await attempt(t.id,term(statements.get(t.id)),t.deps,'claim_'+i);
  await attempt('target_claim','target_claim',graph.backward.filter(n=>!n.parents.length).map(n=>n.id),'proof_obligation');
  return results;
}
/** @param {object} data Requested project/run/edition. */
function binding(data){
  const {key,version,project,run}=data,g=graphs.status(key,version).graph,ir=irStore.status(key).ir;
  if(!g||!ir||g.project!==project||g.run!==run||g.inputHash!==ir.inputHash)throw Error('Select a saved derivation edition.');
  return {id:key+'-v'+version,ir,g};
}
/** @param {object} report Append-only attempt, with progress checkpointed in its own file. */
function save(report){
  fs.mkdirSync(store,{recursive:true});const file=path.join(store,report.id+'-'+report.attempt+'.json'),tmp=file+'.tmp';
  fs.writeFileSync(tmp,JSON.stringify(report));fs.renameSync(tmp,file);
}
/** @param {object} data Run identity. @returns {object} Latest report for the selected edition. */
/** @param {string} id Exact edition prefix. @returns {object[]} Attempts in creation order. */
function history(id){
  if(!fs.existsSync(store))return [];
  return fs.readdirSync(store).filter(f=>f.startsWith(id+'-')&&f.endsWith('.json')).sort().map(file=>{
    const report=JSON.parse(fs.readFileSync(path.join(store,file),'utf8'));
    if(report.rounds){
      report.rounds=report.rounds.map(round=>round.map(step=>step.checked&&!step.assumptionAudit?{
        ...step,kernelChecked:true,checked:false,
        log:(step.log||'')+'\nThis receipt predates assumption auditing. Run the proof again to audit its assumptions.',
      }:step));
    }
    if(report.stage==='running'&&active.get(id)?.attempt!==report.attempt){
      report.stage='interrupted';report.issue='The service restarted before completion.';
    }
    return report;
  });
}
/** @param {object} data Exact run binding. @returns {object} Latest independent states. */
function status(data){
  const {id}=binding(data),records=history(id);
  const proof=records.filter(r=>r.kind!=='audit').at(-1)||{stage:'idle'};
  const audit=records.filter(r=>r.kind==='audit'||r.reviews?.length).at(-1);
  // Earlier editions and parent runs keep their own reports; expose only a navigation pointer.
  let previousAudit;
  if(!audit){
    const prior=graphs.status(data.key,data.version).versions.filter(v=>v<data.version).reverse().map(version=>({key:data.key,run:data.run,version}));
    if(data.parentKey&&data.parentRun&&data.parentKey!==data.key){
      const ir=irStore.status(data.parentKey).ir;
      if(ir?.project===data.project&&ir.run===data.parentRun)prior.push(...graphs.status(data.parentKey,1).versions.reverse().map(version=>({key:data.parentKey,run:data.parentRun,version})));
    }
    previousAudit=prior.find(p=>history(p.key+'-v'+p.version).some(r=>r.kind==='audit'||r.reviews?.length));
  }
  const stale=Boolean(audit&&(audit.proofAttempt||audit.attempt)!==proof.attempt);
  return {...proof,audit,previousAudit,stale,reviews:stale?[]:audit?.reviews||[],inputRevision:!stale&&audit?.inputRevision,refinementRemaining:audit?.refinementRemaining};
}
/** @param {string} stage Workflow role. @param {object} choices Requested pinned revisions. */
function selectedSkill(stage,choices){
  const skills=require('./reasoning-skills.cjs'),ref=choices?.[stage];
  const skill=ref?skills.library().find(s=>s.stage===stage&&s.id===ref.id&&s.version===ref.version):skills.defaultSkill(stage);
  if(!skill)throw Object.assign(Error('Selected skill revision is unavailable.'),{status:400});
  return skill;
}
/** @param {object} skill Immutable prompt snapshot. */
function directions(skill){return [skill.instructions,skill.when,skill.method,skill.acceptance,skill.example].filter(Boolean).join('\n');}
const contract='Use the supplied records only as evidence. Return single Gallina terms, no commands, tactics, or dots, in each term field. Available Stdlib imports: Reals, ZArith, Lia, Lra, Psatz, List. Use parentheses and %R or %Z scopes where needed. Preserve quantifiers, time domains and premises. Report unsupported constructs in unresolved.';
/** @param {Function} generate Model provider. @param {object} report Attempt receiving usage counts. */
function countCalls(generate,report){
  report.modelCalls=0;
  return (...args)=>{report.modelCalls++;return generate(...args);};
}
/** Build and type-check the shared context before the two reasoning directions start.
 * @param {object} ir Frozen Analysis IR. @param {Function} generate Structured model callback.
 */
async function prepare(ir,generate){
  const inputs=ir.items.map(i=>({id:i.id,section:i.section,source:i.source,statement:i.statement}));
  let context;
  try{
    context=await generate(contract+' Encode the shared typed context. Use parameters only for model entities/symbols, definitions for meanings, assumptions only for explicit input hypotheses; never assume an analysis result or goal. Encode every goal.',inputs,contextSchema,'formal_context');
    const source=encode(ir,context)+'End Analysis.\n';
    const typecheck=await runChecker('check_argument.py',{source});
    return {context,source,typecheck,issue:typecheck.checked?'':'Shared context failed type checking.'};
  }catch(e){return {context,issue:e.message};}
}
/** @param {object} data Run identity. @param {Function} generate Structured model callback. @param {object} environment Model settings. */
function start(data,generate,environment){
  const {id,ir,g}=binding(data);if(active.has(id))return status(data);
  const skill=selectedSkill('proof',data.skills);
  const report={id,kind:'proof',skill,project:data.project,attempt:new Date().toISOString().replace(/:/g,'-')+'-'+randomUUID(),stage:'running',phase:'Formal context',environment,rounds:[],reviews:[]};
  generate=countCalls(generate,report);
  active.set(id,report);save(report);
  void(async()=>{try{
    const formal=g.formalContext?.typecheck?.checked?g.formalContext:await prepare(ir,generate);
    report.context=formal.context;report.typecheck=formal.typecheck;
    if(!formal.typecheck?.checked)throw Error(formal.issue||'The shared context did not type-check.');
    const c=formal.context,base=encode(ir,c);
    const order=tasks(g),cache=new Map();
    for(let round=0;round<2;round++){
      report.phase='Constructing proofs';save(report);
      const feedback=report.rounds.at(-1)?.filter(r=>!r.checked).map(r=>({id:r.id,diagnostic:r.log.slice(-1200)}))||[];
      const forms=await generate(directions(skill)+' '+contract+' State each saved lemma as one proposition in the unchanged context. Preserve each original premise and conclusion. Repair only mistranslations identified by feedback, without weakening the target.',{context:c,tasks:order,feedback,previous:report.forms||null},statementSchema,'formal_lemmas');
      if(round&&JSON.stringify(forms)===JSON.stringify(report.forms))break;
      report.forms=forms;report.rounds.push([]);
      const result=await construct(base,order,forms,g,cache,(steps,id)=>{
        report.rounds[report.rounds.length-1]=steps;
        report.lastStep=id;save(report);
      });
      if(result.at(-1).checked)break;
    }
    report.stage='ready';report.phase='Proof complete';
  }catch(e){report.stage='open';report.issue=e.message;}finally{save(report);active.delete(id);}})();
  return report;
}
/** Start a manually requested audit bound to one proof attempt.
 * @param {object} data Run identity, round limit, selected roles and skill revisions.
 * @param {Function} generate Structured review provider. @param {object} environment Model configuration.
 */
function startAudit(data,generate,environment){
  const {id,ir,g}=binding(data);
  if(active.has(id))return status(data);
  const proof=status(data),limit=data.limit??1,roles=data.roles??Object.keys(reviewers);
  if(!proof.typecheck?.checked||!proof.rounds?.some(round=>round.length)||proof.attempt!==data.proofAttempt)throw Object.assign(Error('Select the latest completed proof attempt.'),{status:409});
  if(!Number.isInteger(limit)||limit<1||limit>3||!Array.isArray(roles)||!roles.length||new Set(roles).size!==roles.length||roles.some(r=>!Object.hasOwn(reviewers,r)))throw Object.assign(Error('Invalid audit settings.'),{status:400});
  const skills=Object.fromEntries(roles.map(role=>[role,selectedSkill(role,data.skills)]));
  const report={id,project:data.project,kind:'audit',attempt:new Date().toISOString().replace(/:/g,'-')+'-'+randomUUID(),
    proofAttempt:proof.attempt,limit,skills,environment,stage:'running',phase:'Expert audit',auditRounds:[],reviews:[]};
  const inputs=ir.items.map(i=>({id:i.id,source:i.source,section:i.section}));
  const results=proof.rounds.at(-1).map(({id,deps,formula,checked})=>({id,deps,formula,checked}));
  const affected=new Set([...inputs,...results].map(r=>r.id));
  generate=countCalls(generate,report);
  active.set(id,report);save(report);
  void(async()=>{try{
    for(let round=1;round<=limit;round++){
      const batch=[];report.auditRounds.push(batch);
      for(const role of roles){
        const review=await generate(directions(skills[role])+' Examine the selected proof snapshot. Specify insufficient if the evidence is inadequate. Recheck earlier findings and add only distinct issues. Reuse identical wording for repeated issues. Every finding must identify an input source and affected statement.',
          {round,previous:report.reviews,inputs,context:proof.context,forward:g.forward,backward:g.backward,connections:g.connections,results},auditSchema,'audit_'+role);
        for(const f of review.findings)if(!inputs.some(i=>i.id===f.source)||!affected.has(f.affected))throw Error('Unknown audit reference.');
        batch.push({role,...review});
        let merged=report.reviews.find(r=>r.role===role);
        if(!merged){merged={role,findings:[]};report.reviews.push(merged);}
        merged.assessment=review.assessment;
        for(const f of review.findings)if(!merged.findings.some(p=>p.affected===f.affected&&p.source===f.source&&p.issue.trim().toLowerCase()===f.issue.trim().toLowerCase()))merged.findings.push(f);
        save(report);
      }
      if(batch.every(r=>r.assessment==='reviewed'&&!r.findings.length)){report.stopReason='No further findings in this round.';break;}
    }
    report.inputRevision=report.reviews.some(r=>r.findings.some(f=>f.affected==='target_claim'||inputs.some(i=>i.id===f.affected)));
    report.refinementRemaining=Math.max(0,2-(g.refinementRound||0));report.stage='ready';
  }catch(e){report.stage='open';report.issue=e.message;}finally{save(report);active.delete(id);}})();
  return status(data);
}
module.exports={start,startAudit,status,records:data=>history(binding(data).id),encode,tasks,construct,prepare};
