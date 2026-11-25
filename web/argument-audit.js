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
  async function load(d,action='status'){
    const id=identity(d),previous=reports.get(id),settings=options(d);
    clearTimeout(timers.get(id));
    reports.set(id,{...previous,stage:'loading'});if(action!=='status')refresh();
    try{
      const route={status:'argument-review-status',proof:'argument-review',audit:'start-audit'}[action];
      const report=await request(route,{...d,...settings,proofAttempt:previous?.attempt});
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
  /** @param {object} d Frozen run and edition. */
  function panel(d){
    const r=current(d),root=r.rounds?.at(-1)?.find(x=>x.id==='target_claim'),busy=r.stage==='running'||r.audit?.stage==='running';
    if(r.stage==='loading')return '<p role="status">Reading proof status…</p>';
    if(r.stage==='error')return '<p>'+esc(r.issue)+'</p>'+start(d,'status','Reload status');
    const blocked=r.issue||(!root?.checked&&r.rounds?.at(-1)?.find(n=>!n.checked)?.id);
    const state=r.stage==='running'?(r.lastStep?'Constructing proofs · last checked '+r.lastStep:r.phase):root?.checked?'Proof verified':r.stage==='idle'?'Ready to start':'Needs attention';
    const primary=root?.checked?nav('expert-audit','Open expert audit'):blocked?'<a class="control primary" href="'+details(d,'blocker')+'">View blocker</a>':start(d,'proof','Start proof');
    return '<section class="audit-summary"><div role="status"><h3>'+esc(state)+'</h3>'+(blocked?'<p>'+esc(r.issue?r.issue.split('\n')[0].slice(0,240):'Open obligation · '+blocked)+'</p>':'')+'</div></section><div class="action-row">'+(busy?'':primary+(blocked?start(d,'proof','Retry proof'):'')+setup(d,'proof'))+'</div>';
  }
  /** @param {object} d Frozen edition. @param {object} structure Source register. @param {object} initial State before a graph exists. */
  function expert(d,structure,initial){
    const p=initial||current(d),a=p.audit,eligible=p.typecheck?.checked&&p.rounds?.some(rows=>rows.length);
    const busy=p.stage==='running'||a?.stage==='running',settings=options(d);
    const root=p.rounds?.at(-1)?.find(x=>x.id==='target_claim');
    const state=p.stage==='loading'?'Reading audit status…':p.stage==='empty'?'Add project inputs':p.stage==='underived'?'Waiting for derivation':p.stage==='error'?'Could not read status':(p.stale||p.previousAudit)?'Changes since last audit':busy?(a?.stage==='running'?'Reviewing · round '+(a.auditRounds?.length||1):'Proof in progress'):a?.stage==='ready'?'Audit complete · '+(a.auditRounds?.length||1)+' round(s)':a?.stage==='open'||a?.stage==='interrupted'?'Audit interrupted':eligible?(root.checked?'Ready to audit':'Reviewing a partial proof'):'A checked formal model and a proof attempt are needed.';
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
  return {load,current,panel,expert,configure,options,details,record,rootChecked:d=>Boolean(current(d).rounds?.at(-1)?.find(x=>x.id==='target_claim')?.checked)};
}