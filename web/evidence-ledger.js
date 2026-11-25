/** Create a read-only view of evidence stored by the checker.
 * @param {object} ui Workspace rendering, navigation and HTTP helpers.
 */
function createEvidenceLedger({audit,request,refresh,esc,markdownView,runName}){
  /** @type {Map} Pending and completed reads keyed by snapshot and requested edition. */
  const reads=new Map();
  /** @param {object} owner Project record. @param {number} run Input snapshot. @param {number} version Optional graph edition. */
  function read(owner,run,version){
    const key=owner.irKeys?.[run];
    if(!key)return {unavailable:true};
    const token=JSON.stringify([key,version??null]);
    if(!reads.has(token)){
      const entry={key,pending:true};reads.set(token,entry);
      request('evidence',{key,project:owner.id,run,version}).then(result=>Object.assign(entry,result))
        .catch(e=>{entry.error=e.message;}).finally(()=>{entry.pending=false;if(reads.get(token)===entry)refresh();});
    }
    return reads.get(token);
  }
  /** @param {string} key Immutable input key whose evidence may have changed. */
  function invalidate(key){
    for(const [token,e] of reads)if(e.key===key)reads.delete(token);
  }
  /** @param {object} owner Project. @param {number} run Input snapshot. @param {number} version Optional edition. */
  function usage(owner,run,version){
    const e=read(owner,run,version);
    if(e.pending)return 'Loading…';
    if(e.error||e.unavailable||e.version==null)return 'Not recorded';
    return String(e.recordedChecks)+' (v'+e.version+')';
  }
  /** @param {object} c Stored scalar claim, proof source and checker output. */
  function claim(c){
    const status={checked:'Checked local claim',counterexample:'Checked counterexample',open:'Open claim'}[c.status]||'Unchecked';
    const formula=[...c.premises,'⇒ '+c.conclusion].join('\n');
    const assignment=c.assignment?'<p>'+esc(Object.entries(c.assignment).map(([k,v])=>k+' = '+v).join(', '))+'</p>':'';
    return '<details class="help-item"><summary>'+esc(status+' · '+c.title)+'</summary><pre>'+esc(formula)+'</pre><p>'+esc(c.mapping)+'</p>'+assignment+
      '<details><summary>Checker evidence</summary><pre>'+esc([c.source,c.compiler,c.kernel,c.diagnostic,Number.isInteger(c.returncode)?'Exit code '+c.returncode:''].filter(Boolean).join('\n'))+'</pre></details></details>';
  }
  /**
   * Link work items back to the original edition and most specific available screen.
   * @param {object[]} work Outstanding actions computed from durable records.
   * @param {Function} link URL builder for this run.
   * @param {number} version Selected graph edition.
   */
  function workPanel(work,link,version){
    const labels={derive:'Start derivation',coverage:'Inspect goal coverage',unlinked:'Review unlinked goal',check:'Inspect and check route',continue:'Continue obligation',review:'Review check result',compose:'Inspect root proof obligation'};
    function item(w){
      const params={};
      if(w.step)params.step=w.step;
      if(w.lemma)params.lemma=w.lemma;
      if(Number.isInteger(w.index))params.route=w.index;
      if(w.trail)params.evidence=['local',...w.trail].join('-');
      const view=w.kind==='coverage'?'ir':w.kind==='compose'?'derivation-record':'derivation';
      return '<li>'+markdownView(w.title)+'<a href="'+link(view,version,params)+'">'+esc(labels[w.kind])+' →</a></li>';
    }
    return work.length?'<details class="help-item"><summary>Pending work ('+work.length+')</summary><ul>'+work.map(item).join('')+'</ul></details>':'';
  }
  /** @param {object} owner Project. @param {number} run Input snapshot. @param {number} version Optional edition. */
  function page(owner,run,version,expert=false,detail=false){
    const e=read(owner,run,version);
    const auditEntry=(stage,issue)=>audit.expert({project:owner.id,run},{sources:[],lemmas:[]},{stage,issue});
    if(expert&&(e.pending||e.error||e.unavailable||!e.version))return auditEntry(e.pending?'loading':e.error?'error':run?'underived':'empty',e.error);
    if(e.pending)return '<p role="status">Reading saved evidence…</p>';
    if(e.error)return '<p role="alert">'+esc(e.error)+'</p><button type="button" class="control" data-reload-evidence>Retry</button>';
    if(e.unavailable||!e.version)return '<h2>'+esc(runName(run))+'</h2><p>No saved derivation yet.</p><button type="button" class="control primary" data-page="derivation">Open derivation →</button>';
    const link=(view,v,more={})=>'?'+esc(new URLSearchParams({view,project:owner.id,run,version:v,...more}).toString());
    const bound={key:owner.irKeys[run],project:owner.id,run,version:e.version};
    const versions=e.editions.map(v=>v===e.version?'<strong aria-current="true">v'+v+'</strong>':'<a href="'+link(detail?'proof-details':expert?'expert-audit':'verification',v)+'">v'+v+'</a>').join(' · ');
    const header='<header><h2>'+esc(runName(run))+'</h2><nav aria-label="Derivation edition">'+versions+'</nav></header>';
    bound.parentRun=owner.workspace?.records?.find(r=>r.id===run)?.parent;
    bound.parentKey=owner.irKeys?.[bound.parentRun];
    const target=e.structure.targets[0],source=e.structure.sources.find(s=>s.id===target?.id);
    const goalHeader='<header class="av-title"><h2>'+esc(target?.title||'Proof target')+'</h2><a href="'+audit.details(bound)+'">Run details ↗</a></header>';
    if(!detail)return '<div class="stack workflow-page">'+goalHeader+(source?(expert?markdownView(source.text):'<details><summary>Theorem statement</summary>'+markdownView(source.text)+'</details>'):'')+(expert?audit.expert(bound,e.structure):audit.panel(bound,e.structure))+'</div>';

    const cards=e.receipts.map(r=>{
      const route=link('derivation',e.version,{step:r.backward,lemma:r.forward,route:r.index,evidence:['local',...r.trail].join('-')});
      return '<article class="help-item"><h3>'+esc(r.backward+' · '+r.forward+' — '+r.branch)+'</h3>'+
        (r.question?markdownView(r.question):'')+(r.trail.length&&!r.questionBound?'<p>Historical check. The recorded child question was not passed to the model.</p>':'')+r.checks.map(claim).join('')+
        (r.open.length?'<details><summary>Remaining conditions ('+r.open.length+')</summary>'+r.open.map(o=>markdownView(o)).join('')+'</details>':'')+
        (r.environment?'<details><summary>Check environment</summary><pre>'+esc([r.environment,r.switch].filter(Boolean).join('\n'))+'</pre></details>':'')+
        '<a href="'+route+'">Open route and sources →</a></article>';
    }).join('');
    return '<div class="stack">'+header+'<p>'+e.receipts.length+' local record'+(e.receipts.length===1?'':'s')+' · '+e.recordedChecks+' recorded Rocq check'+(e.recordedChecks===1?'':'s')+'</p>'+
      audit.record(bound)+
      '<details class="help-item"><summary>Theorems, lemmas &amp; dependencies</summary>'+e.structure.targets.map(t=>'<h3>'+esc(t.title)+'</h3>').join('')+
      e.structure.lemmas.map(n=>'<details><summary>'+esc(n.id+' · '+n.title)+'</summary>'+markdownView(n.formula)+'<ul>'+e.structure.dependencies.filter(d=>d.to===n.id).map(d=>'<li>'+esc(d.from+' → '+d.to+' · '+d.role)+'</li>').join('')+'</ul><small>'+esc(n.sources.join(' · '))+'</small></details>').join('')+'</details>'+(audit.rootChecked(bound)?'':workPanel(e.work||[],link,e.version))+(cards?'<details class="help-item"><summary>Local check records ('+e.receipts.length+')</summary>'+cards+'</details>':'<p>No local evidence saved for this edition. <a href="'+link('derivation',e.version)+'">Inspect derivation →</a></p>')+'</div>';
  }
  return {page,usage,invalidate};
}
