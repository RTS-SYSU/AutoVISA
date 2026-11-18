/** Local derivation client: every mathematical and evidence state is read from the workspace Interface. */
"use strict";

/** @type {Object} state Current mapping, actual execution, selection and same-origin write token. */
const state = {mapping:null,run:null,token:"",active:null,busy:false,pinnedSelection:null};
/** @type {Object<string,string>} names Localized original target names; internal identities stay unchanged. */
const names = {"fig3_acceptance_soundness":"Fig.3 接受充分性","fig3_exactness":"Fig.3 精确性",
  "dm_optimality":"DM 优先级最优性","fp_soundness":"固定优先级充分性"};
/** @type {Object<string,string>} sourceNames Human-readable labels for semantic source bindings. */
const sourceNames={fig3:"Fig.3 迭代测试",parameter_order:"任务参数约束",sporadic_separation:"最小释放间隔",dm_priority:"DM 优先级",sporadic_deadline:"截止期约束",fig3_acceptance_soundness:"接受充分性目标"};

/**
 * Resolve a fixed page element.
 * @param {string} id Authored HTML element identity.
 * @returns {HTMLElement} Matching page element.
 */
function $(id){return document.getElementById(id);}

/**
 * Build literal text content.
 * @param {string} tag HTML element name.
 * @param {string} text Display text, never interpreted as markup.
 * @param {string} className Optional presentation class.
 * @returns {HTMLElement} Detached node.
 */
function el(tag,text="",className=""){
  /** @type {HTMLElement} element Safe container for source and mathematical text. */
  const element=document.createElement(tag);element.textContent=text;element.className=className;return element;
}

/**
 * Call the shared local Interface.
 * @param {string} path Fixed endpoint and encoded identifiers.
 * @param {Object|null} body Optional JSON command.
 * @returns {Promise<Object>} Verified response or rejection.
 */
async function api(path,body=null){
  /** @type {Response} response Same-origin transport carrying the session token only for commands. */
  const response=await fetch(path,body===null?{}:{method:"POST",headers:{"Content-Type":"application/json","X-Review-Token":state.token},body:JSON.stringify(body)});
  /** @type {Object} value Result whose status is checked before it enters application state. */
  const value=await response.json();if(!response.ok)throw new Error(value.message||"操作失败");return value;
}

/**
 * Serialize actions and show their actual outcome.
 * @param {Function} action Awaitable action owning the current page transition.
 * @returns {Promise<void>} Completion after restoring interaction.
 */
async function perform(action){
  if(state.busy)return;state.busy=true;$("derive").disabled=true;
  for(const picker of document.querySelectorAll("select"))picker.disabled=true;
  try{await action();}catch(error){$("message").textContent=error.message;$("message").className="error";}
  finally{state.busy=false;$("derive").disabled=!state.mapping;for(const picker of document.querySelectorAll("select"))picker.disabled=picker.dataset.pinned==="true";}
}

/**
 * Read a claim's user-facing name.
 * @param {Object} claim Graph claim with stable identity and optional label.
 * @returns {string} Display name.
 */
function title(claim){return names[claim.key.replace("goal/","")]||claim.title;}

/**
 * Display the typed variable substitutions used by an alignment.
 * @param {Object} value Verified IR variable or application, used only as literal presentation text.
 * @returns {string} Readable mathematical expression.
 */
function bindingText(value){
  if(value.op==="var")return value.name;
  if(value.op==="nat")return String(value.value);
  if(value.op==="call"){
    /** @type {string} symbol Fixed model name matching the saved typed application. */
    const symbol={prefix:"firstn",ir_initial:"initial"}[value.symbol]||value.symbol;
    return "("+symbol+(value.args.length?" "+value.args.map(bindingText).join(" "):"")+")";
  }
  return JSON.stringify(value);
}

/**
 * Restore the execution picker without changing proof data.
 * @returns {Promise<void>} Saved runs loaded into the picker.
 */
async function loadHistory(){
  /** @type {Array<Object>} runs Immutable executions belonging to the selected mapping. */
  const runs=await api("/api/derivations?mapping="+encodeURIComponent(state.mapping.id));
  $("runs").replaceChildren(el("option","选择已保存运行"));
  $("runs").firstChild.value="";
  for(const run of runs){
    /** @type {HTMLOptionElement} option One actual execution, with its creation time. */
    const option=el("option",run.created_at.slice(0,19).replace("T"," ")+" · "+run.id.slice(0,8));
    option.value=run.id;option.disabled=run.status==="registered";$("runs").append(option);
  }
  if(state.run)$("runs").value=state.run.id;
}

/**
 * Load one complete run through the same Interface used by the CLI.
 * @param {string} id Saved execution identity.
 * @param {string|null} selection Exact route revision from a saved comparison, or null for the current head.
 * @returns {Promise<void>} Rendered graph and current selected route.
 */
async function openRun(id,selection=null){
  state.pinnedSelection=selection;
  state.run=await api("/api/derivation?id="+encodeURIComponent(id)+(selection?"&selection="+encodeURIComponent(selection):""));
  state.active=null;render();$("runs").value=id;
  window.history.replaceState(null,"","/reasoning?run="+encodeURIComponent(id)+(selection?"&selection="+encodeURIComponent(selection):""));
  await feedbackLoad();await continuationLineage();
}

/**
 * Create an SVG element with authored geometric attributes.
 * @param {string} tag SVG tag.
 * @param {Object} attrs Attribute values determined by the graph layout.
 * @param {string} text Optional literal label.
 * @returns {SVGElement} Detached graphical element.
 */
function svg(tag,attrs={},text=""){
  /** @type {SVGElement} element Namespace-correct diagram primitive. */
  const element=document.createElementNS("http://www.w3.org/2000/svg",tag);
  for(const [key,value]of Object.entries(attrs))element.setAttribute(key,String(value));
  element.textContent=text;return element;
}

/**
 * Render claim nodes and AND-premise hyperedges in directional columns.
 * @returns {void}
 */
function drawGraph(){
  /** @type {SVGElement} canvas Diagram surface; positions indexes stable claim identities. */
  const canvas=$("graph"),positions=new Map();canvas.replaceChildren();
  /** @type {Array<Array>} columns Forward facts, backward obligations and original roots. */
  const columns=[["forward","前向候选",30],["backward","后向义务",430],["root","登记目标",830]];
  for(const [side,label,x]of columns){
    canvas.append(svg("text",{x,y:30,class:"graph-heading"},label));
    state.run.graph.nodes.filter(node=>node.side===side).forEach((node,index)=>positions.set(node.key,{x,y:60+index*115}));
  }
  /** @type {number} height All new obligations remain in the visible diagram view box. */
  const height=Math.max(440,...columns.map(([side])=>100+115*state.run.graph.nodes.filter(node=>node.side===side).length));
  canvas.setAttribute("viewBox","0 0 1120 "+height);
  /** @type {SVGElement} definitions Arrowhead used for every directed implication. */
  const definitions=svg("defs"),marker=svg("marker",{id:"arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:6,markerHeight:6,orient:"auto-start-reverse"});
  marker.append(svg("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#618b83"}));definitions.append(marker);canvas.append(definitions);
  for(const edge of state.run.graph.edges){
    if(!edge.premises.length)continue;
    /** @type {Object} target Exact conclusion position; reversed alignments enter its right boundary. */
    const target=positions.get(edge.conclusion);
    /** @type {boolean} leftward True when every premise is to the right of the conclusion. */
    const leftward=edge.premises.every(key=>positions.get(key).x>target.x);
    /** @type {Object} joint Visible conjunction point before the appropriate conclusion boundary. */
    const joint={x:leftward?target.x+305:Math.max(5,target.x-45),y:target.y+(edge.key==="via_jobs"?58:27)};
    /** @type {string} style Selected and alternative routes have distinct line styles. */
    const style="graph-edge"+(state.run.selection.choices[edge.conclusion]===edge.key?" selected":"");
    for(const premise of edge.premises){
      /** @type {Object} start Location of one jointly required premise. */
      const start=positions.get(premise);
      /** @type {number} exit, bend, approach Control points keep a reversed edge outside both nodes. */
      const exit=start.x+(leftward?0:260),bend=exit+(leftward?-35:35),approach=joint.x+(leftward?30:-30);
      canvas.append(svg("path",{class:style,d:`M ${exit} ${start.y+37} C ${bend} ${start.y+37}, ${approach} ${joint.y}, ${joint.x} ${joint.y}`}));
    }
    canvas.append(svg("path",{class:style,d:`M ${joint.x} ${joint.y} L ${leftward?target.x+265:target.x-5} ${joint.y}`,"marker-end":"url(#arrow)"}));
    if(edge.premises.length>1){
      canvas.append(svg("circle",{cx:joint.x,cy:joint.y,r:11,class:"graph-joint"}),svg("text",{x:joint.x,y:joint.y+4,"text-anchor":"middle",class:"graph-joint-label"},"∧"));
    }
  }
  for(const claim of state.run.graph.nodes){
    /** @type {Object} point Geometric position of this claim; group is its accessible clickable view. */
    const point=positions.get(claim.key),group=svg("g",{class:"graph-node "+(claim.complete?"complete":"open"),
      role:"button",tabindex:0,"aria-label":title(claim),"data-node":claim.key,transform:`translate(${point.x},${point.y})`});
    group.append(svg("rect",{width:260,height:76,rx:10}),svg("text",{x:15,y:26,class:"node-title"},title(claim).slice(0,17)),
      svg("text",{x:15,y:47,class:"node-title"},title(claim).slice(17,33)),
      svg("text",{x:15,y:65,class:"node-status"},claim.complete?"● 已证明":claim.statement?"○ 开放义务":"○ 尚未编码"));
    group.addEventListener("click",()=>details(claim.key));
    group.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();details(claim.key);}});
    canvas.append(group);
  }
}

/**
 * Render a restored execution without inferring success from graph connectivity.
 * @returns {void}
 */
function render(){
  /** @type {HTMLElement} version Exact historical route label and an explicit link to the current view. */
  const version=$("route-version");version.replaceChildren();
  version.append(el("span",(state.pinnedSelection?"固定路线版本 · ":"当前路线版本 · ")+state.run.selection.id));
  if(state.pinnedSelection){
    /** @type {HTMLAnchorElement} current Deliberate navigation away from the fixed historical selection. */
    const current=el("a","查看当前路线 ↗","download");current.href="/reasoning?run="+encodeURIComponent(state.run.id);version.append(current);
  }
  $("empty-graph").hidden=true;$("workspace").hidden=false;$("overview").hidden=false;
  /** @type {Array<Object>} nodes Candidate claims; count uses only actual complete proof receipts. */
  const nodes=state.run.graph.nodes;
  $("overview").replaceChildren();
  /** @type {Object|undefined} primary Actual saved status of the user-selected primary target. */
  const primary=state.run.plan.find(item=>item.root==="goal/"+state.mapping.ir.primary);
  for(const [label,value,note]of [["已证明局部命题",nodes.filter(node=>node.complete).length,"实际 Rocq 证据"],
      ["已检查对齐",state.run.graph.alignments.filter(item=>item.status==="checked").length,"含显式实例化"],
      ["登记目标",state.run.graph.roots.length,"全部目标保留"],["主要目标",primary?.status==="proved"?"已证明":"未证明",primary?.open.length?"仍有开放证明义务":"按实际证据显示"]]){
    /** @type {HTMLElement} card Compact summary of the saved run. */
    const card=el("div","","reasoning-stat");card.append(el("span",label),el("strong",String(value)),el("small",note));$("overview").append(card);
  }
  $("run-export").href="/api/derivation?id="+encodeURIComponent(state.run.id)+(state.pinnedSelection?"&selection="+encodeURIComponent(state.pinnedSelection):"");
  drawGraph();$("routes").replaceChildren();$("alignments").replaceChildren();
  for(const obligation of state.run.plan){
    /** @type {Object} claim Root whose alternative routes remain independently selectable. */
    const claim=nodes.find(item=>item.key===obligation.root);
    const card=el("div","","route-card");card.append(el("strong",title(claim)));
    /** @type {Array<Object>} routes Candidate sufficient derivations for this exact root. */
    const routes=state.run.graph.edges.filter(edge=>edge.conclusion===claim.key);
    if(routes.length){
      const picker=el("select");picker.setAttribute("aria-label",title(claim)+"的推导路线");
      picker.dataset.pinned=String(!!state.pinnedSelection);picker.disabled=!!state.pinnedSelection;
      for(const route of routes){const option=el("option",route.key==="via_witness"?"工作量见证 → 调度保证":"按任务和作业直接分解");option.value=route.key;picker.append(option);}
      picker.value=state.run.selection.choices[claim.key];
      picker.addEventListener("change",()=>perform(async()=>{
        /** @type {Object} choices Complete selected-route revision with one changed root. */
        const choices={...state.run.selection.choices,[claim.key]:picker.value};
        $("message").className="";$("message").textContent="正在保存路线…";
        await api("/api/select-route",{run:state.run.id,expected:state.run.selection.id,choices});
        await openRun(state.run.id);$("message").textContent="路线已保存，原候选与历史选择均保留。";
      }));card.append(picker);
    }
    card.append(el("p","开放："+obligation.open.map(key=>title(nodes.find(node=>node.key===key))).join("；"),"open-list"));
    $("routes").append(card);
  }
  for(const alignment of state.run.graph.alignments){
    /** @type {HTMLElement} card Direction, instantiation and actual implication-check status. */
    const card=el("div","","alignment-card");
    /** @type {string} substitution The actual current direction's bindings, including an unresolved reverse relation. */
    const substitution=alignment.instantiation?Object.entries(alignment.instantiation).map(([key,value])=>key+" := "+bindingText(value)).join("\n"):"等待建立实例化";
    card.append(el("strong",title(nodes.find(node=>node.key===alignment.from))+" → "+title(nodes.find(node=>node.key===alignment.to))),
      el("p",alignment.status==="checked"?"该方向的条件充分性已检查。":"该方向仍待证明与实例化。"),
      el("pre",substitution+"\n条件："+(alignment.conditions?.join("；")||"待明确")));
    /** @type {HTMLButtonElement} feedbackButton Address the current alignment direction, including adopted revisions. */
    const feedbackButton=el("button","对此对齐反馈","secondary");
    feedbackButton.addEventListener("click",()=>feedbackTarget("alignment",alignment.key,true));card.append(feedbackButton);
    $("alignments").append(card);
  }
  feedbackTargets();
  if(nodes.length)details(nodes[0].key);
  if(state.run.error){$("message").textContent=state.run.error.message;$("message").className="error";}
}

/**
 * Show a node's exact proposition, original source anchors and proof references.
 * @param {string} key Claim identity within the current graph.
 * @returns {void}
 */
function details(key){
  state.active=key;
  /** @type {Object} claim Exact candidate selected in the diagram. */
  const claim=state.run.graph.nodes.find(item=>item.key===key);$("detail-title").textContent=title(claim);
  $("details").replaceChildren(el("span",claim.complete?"已证明":"开放义务","badge"),el("pre",claim.formal||"此所选目标尚未编码；原目标继续保留。"));
  for(const group of $("graph").querySelectorAll("[data-node]"))group.classList.toggle("active",group.dataset.node===key);
  /** @type {HTMLButtonElement} feedbackButton Connect this exact node to the feedback form. */
  const feedbackButton=el("button","对这个节点提出反馈","secondary");
  feedbackButton.addEventListener("click",()=>feedbackTarget("node",key,true));$("details").append(feedbackButton);
  $("details").append(el("p","绑定核对修订 "+claim.review_revision.slice(0,12),"muted"));
  for(const edge of state.run.graph.edges.filter(item=>item.conclusion===key)){
    $("details").append(el("p","联合前提："+(edge.premises.map(p=>title(state.run.graph.nodes.find(n=>n.key===p))).join(" ∧ ")||"基础定义")),
      el("p","推导检查："+({complete:"完整证明通过",conditional:"条件充分性通过"}[edge.outcome]||edge.outcome),"muted"));
  }
  /** @type {Set<string>} attempts Actual complete or conditional evidence associated with this claim. */
  const attempts=new Set([...claim.attempts,...state.run.graph.edges.filter(edge=>edge.conclusion===key).map(edge=>edge.attempt).filter(Boolean)]);
  for(const attempt of attempts){
    const link=el("a",attempt===claim.complete?"查看完整节点证明与依赖 ↗":"查看条件证明或尝试诊断 ↗","download");link.href="/api/derivation-evidence?run="+encodeURIComponent(state.run.id)+"&attempt="+encodeURIComponent(attempt);link.target="_blank";link.rel="noopener";$("details").append(link);
  }
  for(const source of claim.source_keys){
    /** @type {Object} binding Frozen semantic interpretation and exact original source ranges. */
    const binding=state.mapping.ir.bindings[source];if(!binding)continue;
    /** @type {HTMLDetailsElement} references Expandable exact excerpts keep the proposition easy to inspect. */
    const references=el("details");references.append(el("summary",sourceNames[source]||source),el("p",binding.summary));
    $("details").append(references);
    for(const evidence of binding.sources)for(const anchor of evidence.anchors){
      const quote=el("div","","source-quote");quote.append(el("p",anchor.quote));
      const link=el("a","原文第 "+anchor.page+" 页 ↗");link.href="/api/image?extraction="+encodeURIComponent(anchor.extraction_id)+"&page="+anchor.page;link.target="_blank";link.rel="noopener";quote.append(link);references.append(quote);
    }
  }
}

$("derive").addEventListener("click",()=>perform(async()=>{
  $("message").className="";$("message").textContent="正在独立展开两侧推导并运行 Rocq 检查，完成后保存本轮图和证据。";
  const run=await api("/api/derive",{mapping:state.mapping.id});await openRun(run.id);await loadHistory();
  $("message").textContent=run.status==="failed"?"本轮执行遇到问题，已保存诊断。":"本轮推导已保存。查看绿色局部证明及尚待解决的调度义务。";
}));
$("runs").addEventListener("change",()=>{if($("runs").value)perform(()=>openRun($("runs").value));});
perform(async()=>{
  /** @type {URLSearchParams} query Immutable run or mapping selected by the preceding workbench page. */
  const query=new URLSearchParams(location.search),catalog=await api("/api/catalog");
  state.token=catalog.token;$("test-banner").hidden=!catalog.testing;
  state.pinnedSelection=query.get("selection");
  if(query.get("run"))state.run=await api("/api/derivation?id="+encodeURIComponent(query.get("run"))+(state.pinnedSelection?"&selection="+encodeURIComponent(state.pinnedSelection):""));
  const mapping=query.get("mapping")||state.run?.mapping;
  if(!mapping)throw new Error("请从冻结记录中的已检查映射进入双向推导。");
  state.mapping=await api("/api/mapping?id="+encodeURIComponent(mapping));
  $("context").textContent="case_11 · 整数时间 / 零星任务 / DM · 冻结 "+state.mapping.freeze.slice(0,12);
  await loadHistory();if(state.run){render();await feedbackLoad();await continuationLineage();}
});
