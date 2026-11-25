/** Manage local reasoning methods and stage choices in the workspace.
 * @param {object} host Run navigation, rendering and same-origin service.
 */
function createReasoningSkills({request,esc,render,context,openRecord,listRuns,markdown,math,typeset}){
  const stages=['forward','backward','alignment'],names={forward:'Forward',backward:'Backward',alignment:'Alignment'};
  let catalog=null,loading=null,loadError='';
  const pending=new Map();
  /** Load the shared library once. @param {boolean} force Refresh after publishing a revision. */
  async function load(force=false){
    if(loading)return loading;
    if(catalog&&!force)return catalog;
    loading=request('skills',{}).then(result=>{catalog=result;loadError='';return result;}).catch(error=>{loadError=error.message;throw error;}).finally(()=>{loading=null;render();});
    return loading;
  }
  const latest=()=>Array.from(new Map(catalog.skills.map(s=>[s.id,s])).values());
  const token=s=>s.id+'@'+s.version;
  function button(action,label,id=''){return '<button type="button" class="control" data-skill-action="'+action+'" data-skill-id="'+esc(id)+'">'+esc(label)+'</button>';}
  /** Stage labels and icons used to browse execution skills in Resources. */
  const cardStages={
    proof:['Proof','shield-check'],fidelity:['Expert audit · model','scan'],semantics:['Expert audit · semantics','network'],coverage:['Expert audit · coverage','list-checks'],
    extraction:['PDF extraction','file-text'],
    forward:['Forward reasoning','git-branch'],
    backward:['Backward reasoning','network'],
    alignment:['Alignment','git-merge']
  };
  /** @param {object} skill Published skill revision displayed in the library. */
  function skillCard(skill){
    const [stage,icon]=cardStages[skill.stage];
    return `<button type="button" class="skill-card" data-skill-action="details" data-skill-id="${esc(skill.id)}">
      <span class="skill-card-top"><span class="skill-card-icon"><i aria-hidden="true" data-lucide="${icon}"></i></span><i aria-hidden="true" data-lucide="chevron-right"></i></span>
      <strong>${esc(skill.name)}</strong><span class="skill-card-stage">${stage}</span></button>`;
  }
  /** @returns {string} Resource cards in workflow order, followed by user-created skills. */
  function libraryPage(){
    if(!catalog){if(!loading&&!loadError)queueMicrotask(()=>load().catch(()=>{}));return loadError?esc(loadError)+button('refresh','Retry'):'Loading skills…';}
    const entries=latest();
    function grid(skills){return '<div class="skill-grid">'+skills.map(skillCard).join('')+'</div>';}
    const custom=entries.filter(s=>!s.builtin);
    return '<div class="skill-library"><header class="av-title"><h2>Built-in skills</h2>'+button('new','New skill')+'</header>'+
      grid(entries.filter(s=>s.builtin))+(custom.length?'<h2>Custom skills</h2>'+grid(custom):'')+'</div>';
  }
  /** @param {object} skill Catalog entry with the instructions used by its execution stage. */
  function details(skill){
    const extraction=skill.stage==='extraction';
    const execution=!extraction&&!stages.includes(skill.stage);
    const where=execution?(skill.stage==='proof'?'Proof → Proof settings':'Expert audit → Audit settings'):extraction?'Documents → Extract paper contributions':'Derivation → Reasoning setup';
    const notes=[['Instructions',skill.instructions.replace(/^# [^\n]+\r?\n/,'')],['When to use',skill.when],['Procedure',skill.method],['Completion criteria',skill.acceptance],['Example',skill.example]];
    const content=notes.filter(([,value])=>value?.trim()).map(([label,value])=>'<section><h3>'+label+'</h3>'+markdown(value)+'</section>').join('');
    const actions=extraction?'':'<footer><button type="button" data-open-editor>'+(execution?(skill.builtin?'View settings':'Edit skill'):skill.builtin?'Try skill':'Edit or try skill')+'</button><button type="button" data-copy>Make a copy</button></footer>';
    const d=dialog(skill.name,'<p class="skill-location">'+esc(where)+' · '+(skill.builtin?'Built-in':'Custom')+' · v'+esc(String(skill.version))+'</p><div class="skill-reading">'+content+'</div>'+actions);
    if(!extraction){
      d.querySelector('[data-open-editor]').onclick=()=>{d.close();editor(skill);};
      d.querySelector('[data-copy]').onclick=()=>{d.close();editor(skill,true);};
    }
    typeset(d);
  }

  /** @param {string} title Accessible modal name. @param {string} body Form content. */
  function dialog(title,body){
    const d=document.createElement('dialog');d.className='skill-dialog';d.setAttribute('aria-label',title);
    d.innerHTML='<header><h2>'+esc(title)+'</h2><button type="button" aria-label="Close">×</button></header>'+body+'<p role="status" class="skill-status"></p>';
    document.body.append(d);d.querySelector('header button').onclick=()=>d.close();d.onclose=()=>d.remove();d.showModal();return d;
  }
  /** @param {string} id Operation handle. @param {Function} report Progress feedback. */
  async function wait(id,report){
    for(;;){const task=await request('skill-progress',{id});if(task.stage==='failed')throw Error(task.message);
      if(task.stage!=='running')return task;report(names[task.phase]||({'formal context':'Checking shared context',bidirectional:'Forward and backward reasoning'})[task.phase]||'Preparing');await new Promise(r=>setTimeout(r,1400));}
  }
  /** @param {object} ctx Saved IR and optional parent graph. */
  function choices(ctx){
    const stored=ctx.owner.skillSetups?.[ctx.key];
    return Object.fromEntries(stages.map(stage=>{
      const selection=stored?.[stage]||ctx.graph?.workflow?.[stage]?.skill||{id:'default-'+stage,version:ctx.graph?1:2};
      return [stage,{id:selection.id,version:selection.version}];
    }));
  }
  function setup(ctx){
    const config=choices(ctx);
    const d=dialog('Reasoning setup','<form>'+stages.map(stage=>{
      const options=latest().filter(s=>s.stage===stage);
      const pinned=catalog.skills.find(s=>token(s)===token(config[stage]));
      if(pinned&&!options.some(s=>token(s)===token(pinned)))options.push(pinned);
      return '<label>'+names[stage]+'<select name="'+stage+'">'+options.map(s=>'<option value="'+esc(token(s))+'" '+(token(s)===token(config[stage])?'selected':'')+'>'+esc(s.name)+(options.filter(o=>o.id===s.id).length>1?' · revision '+s.version:'')+'</option>').join('')+'</select><small>Inputs · '+esc(catalog.inputs[stage])+'</small></label>';
    }).join('')+'<footer><button>Apply setup</button></footer></form>');
    d.querySelector('form').onsubmit=e=>{e.preventDefault();const fd=new FormData(e.target);
      const next=Object.fromEntries(stages.map(stage=>{const s=catalog.skills.find(s=>token(s)===fd.get(stage));return [stage,{id:s.id,version:s.version}];}));
      (ctx.owner.skillSetups??={})[ctx.key]=next;ctx.persist();d.close();render();};
  }
  /** @param {object} ctx Current run. @returns {string} Launch or inspect configuration. */
  function toolbar(ctx){
    const config=choices(ctx),custom=stages.filter(stage=>config[stage].id!=='default-'+stage);
    const job=pending.get(ctx.key);
    if(!job&&sessionStorage.getItem('autovisa.operation.'+ctx.key))queueMicrotask(()=>resume(ctx));
    const rerun=stages.slice(0,2).filter(stage=>token(config[stage])!==token(ctx.graph?.workflow?.[stage]?.skill||{id:'default-'+stage,version:1}));
    const label=!ctx.graph?'Start derivation':rerun.length?'Run '+rerun.map(s=>names[s]).join(' + ')+' + Alignment':'Re-run alignment';
    return '<div class="skill-bar"><strong>Reasoning setup</strong><span>'+(custom.length?custom.map(s=>names[s]).join(', ')+' customized':'Default workflow')+'</span>'+button('configure','Configure')+(job&&!job.error?'<span role="status">'+esc(job.phase)+'…</span>':button('execute',label))+(job?.error?'<p role="alert">'+esc(job.error)+'</p>':'')+'</div>';
  }
  /** Recover a user-started workflow after this browser tab reloads. @param {object} ctx Bound run. */
  function resume(ctx){
    const id=sessionStorage.getItem('autovisa.operation.'+ctx.key);
    if(id&&!pending.has(ctx.key))void execute(ctx,id);
  }
  async function execute(ctx,resumedId){
    if(pending.has(ctx.key)&&!pending.get(ctx.key).error)return;
    const state={phase:'Preparing'};pending.set(ctx.key,state);render();
    try{
      const result=resumedId?{id:resumedId}:await request('run-skills',{key:ctx.key,project:ctx.owner.id,run:ctx.run,parent:ctx.graph?.version||null,setup:choices(ctx)});
      sessionStorage.setItem('autovisa.operation.'+ctx.key,result.id);
      const done=await wait(result.id,phase=>{if(state.phase!==phase){state.phase=phase;render();}});
      pending.delete(ctx.key);sessionStorage.removeItem('autovisa.operation.'+ctx.key);if(context()?.key===ctx.key)openRecord(ctx,done.version,undefined,true);else render();
    }catch(error){sessionStorage.removeItem('autovisa.operation.'+ctx.key);pending.set(ctx.key,{error:error.message});render();}
  }
  /** @param {object} graph Historical evidence, including inherited stages. */
  function evidence(graph){
    if(!graph.workflow)return '<details class="help-item"><summary>Reasoning setup</summary><p>Original workflow · created before configurable skills.</p></details>';
    return '<details class="help-item" open><summary>Reasoning setup</summary>'+stages.map(stage=>{
      const w=graph.workflow[stage],s=w.skill;
      return '<details class="arg-source"><summary>'+names[stage]+' · '+esc(s?.name||'Original workflow')+(w.reusedFrom?' · reused from v'+w.reusedFrom:'')+'</summary>'+
        (s?'<p>Skill revision '+s.version+'</p>'+markdown(s.instructions)+[s.when,s.method,s.acceptance].filter(Boolean).map(x=>markdown(x)).join('')+(s.example?'<h4>Example</h4>'+markdown(s.example):''):'')+
        (w.scope?'<p>Scope · '+esc(w.scope)+(w.inheritedFrom?' · other comparisons from v'+w.inheritedFrom:'')+'</p>':'')+
        '<small>Output SHA-256 · '+esc(w.hash)+'</small></details>';
    }).join('')+(graph.parentVersion?'<p>Based on '+button('parent','Open v'+graph.parentVersion,String(graph.parentVersion))+' '+button('compare','Compare alignment')+'</p>':'')+'</details>';
  }
  /** @param {object|null} original Source skill for viewing, editing or copying. @param {boolean} copy Create a distinct ID. */
  function editor(original,copy=false){
    const locked=original?.builtin&&!copy;
    const runs=listRuns(),ctx=context();
    const d=dialog(locked?'Default skill':copy?'Copy skill':original?'Edit skill':'New skill','<form><fieldset><label>Name<input name="name" required></label><label>Stage<select name="stage">'+[...stages,'proof','fidelity','semantics','coverage'].map(s=>'<option value="'+s+'">'+(names[s]||cardStages[s][0])+'</option>').join('')+'</select></label><label>Instructions · Markdown<textarea name="instructions" required rows="6"></textarea></label><label>Example (optional)<textarea name="example" rows="2"></textarea></label><details><summary>Method and acceptance</summary><label>When to use<textarea name="when"></textarea></label><label>Procedure<textarea name="method" rows="4"></textarea></label><label>Completion criteria<textarea name="acceptance"></textarea></label></details></fieldset>'+
      '<details class="trial-box"><summary>Try on a saved run</summary><label>Run<select name="run">'+runs.map((r,i)=>'<option value="'+i+'">'+esc(r.label)+'</option>').join('')+'</select></label><label class="target">Compare against<select name="focus"></select></label><button type="button" data-try>Try skill</button><section class="trial-output"></section></details><footer><button type="button" data-save>'+ (locked?'Make a copy':'Save skill')+'</button><button type="button" hidden data-adopt>Save skill &amp; keep alignment</button></footer></form>');
    const f=d.querySelector('form'),el=f.elements,n=el.namedItem('name'),stage=el.namedItem('stage'),instructions=el.namedItem('instructions'),example=el.namedItem('example'),run=el.namedItem('run'),focus=el.namedItem('focus');
    const msg=d.querySelector('[role=status]'),out=d.querySelector('.trial-output'),adopt=d.querySelector('[data-adopt]');
    n.value=(original?.name||'')+(copy?' (copy)':'');stage.value=original?.stage||'alignment';instructions.value=original?.instructions||'';example.value=original?.example||'';
    for(const k of ['when','method','acceptance'])el.namedItem(k).value=original?.[k]||'';
    if(locked)d.querySelector('fieldset').disabled=true;
    if(original&&!copy)stage.disabled=true;
    let saved=copy?null:original,trial=null,sequence=0,base=null,busy=false;
    function draft(){return {stage:stage.value,name:n.value.trim(),instructions:instructions.value.trim(),example:example.value.trim(),...Object.fromEntries(['when','method','acceptance'].map(k=>[k,el.namedItem(k).value.trim()]))};}
    function invalidate(){trial=null;adopt.hidden=true;out.replaceChildren();}
    const current=()=>runs[Number(run.value)];
    if(ctx){const i=runs.findIndex(r=>r.key===ctx.key);if(i>=0)run.value=String(i);}
    async function targets(){
      const seq=++sequence;invalidate();base=null;const r=current();focus.innerHTML='';d.querySelector('.target').hidden=stage.value!=='alignment';
      d.querySelector('.trial-box').hidden=!stages.includes(stage.value);
      if(!r||!stages.includes(stage.value))return;
      try{const summary=await request('derivation-status',{key:r.key,version:2});
        const activeVersion=ctx?.key===r.key?ctx.graph?.version:null;const ver=activeVersion>=2?activeVersion:Math.max(0,...summary.versions.filter(v=>v>=2));const record=ver===2?summary:ver?await request('derivation-status',{key:r.key,version:ver}):{};
        if(seq!==sequence)return;base=record.graph;msg.textContent=base?'Trial input · '+r.label+' · v'+base.version:'';focus.innerHTML='<option value="">All backward steps</option>'+(base?.backward||[]).map(s=>'<option value="'+esc(s.id)+'">'+esc(s.id+' · '+s.title)+'</option>').join('');
      }catch(error){if(seq===sequence)msg.textContent=error.message;}
    }
    run.onchange=stage.onchange=targets;focus.onchange=invalidate;f.oninput=invalidate;
    async function publish(){
      const value=draft();if(saved&&Object.keys(value).every(k=>(saved[k]||'')===value[k]))return saved;
      saved=await request('save-skill',{...value,...(saved?{id:saved.id,version:saved.version}:{})});await load(true);return saved;
    }
    async function action(fn){
      if(busy)return;busy=true;
      const controls=[...f.querySelectorAll('input,select,textarea,button')].map(e=>[e,e.disabled]);
      controls.forEach(([e])=>{e.disabled=true;});msg.textContent='';
      try{await fn();}catch(e){msg.textContent=e.message;}finally{busy=false;controls.forEach(([e,disabled])=>{e.disabled=disabled;});}
    }
    f.onsubmit=e=>e.preventDefault();
    d.querySelector('[data-save]').onclick=()=>action(async()=>{
      if(locked){d.close();editor(original,true);return;}
      await publish();d.close();
    });
    d.querySelector('[data-try]').onclick=()=>action(async()=>{
      invalidate();const r=current();if(!r)throw Error('Choose a run with confirmed inputs.');
      if(stage.value==='alignment'&&!base)throw Error('Open a run with a saved detailed graph.');
      const job=await request('run-skills',{key:r.key,run:r.run,project:r.owner.id,parent:base?.version,focus:focus.value,trial:draft()});
      const result=await wait(job.id,p=>{msg.textContent='Trying '+p+'…';});trial={id:job.id,r};
      out.innerHTML=result.output.map(line=>line.status?'<article><h4>'+esc(line.forward+' ↔ '+line.backward+' · '+line.status)+'</h4>'+math(line.available,true)+math(line.required,true)+markdown(line.condition)+'</article>':'<article><h4>'+esc(line.id+' · '+line.title)+'</h4>'+math(line.formula,true)+markdown(line.reason)+'</article>').join('')||'<p>No corresponding steps found.</p>';
      typeset(out);msg.textContent='Preview ready.';adopt.hidden=stage.value!=='alignment';
    });
    adopt.onclick=()=>action(async()=>{
      const skill=await publish(),result=await request('adopt-skill-trial',{id:trial.id,skill});
      d.close();openRecord(trial.r,result.version,focus.value);
    });
    void targets();
  }
  /** Compare the recorded outputs for the same obligation across a parent and child.
   * @param {object} ctx Current project, run and selected historical record.
   */
  async function compare(ctx){
    const graph=ctx.graph,parent=(await request('derivation-status',{key:ctx.key,version:graph.parentVersion})).graph;
    if(!parent)throw Error('Parent record unavailable.');
    const d=dialog('Compare alignment','<label>Backward obligation<select name="obligation"></select></label><section class="skill-comparison"></section>');
    const picker=d.querySelector('select'),host=d.querySelector('.skill-comparison');
    const ids=[...new Set([...graph.backward,...parent.backward].map(n=>n.id))];
    picker.innerHTML=ids.map(id=>'<option value="'+esc(id)+'">'+esc(id)+'</option>').join('');
    if(ids.includes(graph.workflow.alignment.scope))picker.value=graph.workflow.alignment.scope;
    function draw(){
      host.innerHTML=[parent,graph].map(g=>'<section><h3>v'+g.version+' · '+esc(g.backward.find(n=>n.id===picker.value)?.title||'Step absent')+'</h3>'+
        (g.connections.filter(p=>p.backward===picker.value).map(p=>'<article><strong>'+esc(p.forward+' · '+p.status+' · '+(p.branch||p.title))+'</strong>'+markdown(p.condition||p.reason)+'</article>').join('')||'<p>No recorded link.</p>')+'</section>').join('');
      typeset(host);
    }
    picker.onchange=draw;draw();
  }
  /** @param {string} action Workspace action. @param {string} id Skill ID or parent version. */
  async function handle(action,id){
    try{
      await load(action==='refresh');
      const ctx=context(),skill=latest().find(s=>s.id===id);
      if(action==='details'&&skill)details(skill);
      if(['new','edit','copy'].includes(action))editor(skill,action==='copy');
      if(action==='configure'&&ctx)setup(ctx);
      if(action==='execute'&&ctx)await execute(ctx);
      if(action==='parent'&&ctx)openRecord(ctx,Number(id),ctx.graph?.workflow?.alignment.scope);
      if(action==='compare'&&ctx)await compare(ctx);
    }catch(error){const d=dialog('Skills','');d.querySelector('[role=status]').textContent=error.message;}
  }
  return {libraryPage,toolbar,evidence,handle};
}
