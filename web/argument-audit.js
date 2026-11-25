/** Independent proof and audit controls for a single frozen run edition. */
function createArgumentAudit({request,esc,refresh}){
  const reports=new Map(),preferences=new Map(),histories=new Map(),timers=new Map();
  const names={proof:'Proof',fidelity:'Model fidelity',semantics:'Scheduling semantics',coverage:'Goal coverage'};
  const roles=['fidelity','semantics','coverage'];
  const identity=d=>JSON.stringify([d.key,d.version]);
  /** @param {object} d Frozen edition. @returns {object} Editing preferences for the next attempt. */
  function options(d){
    const key=identity(d);
    if(!preferences.has(key))preferences.set(key,{skills:{},roles:[...roles],limit:1});
    return preferences.get(key);
  }
  /** @param {object} d Run binding. @param {string} action Explicit launch or status refresh. */
  async function load(d,action='status',selection={}){
    const id=identity(d),previous=reports.get(id),settings=options(d);
    clearTimeout(timers.get(id));
    reports.set(id,{...previous,stage:'loading'});if(action!=='status')refresh();
    try{
      const route={status:'argument-review-status',proof:'argument-review',audit:'start-audit'}[action];
      const report=await request(route,{...d,...settings,...selection,proofAttempt:previous?.attempt});
      reports.set(id,report);histories.delete(id);
      if(report.stage==='running'||report.audit?.stage==='running')timers.set(id,setTimeout(()=>load(d),2000));
    }catch(e){reports.set(id,{stage:'error',issue:e.message});}
    refresh();
  }
  /** @param {object} d Bound run. @returns {object} Latest workflow state. */
  function current(d){
    const id=identity(d);
    if(!reports.has(id)){reports.set(id,{stage:'loading'});queueMicrotask(()=>load(d));}
    return reports.get(id);
  }
  const nav=(page,label)=>'<button type="button" class="control" data-page="'+page+'">'+label+'</button>';
  const start=(d,action,label)=>'<button type="button" class="control primary" data-workflow="'+action+'" data-version="'+d.version+'">'+label+'</button>';
  const setup=(d,mode)=>'<button type="button" class="cite" data-workflow-settings="'+mode+'" data-version="'+d.version+'">'+names[mode]+' settings</button>';
  names.audit='Audit';
  /** @param {object} d Run identity. @param {string} anchor Optional evidence section. */
  function details(d,anchor=''){return '?'+esc(new URLSearchParams({view:'proof-details',project:d.project,run:d.run,version:d.version}).toString())+(anchor?'#'+anchor:'');}
  /** @param {string} attempt Historic UTC timestamp followed by its unique suffix.
   * @returns {string} Local date and time to distinguish retries of the same run.
   */
  function attemptTime(attempt){
    const match=/^(\d{4}-\d\d-\d\dT\d\d)-(\d\d)-(\d\d\.\d{3}Z)/.exec(attempt||'');
    if(!match)return '';
    const date=new Date(match[1]+':'+match[2]+':'+match[3]);
    return date.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  }
  /** @param {object} previous Compact outcome recorded for the preceding proof attempt. */
  function previousLine(previous){
    if(!previous)return '';
    let outcome;
    if(previous.stage==='interrupted')outcome='Interrupted by a service restart.';
    else if(previous.questions)outcome='Stopped with '+previous.questions+' model clarification item(s).';
    else if(previous.issue)outcome=previous.issue;
    else if(previous.finalChecked)outcome='Final theorem verified.';
    else if(previous.open)outcome=previous.open+' obligation(s) remained open.';
    else if(previous.scope==='model'&&previous.modelChecked)outcome='Formal model checked.';
    else outcome='Recorded status: '+previous.stage+'.';
    return '<p><small>'+esc(attemptTime(previous.attempt))+' — '+esc(outcome)+'</small></p>';
  }
  /** @param {object} report Current attempt only. @returns {string} Its observed stage and next action. */
  function currentMessage(report){
    const operation=report.progress?.operation;
    if(report.stage==='running'){
      if(operation==='prepare-model')return 'Waiting for the model response. Rocq checking has not started. This page updates automatically.';
      if(operation==='check-model')return 'Rocq is type-checking the formal model. This page updates automatically.';
      if(operation==='prepare-statements')return 'Preparing statements for the selected obligations. This page updates automatically.';
      return 'Checks are in progress. This page updates automatically.';
    }
    if(report.stage==='open'&&report.context?.unresolved?.length)
      return 'Review the '+report.context.unresolved.length+' model clarification '+(report.context.unresolved.length===1?'item':'items')+' below to continue. Rocq checking has not started.';
    if(report.stage==='interrupted'||report.stage==='open')return report.issue?.split('\n')[0]||'Open the diagnostic below for this attempt.';
    if(report.stage==='ready'&&report.scope==='model')return 'Rocq checked the model. Choose a lemma or the final theorem to continue.';
    return '';
  }
  /** Render counts from completed checker receipts in the most recent recorded round.
   * @param {object} report Saved attempt or an idle state. @param {object} structure DAG of this edition.
   * @returns {string} Stage indicator and accessible obligation counter.
   */
  function proofProgress(report,structure){
    const rounds=report.rounds||[], rows=rounds.at(-1)||[], total=structure.lemmas.length+1;
    const verified=rows.filter(row=>row.checked).length, root=rows.find(row=>row.id==='target_claim');
    const progress=report.progress||{}, idle=report.stage==='idle', running=report.stage==='running';
    /** @type {boolean} A stopped or partially completed attempt still needs user attention. */
    const blocked=['open','interrupted'].includes(report.stage)||(!running&&rows.some(row=>!row.checked));
    const modelOnly=report.scope==='model'&&report.typecheck?.checked;
    const stage=(!running&&root)||progress.operation==='check-target'?2:
      modelOnly||(!rounds.length&&!report.typecheck?.checked)?0:1;
    const stages=['Formal model','Lemmas & subgoals','Final theorem'];
    const selected=structure.lemmas.find(node=>node.id===progress.step);
    const checkingNode=progress.operation==='check-lemma'&&selected?'Checking '+selected.id+' · '+selected.title+'.':'';
    const time=attemptTime(report.attempt);
    /** @type {string} Only a positive checker receipt for the root establishes theorem success. */
    const headline=root?.checked?'Proof verified':idle?'Ready to start':running?'Proof in progress':
      report.stage==='interrupted'?'Proof interrupted':report.stage==='open'?'Proof stopped':
      blocked?'Proof needs attention':modelOnly?'Formal model checked':'Selected checks complete';
    const tone=root?.checked?'verified':idle?'idle':running?'running':blocked?'blocked':'partial';
    const verdict=root?.checked?'Verified by Rocq':root?'Open':progress.operation==='check-target'&&running?'Checking in Rocq':'Not yet verified';
    const count=rows.length+' / '+total;
    const message=checkingNode&&running?checkingNode:currentMessage(report);
    const round=progress.round>1?' · Round '+progress.round:'';
    return '<section class="proof-progress" data-tone="'+tone+'" aria-label="Proof progress">'+
      '<div class="proof-heading"><div><p class="proof-stage">Step '+(stage+1)+' of 3 · '+esc(stages[stage]+round)+'</p>'+
      '<h3 role="status">'+esc(headline)+'</h3></div><div class="proof-verdict"><span>Final theorem</span><strong>'+esc(verdict)+'</strong></div></div>'+
      (message?'<p class="proof-message">'+esc(message)+'</p>':'')+
      '<div class="proof-count"><span><strong>'+count+'</strong> obligations checked</span>'+
      (rows.length?'<span>'+verified+' verified · '+(rows.length-verified)+' open</span>':'')+'</div>'+
      '<progress aria-label="Obligations checked in the latest round" value="'+rows.length+'" max="'+total+'"></progress>'+
      (time?'<div class="proof-attempt">Attempt started · '+esc(time)+'</div>':'')+
      (report.previousProof?'<details class="proof-history"><summary>Previous attempt</summary>'+previousLine(report.previousProof)+'</details>':'')+'</section>';
  }
  /** @type {Map<string,object>} Keep the reader's selected stage and node across status polls. */
  const selections=new Map();
  /** @param {object} d Frozen run binding. @param {string} stage Stage name. @param {string} node Selected DAG identifier. */
  function select(d,stage,node){
    selections.set(identity(d),{stage,node});refresh();
  }
  /** @param {object} structure Saved lemmas and support edges, including multiple supporters per goal. */
  function topology(structure){
    const nodes=new Map(structure.lemmas.map(node=>[node.id,node]));
    nodes.set('target_claim',{id:'target_claim',title:structure.targets.map(t=>t.title).join(' · ')});
    const edges=[...structure.dependencies,...(structure.roots||[]).map(from=>({from,to:'target_claim'}))];
    const parents=new Map([...nodes.keys()].map(id=>[id,new Set()]));
    for(const {from,to} of edges)if(nodes.has(from)&&nodes.has(to))parents.get(to).add(from);
    return {nodes,parents};
  }
  /** Draw the frozen support DAG with prerequisites above their consumers.
   * @param {object} dag Node and predecessor maps. @param {string} selected Focused node.
   * @param {Map} receipts Checker results from this attempt. @param {object} d Run binding.
   */
  function plot(dag,selected,receipts,d){
    const levels=new Map(),layers=[];
    // Both directional graphs use immutable topological dependencies.
    function level(id){
      if(!levels.has(id))levels.set(id,1+Math.max(-1,...[...dag.parents.get(id)].map(level)));
      return levels.get(id);
    }
    for(const id of dag.nodes.keys())(layers[level(id)]??=[]).push(id);
    const width=Math.max(310,...layers.map(layer=>layer.length*76)),height=layers.length*61+12,points=new Map();
    layers.forEach((layer,row)=>layer.forEach((id,i)=>points.set(id,{x:width/2+(i-(layer.length-1)/2)*76,y:30+(layers.length-1-row)*61})));
    let paths='';
    for(const [id,deps] of dag.parents)for(const parent of deps){
      const a=points.get(parent),b=points.get(id),y=(a.y+b.y)/2,focus=id===selected||parent===selected;
      paths+='<path class="'+(focus?'focus':'')+'" d="M '+a.x+' '+(a.y-14)+' C '+a.x+' '+y+' '+b.x+' '+y+' '+b.x+' '+(b.y+18)+'" marker-end="url(#proof-arrow)"/>';
    }
    const buttons=[...points].map(([id,{x,y}])=>{
      const receipt=receipts.get(id),status=receipt?(receipt.checked?'verified':'open'):'pending',node=dag.nodes.get(id);
      return '<button type="button" class="dag-dot '+status+'" data-proof-node="'+esc(id)+'" data-version="'+d.version+'" aria-pressed="'+(id===selected)+'" aria-label="'+esc(node.title+' · '+status)+'" title="'+esc(node.title+' · '+status)+'" style="left:'+x+'px;top:'+y+'px">'+esc(id==='target_claim'?'Final':id)+'</button>';
    }).join('');
    return '<div class="proof-graph-scroll" aria-label="Proof dependency graph"><div class="proof-graph" style="width:'+width+'px;height:'+height+'px"><svg aria-hidden="true" width="'+width+'" height="'+height+'"><defs><marker id="proof-arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L6 3 L0 6Z"/></marker></defs><g>'+paths+'</g></svg>'+buttons+'</div></div>';
  }
  /** @param {object} r Current attempt. @param {object} d Frozen edition. */
  function recovery(r,d){
    if(!['open','interrupted'].includes(r.stage)&&!(r.stage==='ready'&&r.rounds?.at(-1)?.some(n=>!n.checked)))return '';
    const issues=r.context?.unresolved||[],network=/OpenAI|network|proxy|connection/i.test(r.issue||''),model=!r.typecheck?.checked;
    const advice=issues.length?'Review the flagged definitions against the selected theorem. Rebuild for that theorem if an issue concerns a different analysis. Revise inputs if an assumption or the guarantee must change.':
      network?'Check the model connection, then retry this stage.':model?'Inspect the model diagnostic and correct the relevant definitions before trying again.':'Inspect the open obligation, then revise the supporting argument or retry its node.';
    return '<section class="proof-recovery"><h3>Next step</h3><p role="alert">'+esc(advice)+'</p>'+
      (issues.length?'<details><summary>Review model issues ('+issues.length+')</summary><ul>'+issues.map(issue=>'<li>'+esc(issue)+'</li>').join('')+'</ul></details>':'')+
      '<div class="action-row">'+(network?'<button type="button" class="control" data-module-action="openai-settings">Check connection</button>':'')+
      (model?'<button type="button" class="control" data-module-action="revise">Revise inputs</button>':nav('derivation','Inspect derivation'))+
      '<a href="'+details(d,'blocker')+'">View diagnostic</a></div></section>';
  }
  /** @param {object} d Frozen edition. @param {object} structure Immutable proof topology. */
  function panel(d,structure){
    const r=current(d),busy=r.stage==='running'||r.audit?.stage==='running';
    if(r.stage==='loading')return '<p role="status">Reading proof status…</p>';
    if(r.stage==='error')return '<h3>Proof status unavailable</h3><p>'+esc(r.issue)+'</p><p>Reload to see the latest recorded attempt.</p>'+start(d,'status','Reload status');
    const dag=topology(structure),ready=Boolean(r.typecheck?.checked||structure.modelChecked);
    const view=selections.get(identity(d))||{stage:ready?'final':'model'};
    const stage=view.stage,first=structure.lemmas[0]?.id;
    const id=stage==='final'?'target_claim':dag.nodes.has(view.node)?view.node:first;
    const receipt=new Map((r.rounds?.at(-1)||[]).map(n=>[n.id,n])),node=dag.nodes.get(id);
    const tab=(key,title)=>'<button class="control" type="button" data-proof-stage="'+key+'" data-version="'+d.version+'" aria-pressed="'+(stage===key)+'">'+title+'</button>';
    const launch=(scope,label,primary=false)=>'<button type="button" class="control '+(primary?'primary':'')+'" data-workflow="proof" data-proof-scope="'+scope+'" data-proof-target="'+esc(id||'')+'" data-version="'+d.version+'" '+(busy?'disabled':'')+'>'+label+'</button>';
    const tabs='<div class="action-row proof-stage-tabs" role="group" aria-label="Proof stages">'+tab('model','Formal model')+tab('lemmas','Lemmas & subgoals')+tab('final','Final theorem')+'</div>';
    let content;
    if(stage==='model'){
      content='<h3>Formal model</h3><p>Define the model assumptions and selected theorem, then type-check them in Rocq.</p>'+
        (ready?'<p>Model checked.</p>'+tab('lemmas','Choose a lemma'):launch('model',r.context?.unresolved?.length?'Rebuild for selected theorem':'Check formal model',true))+
        '<div class="action-row">'+tab('final','View final theorem DAG')+'</div>';
    }else{
      const deps=[...dag.parents.get(id)||[]],row=receipt.get(id);
      const status=row?(row.checked?'Verified':'Open'):ready?'Not checked':'Waiting for formal model';
      content='<div class="proof-dag-layout"><section><h3>Proof DAG</h3><p>Arrows point from supporting steps to the claim they support.</p>'+plot(dag,id,receipt,d)+'</section><section class="proof-node"><h3>'+esc((id==='target_claim'?'Final theorem':id)+' · '+(node?.title||''))+'</h3><p>'+esc(status)+'</p>'+
        (deps.length?'<p>Direct support · '+esc(deps.join(', '))+'</p>':'')+
        (ready?launch('node',id==='target_claim'?'Check theorem with supporting steps':'Check selected node with support',true):tab('model','Open formal model'))+
        (ready&&stage==='lemmas'?'<div class="action-row">'+launch('group','Check all lemmas & subgoals')+'</div>':'')+'</section></div>';
    }
    return proofProgress(r,structure)+tabs+
      (busy?'':recovery(r,d))+'<section class="proof-stage-body">'+content+'</section><div class="action-row">'+launch('auto','Run full proof automatically')+setup(d,'proof')+(receipt.get('target_claim')?.checked?nav('expert-audit','Open expert audit'):'')+'</div>';
  }
  /** @param {object} d Frozen edition. @param {object} structure Source register. @param {object} initial State before a graph exists. */
  function expert(d,structure,initial){
    const p=initial||current(d),a=p.audit,eligible=p.typecheck?.checked&&p.rounds?.some(rows=>rows.length);
    const busy=p.stage==='running'||a?.stage==='running',settings=options(d);
    const root=p.rounds?.at(-1)?.find(x=>x.id==='target_claim');
    const state=p.stage==='loading'?'Reading audit status…':p.stage==='empty'?'Add project inputs':p.stage==='underived'?'Waiting for derivation':p.stage==='error'?'Could not read status':(p.stale||p.previousAudit)?'Changes since last audit':busy?(a?.stage==='running'?'Reviewing · round '+(a.auditRounds?.length||1):'Proof in progress'):a?.stage==='ready'?'Audit complete · '+(a.auditRounds?.length||1)+' round(s)':a?.stage==='open'||a?.stage==='interrupted'?'Audit interrupted':eligible?(root?.checked?'Ready to audit':'Reviewing a partial proof'):'A checked formal model and a proof attempt are needed.';
    const cards=roles.map(role=>{
      const row=a?.reviews?.find(r=>r.role===role);
      const status=p.stale?'Earlier attempt':row?.assessment==='insufficient'?'Insufficient evidence':row?row.findings.length?row.findings.length+' findings':'No findings':a?.skills&&!a.skills[role]?'Not selected':'Not started';
      return '<article class="audit-dimension"><h3>'+names[role]+'</h3><p>'+esc(status)+'</p></article>';
    }).join('');
    const selector='<label>Audit rounds <select data-audit-limit data-version="'+d.version+'">'+[1,2,3].map(n=>'<option '+(settings.limit===n?'selected':'')+'>'+n+'</option>').join('')+'</select></label>';
    let controls='';
    if(!busy&&eligible)controls=selector+start(d,'audit',a?'Run audit again':'Start audit')+setup(d,'audit');
    else if(!busy&&p.stage!=='loading')controls=p.stage==='empty'?nav('documents','Add inputs'):p.stage==='underived'?nav('derivation','Open derivation'):p.stage==='error'?'<button type="button" class="control" data-reload-audit data-version="'+(d.version||'')+'">Reload status</button>':nav('verification','Open proof');
    if(p.previousAudit)controls+=' <a href="'+details({...d,...p.previousAudit})+'">Earlier audit</a>';
    const findings=p.stale?[]:(a?.reviews||[]).flatMap(r=>r.findings);
    const action=a?.inputRevision?nav('modeling','Inspect inputs')+'<button type="button" class="control" data-module-action="revise">Review inputs</button>':a?.refinementRemaining>0?'<button type="button" class="control" data-refine-argument="'+d.version+'">Revise derivation</button>':'';
    return '<div class="audit-summary"><div role="status"><h3>'+esc(state)+'</h3>'+((a?.issue||p.issue)?'<p>'+esc(a?.issue||p.issue)+'</p>':'')+'</div></div><div class="audit-dimensions">'+cards+'</div>'+
      (findings.length?'<section><h3>Findings to review</h3><ul>'+findings.slice(0,3).map(f=>'<li>'+esc(f.issue)+'</li>').join('')+'</ul>'+action+'</section>':'')+'<div class="action-row">'+controls+'</div>';
  }
  /** @param {object} d Frozen run. @param {string} mode Workflow settings being edited. */
  async function configure(d,mode){
    const {skills}=await request('skills',{}),opts=options(d),stages=mode==='proof'?['proof']:roles;
    const dialog=document.createElement('dialog');dialog.className='skill-dialog';
    dialog.innerHTML='<form><h2>'+names[mode]+' settings</h2>'+stages.map(role=>{
      const choices=Array.from(new Map(skills.filter(s=>s.stage===role).map(s=>[s.id,s])).values());
      const ref=opts.skills[role]||{id:'default-'+role,version:1};
      return '<section><label>'+(mode==='audit'?'<input type="checkbox" name="role" value="'+role+'" '+(opts.roles.includes(role)?'checked':'')+'> ':'')+names[role]+'</label><select aria-label="'+names[role]+' skill" name="'+role+'">'+choices.map(s=>'<option value="'+esc(s.id+'@'+s.version)+'" '+(s.id===ref.id?'selected':'')+'>'+esc(s.name)+'</option>').join('')+'</select></section>';
    }).join('')+'<p role="status"></p><footer><button type="button">Cancel</button><button>Apply</button></footer></form>';
    document.body.append(dialog);dialog.onclose=()=>dialog.remove();dialog.querySelector('button').onclick=()=>dialog.close();
    dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),selected=f.getAll('role');
      if(mode==='audit'&&!selected.length){dialog.querySelector('[role=status]').textContent='Choose a review dimension.';return;}
      for(const stage of stages){const [id,v]=f.get(stage).split('@');opts.skills[stage]={id,version:Number(v)};}
      if(mode==='audit')opts.roles=selected;dialog.close();refresh();
    };dialog.showModal();
  }
  /** @param {object} d Bound edition. @returns {string} Archived attempts and original evidence. */
  function record(d){
    const id=identity(d);
    if(!histories.has(id)){histories.set(id,null);request('workflow-history',d).then(r=>histories.set(id,r.records)).catch(e=>histories.set(id,e.message)).finally(refresh);}
    const rows=histories.get(id);
    if(!Array.isArray(rows))return '<p>'+esc(rows||'Loading attempts…')+'</p>';
    if(!rows.length)return '<p>No proof or audit attempts yet.</p>';
    const latestProof=rows.filter(r=>r.kind!=='audit').at(-1);
    return [...rows].reverse().map(r=>{
      const failed=r.rounds?.at(-1)?.find(n=>!n.checked),block=r.issue||failed?.log;
      const label=(r.kind==='audit'?'Expert audit':'Proof')+' · '+r.attempt.slice(0,10)+' '+r.attempt.slice(11,19).replaceAll('-',':')+ ' UTC';
      return '<section><h3>'+esc(label)+'</h3>'+(block?'<details '+(latestProof===r?'id="blocker" open':'')+'><summary>'+esc(failed?'Open obligation · '+failed.id:r.phase)+'</summary><pre>'+esc(block)+'</pre></details>':'')+
        (r.auditRounds?'<p>'+r.auditRounds.length+' of '+r.limit+' rounds · '+esc(r.stopReason||r.stage)+'</p>':'')+
        (r.reviews||[]).flatMap(role=>role.findings.map(f=>'<article><strong>'+esc(f.issue)+'</strong><p>'+esc(f.correction)+'</p><small>'+esc(role.role+' · '+f.source+' → '+f.affected)+'</small></article>')).join('')+
        '<details><summary>Evidence and settings</summary><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details></section>';
    }).join('');
  }
  return {load,current,select,panel,expert,configure,options,details,record,rootChecked:d=>Boolean(current(d).rounds?.at(-1)?.find(x=>x.id==='target_claim')?.checked)};
}