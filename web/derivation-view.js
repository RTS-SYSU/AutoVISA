/** Views over immutable derivation versions. The host owns navigation and source dialogs.
 * @param {object} helpers Existing safe rendering and paper citation functions.
 */
function createDerivationReader({esc,math,markdownView,citation,request,refresh}){
  /** @param {object} graph Saved DAG. @returns {Map} Stable step IDs and compact reading labels. */
  function index(graph){
    const steps=new Map();
    for(const [side,prefix] of [['forward','F'],['backward','B']]){
      graph[side].forEach((step,i)=>steps.set(step.id,{...step,side,label:prefix+(i+1)}));
    }
    return steps;
  }
  /** @param {string} id Destination ID. @param {string} label Visible link. @param {string} target Record or diagram. */
  function jump(id,label,target='detail'){
    return '<button type="button" class="cite" data-arg-target="'+target+'" data-arg-id="'+esc(id)+'">'+esc(label)+'</button>';
  }
  /** @param {object} graph Current immutable version. @param {object} view Local selection. */
  function selection(graph,view){
    const steps=index(graph);
    const step=steps.get(view.selected)||graph.backward.map(node=>steps.get(node.id))[0];
    return {steps,step};
  }
  /** @param {object} ir Bound IR. @param {string[]} refs Confirmed statement references. */
  function sources(ir,refs){
    return [...new Set(refs)].map(id=>{
      const row=ir.items.find(row=>row.id===id);
      if(!row)return '';
      const hit=citation(row.ref);
      return '<details class="arg-source"><summary>'+esc(row.statement.title)+'</summary>'+markdownView(row.source)+(hit?'<button class="cite" type="button" data-cite="'+esc(row.ref)+'">Open '+esc(hit.label)+'</button>':'<p>Exact passage unavailable.</p>')+'</details>';
    }).join('');
  }
  /** @param {object[]} pairs Cross-direction relationships incident to the selected step.
   * @param {Map} steps Step lookup. @param {boolean} historical Original evidence format.
   */
  function comparisons(pairs,steps,historical,ir){
    if(!pairs.length)return '<p>No recorded cross-graph match for this step.</p>';
    return pairs.map(pair=>{
      const left=steps.get(pair.forward),right=steps.get(pair.backward);
      const status=historical?(pair.status==='aligned'?'Aligned':'Open'):pair.status;
      return '<article class="dag-pair" data-match="'+esc(status)+'"><header><b>'+esc(status)+'</b><span>'+jump(left.id,left.label)+' ↔ '+jump(right.id,right.label)+'</span></header><h4>'+esc(pair.branch||pair.title)+'</h4>'+
        (historical?math(pair.formula,true)+markdownView(pair.reason):
          '<dl><dt>Available · '+left.label+'</dt><dd>'+math(pair.available,true)+'</dd><dt>Required · '+right.label+'</dt><dd>'+math(pair.required,true)+'</dd></dl><strong>'+(status==='Matches'?'Why they match':status==='Conditional'?'Still required':'Missing link')+'</strong>'+markdownView(pair.condition))+'<details><summary>Source statements</summary>'+sources(ir,pair.sources||[])+'</details></article>';
    }).join('');
  }
  /** @param {string} value A saved formula or a sentence containing inline math. */
  function expressionView(value){
    return /\$/.test(value)||(!/\\/.test(value)&&/[a-z]{3,} [a-z]{2,} /i.test(value))?markdownView(value):math(value||'',true);
  }
  /** @type {Map<string,Promise<object>>} Reuse requested historical explanations during this session. */
  const readingCache=new Map();
  /** @type {Map<string,object>} Contexts for the currently rendered reader. */
  const visibleSteps=new Map();
  /** @param {object} node Frozen step. @returns {string} A readable sentence from its stored account. */
  function readingSentence(node){
    if(node.plainStatement)return node.plainStatement;
    const saved=(node.reason||'').replace(/^[-*]\s+|^Unchecked research draft\.\s*/gi,'').trim();
    return saved.split(/(?<=[.!?])(?:\s+|$)|\n\n/)[0]||node.title;
  }
  /** @param {object} graph Frozen edition. @param {object} node Selected step.
   * @param {object} ir Confirmed symbols. @param {boolean} full Show the unabbreviated statement.
   */
  function stepReading(graph,node,ir,full=false){
    visibleSteps.set(node.id,{graph,node,ir});
    const expression=full?node.formula:node.summaryFormula||node.formula;
    return '<div class="step-reading" data-reading-id="'+esc(node.id)+'"><div class="step-sentence">'+markdownView(node.plainStatement||graph.readingNotes?.[node.id]?.plainStatement||readingSentence(node))+'</div><div class="goal-math">'+expressionView(expression)+'</div></div>';
  }
  /** @param {Element} element MathML identifier. Keep script placement in its lookup key. */
  function notationKey(element){
    if(element.localName==='mrow'&&element.children.length===1)return notationKey(element.firstElementChild);
    return element.localName+'('+(element.children.length?Array.from(element.children,notationKey).join(','):element.textContent)+')';
  }
  /** @param {string} tex Exact LaTeX identifier. @returns {string} Structural lookup key. */
  function symbolKey(tex){
    if(!tex)return '';
    try{
      const span=document.createElement('span');
      window.katex.render(tex.replace(/^\$|\$$/g,''),span,{output:'mathml',trust:false});
      return notationKey(span.querySelector('semantics').firstElementChild);
    }catch{return '';}
  }
  /** Common logical operators have the same reading across runs. */
  const operators={'∧':'Both conditions hold.','∨':'At least one condition holds.','⟹':'If the left side holds, the right side follows.','⇒':'If the left side holds, the right side follows.','∀':'For every value in the stated domain.','∃':'There exists a value in the stated domain.','≤':'Less than or equal to.','≥':'Greater than or equal to.','∈':'Is an element of.','=':'Equals.'};
  /** @param {Element} scope Newly typeset portion of the document. */
  function bindSymbols(scope){
    for(const host of scope.querySelectorAll('.step-reading .goal-math math:not([data-symbols-ready])')){
      const ctx=visibleSteps.get(host.closest('[data-reading-id]').dataset.readingId);
      if(!ctx)continue;
      host.dataset.symbolsReady='true';
      const selector='msub,msup,msubsup,mi,mo';
      for(const token of host.querySelectorAll(selector)){
        if(token.parentElement.closest('msub,msup,msubsup'))continue;
        const label=token.textContent;
        if(token.localName==='mo'&&!operators[label]&&!/^[\p{L}]+$/u.test(label))continue;
        token.setAttribute('tabindex','0');token.setAttribute('role','button');
        token.setAttribute('aria-label','Meaning of '+label);token.classList.add('reading-symbol');
        const activate=()=>openSymbol(ctx,label,token);
        token.addEventListener('click',activate);
        token.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();activate();}});
      }
    }
  }
  /** @param {object} ctx Frozen graph, node and IR. @param {string} label Typeset identifier. @param {Element} trigger Focus target on dismissal. */
  async function openSymbol(ctx,label,trigger){
    const {graph,node,ir}=ctx,dialog=document.createElement('dialog');
    dialog.className='scope-dialog symbol-dialog';
    dialog.setAttribute('aria-label','Symbol meaning');
    dialog.innerHTML='<h2>'+esc(label)+'</h2><p role="status"></p><button class="control" type="button">Close</button>';
    document.body.append(dialog);dialog.onclose=()=>{dialog.remove();if(trigger.isConnected)trigger.focus();};dialog.querySelector('button').onclick=()=>dialog.close();
    // Preserve the script layout of the selected identifier in the dialog heading.
    const notation=document.createElementNS('http://www.w3.org/1998/Math/MathML','math');
    const copy=trigger.cloneNode(true);
    for(const attr of ['role','tabindex','class','aria-label'])copy.removeAttribute(attr);
    notation.append(copy);dialog.querySelector('h2').replaceChildren(notation);
    dialog.showModal();
    const message=dialog.querySelector('p');
    const lookup=entries=>entries?.find(entry=>symbolKey(entry.tex)===notationKey(trigger))?.meaning;
    const declared=(ir.symbols||[]).filter(entry=>node.sources.includes(entry.introducedBy)||ir.items?.some(row=>node.sources.includes(row.id)&&row.statement?.uses?.includes(entry.id)));
    const meanings=new Set(declared.filter(entry=>symbolKey(entry.label)===notationKey(trigger)).map(entry=>entry.meaning).filter(Boolean));
    const known=lookup(node.symbols)||lookup(graph.readingNotes?.[node.id]?.symbols)||operators[label]||(meanings.size===1?[...meanings][0]:'');
    if(known){message.textContent=known;return;}
    /** @param {string} status Why the exact definition could not be displayed. */
    function showContext(status){
      message.textContent=status;
      const excerpt=document.createElement('div');
      excerpt.innerHTML='<strong>Step context</strong>'+markdownView(readingSentence(node));
      message.after(excerpt);
    }
    if(node.symbols){showContext('No definition is recorded for this notation.');return;}
    message.textContent='Reading this symbol in the saved step…';
    const key=JSON.stringify([graph.key,graph.version,node.id]);
    try{
      if(!readingCache.has(key)){
        if(readingCache.size>=64)readingCache.delete(readingCache.keys().next().value);
        readingCache.set(key,request('step-reading',{key:graph.key,project:graph.project,run:graph.run,version:graph.version,step:node.id}));
      }
      const entry=await readingCache.get(key);
      const definition=lookup(entry.symbols);
      if(definition)message.textContent=definition;
      else showContext('No exact definition was found for this notation.');
    }catch(error){
      readingCache.delete(key);
      showContext('No local definition. '+(error?.message||'The model lookup failed.'));
    }
  }
  /** @param {object} graph Historical evidence. @param {object} view Current reading selection. */
  function focusOf(graph,view){
    const {steps,step}=selection(graph,view);
    const target=step.side==='backward'?step:steps.get(graph.connections.find(p=>p.forward===step.id&&p.backward===view.goalContext)?.backward||graph.connections.find(p=>p.forward===step.id)?.backward)||steps.get(graph.backward[0].id);
    const pairs=graph.connections.map((p,i)=>({...p,ordinal:i})).filter(p=>p.backward===target.id);
    const desired=step.side==='forward'?step.id:view.lemma;
    const candidates=pairs.filter(p=>p.forward===desired);
    const pool=candidates.length?candidates:pairs;
    const pair=pool.find(p=>p.ordinal===view.pairIndex)||pool.find(p=>p.status==='Gap'||p.status==='open')||pool[0];
    return {steps,target,pairs,pair};
  }
  /**
   * Draw immutable dependencies and cross-direction comparisons at two scales.
   * @param {object} graph Saved run edition.
   * @param {Map} steps Stable IDs mapped to their readable titles.
   * @param {object} target Selected backward step.
   * @param {object} pair Selected alignment, if one exists.
   * @param {boolean} whole Show every recorded step and comparison.
   * @param {string} filter Route status selected in the overview.
   */
  function relationMap(graph,steps,target,pair,whole,filter='All'){
    const nearby=new Set([target.id,...target.parents,...graph.backward.filter(n=>n.parents.includes(target.id)).map(n=>n.id)]);
    const goals=graph.backward.filter(n=>whole||nearby.has(n.id));
    const ids=new Set(goals.map(n=>n.id));
    const children=new Map();
    for(const goal of goals){
      const parent=goal.parents.find(id=>ids.has(id));
      if(!children.has(parent))children.set(parent,[]);
      children.get(parent).push(goal);
    }
    function button(id,context='',status=''){
      const n=steps.get(id),goal=n.side==='backward';
      const active=goal?id===target.id:id===pair?.forward&&context===target.id;
      return '<button type="button" class="tree-step '+n.side+'" '+(goal?'data-map-goal':'data-map-lemma')+'="'+esc(id)+'" data-context="'+esc(context)+'" aria-pressed="'+active+'"><b>'+esc(n.label)+'</b><span>'+esc(n.title)+'</span>'+(status?'<small>'+esc(status)+'</small>':'')+'</button>';
    }
    function branch(n){
      const linked=new Map();
      if(whole||n.id===target.id){
        for(const link of graph.connections.filter(l=>l.backward===n.id)){
          const status=({aligned:'Matches',open:'Gap'})[link.status]||link.status;
          if(filter!=='All'&&filter!==status)continue;
          if(!linked.has(link.forward))linked.set(link.forward,new Set());
          linked.get(link.forward).add(status);
        }
      }
      const extra=n.parents.filter(id=>ids.has(id)).slice(1).map(id=>steps.get(id).label);
      const alignments=[...linked].map(([id,states])=>'<li>'+button(id,n.id,[...states].join(' / '))+'</li>').join('');
      const subgoals=(children.get(n.id)||[]).map(branch).join('');
      return '<li>'+button(n.id)+(extra.length?'<small>Also depends on '+esc(extra.join(', '))+'</small>':'')+(alignments?'<ul class="tree-matches">'+alignments+'</ul>':'')+(subgoals?'<ul>'+subgoals+'</ul>':'')+'</li>';
    }
    const lemmaBranch=n=>{
      const parents=n.parents.map(id=>steps.get(id)?.label).filter(Boolean);
      return '<li>'+button(n.id)+(parents.length?'<small>Depends on '+esc(parents.join(', '))+'</small>':'')+'</li>';
    };
    const dependencies=whole?'<details class="lemma-register"><summary>Forward lemma dependencies</summary><ul>'+graph.forward.map(lemmaBranch).join('')+'</ul></details>':'';
    return '<div class="proof-tree '+(whole?'full-network':'near-network')+'"><ul>'+(children.get(undefined)||[]).map(branch).join('')+'</ul>'+dependencies+'</div>';
  }
  /**
   * Draw immutable dependencies and cross-direction comparisons at two scales.
   * @param {object} graph Saved run edition.
   * @param {Map} steps Stable IDs mapped to their readable titles.
   * @param {object} target Selected backward step.
   * @param {object} pair Selected alignment, if one exists.
   * @param {boolean} whole Show every recorded step and comparison.
   */
  function networkPlot(graph,steps,target,pair,whole,filter='All'){
    const neighbourhood=new Set([...target.parents,target.id,...graph.backward.filter(n=>n.parents.includes(target.id)).map(n=>n.id)]);
    const statusOf=link=>({aligned:'Matches',open:'Gap'})[link.status]||link.status;
    const links=graph.connections.filter(link=>(whole||link.backward===target.id)&&(filter==='All'||statusOf(link)===filter)).flatMap(link=>[link,...(link.supports||[]).map(s=>({...link,forward:s.id,branch:s.role}))]);
    const linkedLemmas=new Set(links.map(link=>link.forward));
    const goals=graph.backward.filter(n=>whole||neighbourhood.has(n.id));
    const lemmas=graph.forward.filter(n=>whole||linkedLemmas.has(n.id));
    const width=whole?780:220, spacing=whole?55:54;
    const height=52+Math.max(goals.length,lemmas.length)*spacing;
    const mapId=whole?'run-network':'goal-network';
    /** @type {Map} Node centers shared by the edge and button layers. */
    const points=new Map();
    const header=[],paths=[],nodes=[];
    for(const [side,group,x] of [['backward',goals,whole?280:54],['forward',lemmas,whole?500:166]]){
      header.push('<text class="map-heading" x="'+x+'" y="17">'+(side==='forward'?'Lemmas':'Goals')+'</text>');
      group.forEach((n,i)=>points.set(n.id,{x,y:52+i*spacing,side}));
    }
    for(const [id,b] of points){
      for(const parent of steps.get(id).parents){
        const a=points.get(parent);if(!a)continue;
        const span=Math.abs(b.y-a.y);
        const bend=(b.side==='forward'?1:-1)*Math.min(whole?86:45,12+span*.18);
        paths.push('<path class="dep-edge" data-from="'+esc(parent)+'" data-to="'+esc(id)+'" d="M '+a.x+' '+(a.y+16)+' C '+(a.x+bend)+' '+(a.y+29)+' '+(b.x+bend)+' '+(b.y-32)+' '+b.x+' '+(b.y-19)+'" marker-end="url(#'+mapId+'-arrow)"/>');
      }
    }
    /** @type {Map} One visual connection per pair, retaining all recorded route labels. */
    const bridges=new Map();
    for(const link of links){
      const key=JSON.stringify([link.backward,link.forward]);
      if(!bridges.has(key))bridges.set(key,[]);
      bridges.get(key).push(link);
    }
    for(const routes of bridges.values()){
      const link=routes[0],a=points.get(link.backward),b=points.get(link.forward);
      if(!a||!b)continue;
      const chosen=link.backward===target.id&&link.forward===pair?.forward;
      const middle=(a.x+b.x)/2;
      paths.push('<path class="map-link'+(chosen?' active':'')+'" data-from="'+esc(link.forward)+'" data-to="'+esc(link.backward)+'" d="M '+(a.x+17)+' '+a.y+' C '+middle+' '+a.y+' '+middle+' '+b.y+' '+(b.x-17)+' '+b.y+'"><title>'+esc(routes.map(r=>(r.branch||r.title)+' · '+r.status).join('\n'))+'</title></path>');
    }
    for(const [id,point] of points){
      const n=steps.get(id),isGoal=n.side==='backward';
      const chosen=isGoal?id===target.id:id===pair?.forward;
      const action=isGoal?'data-map-goal': 'data-map-lemma';
      const title=n.label+' · '+n.title;
      nodes.push('<g role="button" tabindex="0" '+action+'="'+esc(id)+'" aria-pressed="'+chosen+'" aria-label="'+esc(title)+'" class="map-node '+n.side+(chosen?' active':'')+'" transform="translate('+point.x+' '+point.y+')"><title>'+esc(title)+'</title><circle r="16"/><text class="map-id" y="4">'+esc(n.label)+'</text>'+
        (whole?'<text class="map-title" text-anchor="'+(isGoal?'end':'start')+'" x="'+(isGoal?-88:88)+'" y="4">'+esc(n.title.length>25?n.title.slice(0,24).trimEnd()+'…':n.title)+'</text>':'')+'</g>');
    }
    return '<div class="network-scroll '+(whole?'full-network':'near-network')+'"><svg role="group" aria-label="'+(whole?'All goals, lemmas and their connections':'Dependencies and related forward lemmas')+'" viewBox="0 0 '+width+' '+height+'"><defs><marker id="'+mapId+'-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6Z" fill="#6c7991"/></marker></defs>'+header.join('')+paths.join('')+nodes.join('')+'</svg></div>';
  }
  /**
   * Show only the immediate decomposition of one goal, with a row per generation.
   * @param {object} graph Immutable derivation for this run edition.
   * @param {Map} steps Display labels keyed by saved step ID.
   * @param {object} target Backward goal selected by the reader.
   * @returns {string} Keyboard-accessible graph with straight dependency arrows.
   */
  function goalMap(graph,steps,target){
    const children=graph.backward.filter(node=>node.parents.includes(target.id)).map(node=>node.id);
    const rows=[target.parents,[target.id],children].filter(row=>row.length);
    const widest=Math.max(...rows.map(row=>row.length));
    const width=Math.max(180,widest*66),height=62+(rows.length-1)*76;
    /** @type {Map} Coordinates shared by the node buttons and arrow endpoints. */
    const positions=new Map();
    rows.forEach((row,level)=>row.forEach((id,column)=>{
      positions.set(id,{x:width/2+(column-(row.length-1)/2)*66,y:31+level*76});
    }));
    /** @param {string} from Parent goal. @param {string} to Direct subgoal. */
    function arrow(from,to){
      const a=positions.get(from),b=positions.get(to);
      const distance=Math.hypot(b.x-a.x,b.y-a.y);
      const dx=(b.x-a.x)/distance,dy=(b.y-a.y)/distance;
      return '<line class="dep-edge" data-from="'+esc(from)+'" data-to="'+esc(to)+'" x1="'+(a.x+20*dx)+'" y1="'+(a.y+20*dy)+'" x2="'+(b.x-22*dx)+'" y2="'+(b.y-22*dy)+'" marker-end="url(#local-goal-tip)"/>';
    }
    const edges=target.parents.map(id=>arrow(id,target.id)).concat(children.map(id=>arrow(target.id,id)));
    const nodes=Array.from(positions,([id,{x,y}])=>{
      const step=steps.get(id),active=id===target.id,title=esc(step.label+' · '+step.title);
      return '<g class="map-node backward'+(active?' active':'')+'" role="button" tabindex="0" data-map-goal="'+esc(id)+'" aria-label="'+title+'" aria-pressed="'+active+'" transform="translate('+x+' '+y+')"><title>'+title+'</title><circle r="18"/><text class="map-id" y="4">'+esc(step.label)+'</text></g>';
    });
    return '<div class="network-scroll near-network"><svg role="group" aria-label="Direct goal dependencies" style="min-width:'+Math.max(128,widest*48)+'px" viewBox="0 0 '+width+' '+height+'"><defs><marker id="local-goal-tip" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0 L5 2.5 L0 5Z" fill="#6c7991"/></marker></defs>'+edges.join('')+nodes.join('')+'</svg></div>';
  }
  /** @returns {string} Visible key shared by the focused graph and the full run. */
  function mapKey(){
    return '<div class="map-key"><span><i></i>Dependency</span><span><i></i>Alignment</span></div>';
  }
  /** @param {object} graph Saved evidence. @param {Map} steps Step lookup. @param {object} target Selected goal. @param {object} pair Selected route. */
  function overview(graph,steps,target,pair,filter,outline){
    const count=(...states)=>graph.connections.filter(link=>states.includes(link.status)).length;
    const missing=graph.backward.filter(n=>!graph.connections.some(link=>link.backward===n.id)).length;
    const filters=[['All','All',graph.connections.length],['Matches','Matched',count('Matches','aligned')],['Conditional','Conditional',count('Conditional')],['Gap','Gaps',count('Gap','open')]];
    const controls=filters.map(([value,label,total])=>'<button type="button" data-network-filter="'+value+'" aria-pressed="'+(value===filter)+'">'+label+' <b>'+total+'</b></button>').join('');
    return '<section class="run-overview" id="run-graph-overview" tabindex="-1"><header><div><h3>Run overview</h3><p>'+graph.backward.length+' goals · '+graph.forward.length+' lemmas · '+graph.connections.length+' alignment routes</p></div>'+mapFormat(outline)+'</header><div class="run-totals" role="group" aria-label="Filter alignment routes">'+controls+(missing?'<span>Unlinked goals <b>'+missing+'</b></span>':'')+'</div>'+(outline?relationMap(graph,steps,target,pair,true,filter):mapKey()+networkPlot(graph,steps,target,pair,true,filter))+'</section>';

  }
  /** @param {boolean} outline Whether the reader chose nested steps instead of circles. */
  function mapFormat(outline){
    return '<div class="map-formats" role="group" aria-label="Diagram layout"><button type="button" data-map-format="graph" aria-pressed="'+!outline+'">Graph</button><button type="button" data-map-format="outline" aria-pressed="'+outline+'">Outline</button></div>';
  }
  /** @param {object} graph Saved argument. @param {object} view Per-run focus. @param {object} ir Frozen source context. */
  function diagram(graph,view,ir){
    visibleSteps.clear();
    const {steps,target,pairs,pair}=focusOf(graph,view),lemma=pair&&steps.get(pair.forward);
    const lemmaIds=graph.forward.filter(n=>pairs.some(p=>p.forward===n.id)).map(n=>n.id),routes=pair?pairs.filter(p=>p.forward===pair.forward):[];
    const status={Matches:'Matches',Conditional:'Conditional',Gap:'Gap',aligned:'Aligned',open:'Open'};
    const statusText=pair&&status[pair.status];
    const chooser='<label class="goal-picker"><span>Subgoal</span><select data-goal-picker>'+graph.backward.map(n=>'<option value="'+esc(n.id)+'" '+(n.id===target.id?'selected':'')+'>'+esc(steps.get(n.id).label+' · '+n.title)+'</option>').join('')+'</select></label>';
    const left='<section class="goal-column"><h3>Backward goal</h3>'+chooser+'<h2>'+esc(target.title)+'</h2>'+stepReading(graph,target,ir)+jump(target.id,'Run details · '+target.label)+'</section>';
    const outline=view.mapFormat!=='graph';
    const right='<aside class="dependency-column"><h3>Goal connections</h3>'+goalMap(graph,steps,target)+'<button type="button" class="cite" data-show-overview>View run overview ↓</button></aside>';
    let middle='<p>No forward lemma is linked to this goal.</p>';
    if(pair){
      const lemmaButtons=lemmaIds.map(id=>'<button type="button" data-lemma="'+esc(id)+'" aria-pressed="'+(id===lemma.id)+'" title="'+esc(steps.get(id).title)+'">'+steps.get(id).label+'</button>').join('');
      const route=routes.length>1?'<label class="goal-picker"><span>Route</span><select data-route-picker>'+routes.map(p=>'<option value="'+p.ordinal+'" '+(p.ordinal===pair.ordinal?'selected':'')+'>'+esc(p.branch||p.title)+'</option>').join('')+'</select></label>':'';
      middle='<div class="lemma-options">'+lemmaButtons+'</div><h2>'+esc(lemma.title)+'</h2>'+stepReading(graph,lemma,ir)+route+'<div class="align-label"><b data-match="'+esc(statusText)+'">'+esc(statusText)+'</b> '+esc(routes.length>1?lemma.id+' ↔ '+target.id:(pair.branch||pair.title))+'</div>'+
        (pair.supports?.length?'<p>Use together · '+[pair.forward,...pair.supports.map(s=>s.id)].map(id=>jump(id,steps.get(id).label)).join(' + ')+'</p>':'')+jump(lemma.id,'Run details · '+lemma.label)+localPanel(graph,pair);
    }
    return '<div class="focus-layout">'+left+'<section class="lemma-column"><h3>Forward lemmas</h3>'+middle+'</section>'+right+'</div>'+overview(graph,steps,target,pair,view.networkFilter||'All',outline);
  }
  /** Cached evidence belongs to one comparison and graph edition, including refined obligations. */
  const checks=new Map();
  function proofKey(g,index,trail=[]){return JSON.stringify([g.key,g.version,index,trail]);}
  /** @param {object} graph Saved graph. @param {object} pair Selected cross-graph comparison. */
  function localPanel(graph,pair){
    const id=proofKey(graph,pair.ordinal),view=checks.get(id);
    if(!view)queueMicrotask(()=>loadCheck(graph,pair.ordinal,false));
    if(!view||view.stage==='idle'||view.stage==='loading')return '<div class="local-check"><button type="button" class="control" data-local-check="'+pair.ordinal+'">Check local obligations</button></div>';
    if(view.stage==='running')return '<p role="status">Preparing and checking local obligations…</p>';
    if(view.stage==='failed')return '<p role="alert">'+esc(view.message)+'</p><button class="control" data-local-check="'+pair.ordinal+'">Retry check</button>';
    function receipt(r,trail){
      return (r.checks||[]).map(c=>'<details class="proof-receipt"><summary>'+esc(({checked:'Checked · local lemma',counterexample:'Checked · counterexample',open:'Open'})[c.status])+' · '+esc(c.title)+'</summary><p>'+esc(c.mapping)+'</p><pre>'+esc([...c.premises,'⇒ '+c.conclusion].join('\n'))+'</pre>'+(c.assignment?'<p>'+esc(Object.entries(c.assignment).map(([k,v])=>k+' = '+v).join(', '))+'</p>':'')+'<details><summary>Rocq evidence</summary><pre>'+esc([r.environment,c.source,c.compiler,c.kernel,c.diagnostic].filter(Boolean).join('\n'))+'</pre></details></details>').join('')+
        (r.open||[]).map((o,i)=>{
          const child=[...trail,i],prior=checks.get(proofKey(graph,pair.ordinal,child));
          if(!prior)queueMicrotask(()=>loadCheck(graph,pair.ordinal,false,child));
          return '<details class="proof-receipt" data-disclosure="open-'+child.join('-')+'"><summary>Open obligation '+(i+1)+'</summary>'+markdownView(o)+(prior?.stage==='ready'?receipt(prior.receipt,child):prior?.stage==='running'?'Working…':(prior?.stage==='failed'?'<p>'+esc(prior.message)+'</p>':'')+'<button type="button" class="control" data-local-check="'+pair.ordinal+'" data-trail="'+child.join(',')+'">Continue this obligation</button>')+'</details>';
        }).join('');
    }
    return '<details class="local-check" data-disclosure="local"><summary>Local evidence · '+view.receipt.checks.length+' checks · '+view.receipt.open.length+' open</summary>'+receipt(view.receipt,[])+'</details>';
  }
  /** @param {object} graph Immutable graph. @param {number} index Exact alignment. @param {boolean} start User requested computation. */
  async function loadCheck(graph,index,start,trail=[]){
    const id=proofKey(graph,index,trail),cached=checks.get(id);
    if(cached&&(!start||['running','ready'].includes(cached.stage)))return;
    const pending={stage:start?'running':'loading'};checks.set(id,pending);if(start)refresh(graph);
    const data={key:graph.key,project:graph.project,run:graph.run,version:graph.version,index,trail};
    try{
      let r=await request(start?'check-obligation':'obligation-status',data);
      if(checks.get(id)!==pending)return;
      while(r.stage==='running'){checks.set(id,r);await new Promise(ok=>setTimeout(ok,1400));r=await request('obligation-status',data);}
      checks.set(id,r);if(r.stage!=='idle')refresh(graph);
    }catch(e){checks.set(id,{stage:'failed',message:e.message});refresh(graph);}
  }
  /** @param {object} graph Saved graph. @param {object} view Reader section and selected step.
   * @param {object} ir Source statements that were frozen for this run.
   */
  function record(graph,view,ir){
    visibleSteps.clear();
    const {steps,step}=selection(graph,view);
    const section=view.section||step.side;
    const tabs=['forward','backward','alignment'].map((side,i)=>'<button class="control" type="button" data-arg-section="'+side+'" aria-pressed="'+(section===side)+'">'+['Forward steps','Backward steps','Alignment'][i]+'</button>').join('');
    if(section==='alignment')return '<div class="action-row dag-tabs">'+tabs+'</div><div class="dag-register">'+comparisons(graph.connections,steps,graph.version===1,ir)+'</div>';
    const current=step.side===section?step:steps.get(graph[section][0].id);
    const picker=graph[section].map(node=>'<button class="step-row" type="button" data-arg-id="'+esc(node.id)+'" data-arg-target="detail" aria-pressed="'+(current.id===node.id)+'"><b>'+steps.get(node.id).label+'</b> '+esc(node.title)+'</button>').join('');
    const dependencies=current.parents.map(id=>jump(id,steps.get(id).label+' · '+steps.get(id).title)).join(' ');
    const labels={premise:'Premise',definition:'Definition',calculation:'Calculation',theorem_application:'Theorem application',goal_reduction:'Goal reduction',obligation:'Open obligation'};
    const theorem=current.theorem;
    const details=graph.version===1?markdownView(current.reason):
      '<h4>'+esc([labels[current.kind]||'Reasoning',current.structure].filter(Boolean).join(' · '))+'</h4>'+markdownView(current.reason)+
      (current.premises?.length?'<h4>Premises</h4>'+current.premises.map(text=>markdownView(text)).join(''):'')+
      (theorem?'<h4>Theorem used</h4><p><code>'+esc(theorem.name)+'</code></p>'+
        (theorem.instantiations.length?'<dl>'+theorem.instantiations.map(({parameter,value})=>'<dt>'+esc(parameter)+'</dt><dd>'+expressionView(value)+'</dd>').join('')+'</dl>':''):'')+
      (current.calculations?.length?'<h4>Calculations</h4><ol class="dag-calculations">'+current.calculations.map(line=>'<li>'+markdownView(line.operation)+math(line.formula,true)+'<details><summary>Source inputs</summary>'+sources(ir,line.sources)+'</details></li>').join('')+'</ol>':'')+
      (current.requires?.length?'<h4>Outstanding conditions</h4>'+current.requires.map(text=>markdownView(text)).join(''):'');
    return '<div class="action-row dag-tabs">'+tabs+'</div><div class="dag-record"><nav aria-label="Steps in reading order">'+picker+'</nav><article id="arg-record" tabindex="-1"><header><h3>'+current.label+' · '+esc(current.title)+'</h3>'+jump(current.id,'Show on graph','map')+'</header>'+
      (dependencies?'<div class="dag-deps">Parent steps · '+dependencies+'</div>':'')+
      '<h4>'+(section==='forward'?'Result':'Obligation')+'</h4>'+stepReading(graph,current,ir,true)+details+'<h4>Source statements</h4>'+sources(ir,current.sources)+'</article></div>';
  }
  return {diagram,record,loadCheck,focusOf,bindSymbols};
}
