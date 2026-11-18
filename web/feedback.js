"use strict";

/** @type {Object} feedbackState Saved proposal selection; original derivation state remains owned by reasoning.js. */
const feedbackState={run:null,proposal:null};
/** @type {Object} proposalStatus Human-facing proposal states, separate from proof outcomes. */
const proposalStatus={draft:"待核对提案",reviewed_no_change:"核对完成 · 数学内容不变",needs_details:"待补充说明"};
/** @type {Object} taskNames Labels for actual pending or recorded work. */
const taskNames={prove_claim:"证明新增义务",check_joint_sufficiency:"检查联合前提的充分性",
  condition_audit:"核对条件归属",alignment_audit:"核对方向与实例化",
  check_reverse_implication:"证明反向蕴含",supply_instantiation:"补全反向实例化",
  prepare_scope_variant:"明确新范围与目标",clarify_request:"明确反馈要求"};

/**
 * Name a node or relation without inventing a checked outcome.
 * @param {string} key Stable graph identity.
 * @returns {string} Human-readable label with a stable-key fallback.
 */
function feedbackName(key){
  /** @type {Object|undefined} node Original graph claim addressed by this key. */
  const node=state.run.graph.nodes.find(item=>item.key===key);
  /** @type {Object|undefined} alignment Direction is taken from the current run, including adopted reversals. */
  const alignment=state.run.graph.alignments.find(item=>item.key===key);
  if(alignment)return feedbackName(alignment.from)+" → "+feedbackName(alignment.to);
  return node?title(node):({trace_to_tasks:"接受轨迹 → 逐任务见证",response_bridge:"调度桥接义务",
    proposed_service_lower:"截止期前的服务下界",proposed_service_upper:"执行服务不超过作业需求",
    proposed_bridge_from_bounds:"服务上下界 → 原调度桥接义务"}[key]||key);
}

/**
 * Populate all addressable targets from the actual saved graph.
 * @returns {void}
 */
function feedbackTargets(){
  /** @type {string} previous Previously selected target, retained for a route refresh of the same run. */
  const previous=feedbackState.run===state.run.id?$("feedback-target").value:"";
  $("feedback-target").replaceChildren();
  for(const [kind,family,label]of [["node","nodes","节点"],["alignment","alignments","对齐"],["edge","edges","推导"]]){
    for(const item of state.run.graph[family]){
      /** @type {HTMLOptionElement} option Exact target reference; labels never become executable content. */
      const option=el("option",label+" · "+(kind==="edge"?item.premises.map(feedbackName).join(" ∧ ")+" → "+feedbackName(item.conclusion):feedbackName(item.key)));
      option.value=JSON.stringify({kind,key:item.key});$("feedback-target").append(option);
    }
  }
  if(previous&&[...$("feedback-target").options].some(option=>option.value===previous))$("feedback-target").value=previous;
  else $("feedback-target").value=JSON.stringify({kind:"node",key:"response_bridge"});
  feedbackState.run=state.run.id;feedbackExamples();
}

/**
 * Address a graph object from its detail or alignment card.
 * @param {string} kind Graph family: node, alignment or edge.
 * @param {string} key Exact identity in that family.
 * @param {boolean} scroll Whether to bring the form into view.
 * @returns {void}
 */
function feedbackTarget(kind,key,scroll=false){
  $("feedback-target").value=JSON.stringify({kind,key});feedbackExamples();
  if(scroll){$("feedback-workspace").scrollIntoView({behavior:"smooth",block:"start"});$("feedback-text").focus({preventScroll:true});}
}

/**
 * Offer concrete examples without submitting or replacing existing text automatically.
 * @returns {void}
 */
function feedbackExamples(){
  if(!$("feedback-target").value)return;
  /** @type {Object} target Current addressed object, independent of the graph's selected node. */
  const target=JSON.parse($("feedback-target").value);
  /** @type {boolean} split Whether this run already contains the reviewed service-bound decomposition. */
  const split=state.run.graph.nodes.some(item=>item.key==="proposed_service_lower");
  /** @type {Array<Array<string>>} examples Supported local actions suitable for this target. */
  const examples=target.kind==="alignment"?
    [["核对方向","alignment_review","检查这个对齐的蕴含方向、实例化和所需条件。"],["核对间隔","arrival_condition","检查这里是否遗漏了最小释放间隔条件。"]]:
    split&&["response_bridge","proposed_service_lower","proposed_service_upper"].includes(target.key)?
      [["推进服务证明","advance_service","推进服务上下界证明，保留原模型条件并记录未完成义务。"]]:
    target.key==="response_bridge"?
      [["拆分义务","split_bridge","把这个调度桥接义务拆成服务下界和服务上界，保留原模型条件。"],["核对间隔","arrival_condition","检查这个义务中的最小释放间隔条件。"]]:
      [["核对间隔","arrival_condition","核对最小释放间隔条件在哪里使用。"]];
  $("feedback-examples").replaceChildren();
  for(const [label,intent,text]of examples){
    /** @type {HTMLButtonElement} button Explicit example selected by the author before submission. */
    const button=el("button",label,"secondary");button.type="button";
    button.addEventListener("click",()=>{$("feedback-intent").value=intent;$("feedback-text").value=text;});
    $("feedback-examples").append(button);
  }
}

/**
 * Restore proposal history for the current run, optionally selecting a new submission.
 * @param {string|null} preferred Newly submitted proposal identity, if present.
 * @returns {Promise<void>} Rendered history and the selected saved proposal.
 */
async function feedbackLoad(preferred=null){
  /** @type {Array<Object>} entries Immutable summaries belonging only to the current execution. */
  const entries=await api("/api/feedback?run="+encodeURIComponent(state.run.id));
  $("feedback-history").replaceChildren();
  for(const item of entries){
    const option=el("option",item.created_at.slice(5,16).replace("T"," ")+" · "+item.title);
    option.value=item.id;$("feedback-history").append(option);
  }
  /** @type {string|null} requested Identity retained across a browser refresh through its URL. */
  const requested=preferred||new URLSearchParams(location.search).get("proposal");
  const selected=entries.find(item=>item.id===requested)||entries.at(-1);
  if(selected){$("feedback-history").value=selected.id;await feedbackOpen(selected.id);}
  else{
    const option=el("option","暂无提案");option.value="";$("feedback-history").append(option);
    feedbackState.proposal=null;$("proposal-panel").replaceChildren(el("p","REVIEWABLE CHANGES","eyebrow"),
      el("h3","等待一条具体反馈"),el("p","提交后查看具体差异、受影响目标与新增检查任务。","muted"));
  }
}

/**
 * Read one saved proposal and make the selected history entry refreshable.
 * @param {string} id Immutable proposal identity.
 * @returns {Promise<void>} Proposal rendered after verification by the shared service.
 */
async function feedbackOpen(id){
  /** @type {Object} proposal Verified result; its impact remains bound to its original route revision. */
  const proposal=await api("/api/proposal?id="+encodeURIComponent(id));
  if(proposal.run!==state.run.id)throw new Error("提案不属于当前运行。");
  feedbackState.proposal=proposal;$("feedback-history").value=id;feedbackRender(proposal);
  await continuationLoad(proposal);
  const query=new URLSearchParams(location.search);query.set("proposal",id);
  if(state.pinnedSelection)query.set("selection",state.pinnedSelection);
  window.history.replaceState(null,"","/reasoning?"+query);
}

/**
 * Render exact mathematical or relation content in a compact comparison cell.
 * @param {*} value Saved before/after field, never interpreted as HTML.
 * @returns {string} Literal display preserving formal statements and relation direction.
 */
function feedbackValue(value){
  if(value===null||value===undefined)return "无此项";
  if(typeof value!=="object")return typeof value==="string"?feedbackName(value):String(value);
  if(value.formal)return value.formal;
  if(value.premises)return value.premises.map(feedbackName).join(" ∧ ")+"\n⇒ "+feedbackName(value.conclusion)+"\n检查状态："+(value.outcome==="pending"?"待检查":value.outcome);
  if(value.kind==="condition_audit")return "条件："+value.condition+"（原上下文已有）"
    + "\n使用位置："+value.owners.map(feedbackName).join("；")
    + "\n形式定义："+value.kernel_binding.source_file+":"+value.kernel_binding.line
    + "\n论文来源："+value.source_keys.map(key=>sourceNames[key]||key).join("；");
  if(value.from)return feedbackName(value.from)+"\n⇒ "+feedbackName(value.to)+
    "\n实例化："+(value.instantiation?Object.entries(value.instantiation).map(([key,term])=>key+" := "+bindingText(term)).join("；"):"待建立")+"\n条件："+(value.conditions?.join("；")||"待明确")+
    (value.status?"\n状态："+(value.status==="candidate"?"待检查":value.status==="checked"?"已检查":value.status):"");
  return JSON.stringify(value,null,2);
}

/**
 * Show concrete differences, selected-route impact, future checks and source provenance.
 * @param {Object} proposal Verified immutable proposal and current-route observation.
 * @returns {void}
 */
function feedbackRender(proposal){
  /** @type {HTMLElement} panel Single review surface for the selected saved proposal. */
  const panel=$("proposal-panel");panel.replaceChildren(el("p","REVISION PROPOSAL","eyebrow"),el("h3",proposal.title));
  /** @type {HTMLElement} facts Concise interpretation and verification state. */
  const facts=el("div","","proposal-facts");
  for(const value of [proposalStatus[proposal.status],"本地规则","采用记录见下方",proposal.checks.types==="passed"?"IR 类型检查通过":"未新增形式命题","证明检查未运行"])facts.append(el("span",value));
  panel.append(facts,el("p","原反馈 · "+proposal.request.actor+" · "+feedbackName(proposal.request.target.key),"muted"),
    el("div",proposal.request.text,"proposal-original"),el("p","处理依据："+proposal.interpretation.join("；"),"muted"));
  if(proposal.observation.based_on_historical_selection)panel.append(el("p","本提案基于历史路线 "+proposal.selection.slice(0,12)+"；下方影响仍按该版本计算。","pending"));
  if(proposal.requires_math_confirmation)panel.append(el("p","该提案涉及关键数学决策，采用前需要人工确认。","pending"));
  for(const finding of proposal.findings)panel.append(el("p",finding));
  if(proposal.target_snapshot.formal){
    const original=el("details");original.append(el("summary","原义务完整陈述（保持不变）"),el("pre",proposal.target_snapshot.formal));panel.append(original);
  }
  for(const change of proposal.changes){
    /** @type {HTMLElement} card Difference card with literal, inspectable before/after values. */
    const card=el("section","","proposal-diff"),columns=el("div","","proposal-columns");
    card.append(el("h4",change.label));
    for(const [label,value,style]of [["修改前",change.before,"before"],["提案内容",change.after,"after"]]){
      const cell=el("div","",style);cell.append(el("h5",label),el("pre",feedbackValue(value)));columns.append(cell);
    }
    card.append(columns);panel.append(card);
  }
  if(!proposal.changes.length)panel.append(el("p","尚未形成数学修改；反馈原文已保存。","pending"));
  /** @type {HTMLTableElement} table Prospective scope and evidence impact, separate from original proof status. */
  const table=el("table","","proposal-table");
  for(const [label,value]of [
    ["候选路线涉及",proposal.impact.candidate_roots.map(feedbackName).join("；")||"无登记目标"],
    ["所选路线涉及",proposal.impact.selected_roots.map(feedbackName).join("；")||"当前路线不依赖该对象"],
    ["目标与模型",proposal.scope.model==="unchanged"?"原模型条件与登记目标保持不变":"范围修改请求待明确"],
    ["原运行与证据","原版本保持原样；采用后另存关联运行"],
    ["原路线版本",proposal.selection.slice(0,16)]]){
    const row=el("tr");row.append(el("th",label),el("td",value));table.append(row);
  }
  const impactHeading=el("h3","影响范围");
  panel.insertBefore(impactHeading,panel.querySelector(".proposal-diff"));
  panel.insertBefore(table,panel.querySelector(".proposal-diff"));
  panel.append(el("h3","后续检查"));
  for(const task of proposal.tasks){
    const card=el("div","","proposal-task");
    card.append(el("strong",taskNames[task.kind]||task.kind),el("p",task.status==="open"?"待完成":"核对记录已保存","muted"));
    if(task.formal){const details=el("details");details.append(el("summary","查看精确待证命题"),el("pre",task.formal));card.append(details);}
    panel.append(card);
  }
  /** @type {HTMLDetailsElement} evidence Original receipts are links, never repainted as proof of the new proposal. */
  const evidence=el("details");evidence.append(el("summary","相关证据 · "+new Set(proposal.impact.evidence.map(item=>item.attempt)).size+" 份原始回执"));
  for(const item of proposal.impact.evidence){
    const row=el("p"),link=el("a",item.object+" ↗");
    link.href="/api/derivation-evidence?run="+encodeURIComponent(proposal.run)+"&attempt="+encodeURIComponent(item.attempt);link.target="_blank";link.rel="noopener";
    row.append(link,document.createTextNode(" · "+(item.disposition==="preserved"?"保留":"采用后需重新检查")+" · "+item.reason));evidence.append(row);
  }
  panel.append(evidence);
  /** @type {HTMLDetailsElement} provenance Original semantic revision and anchored source excerpts. */
  const provenance=el("details");provenance.append(el("summary","来源与修订绑定"),el("p","冻结："+proposal.freeze+"\n语义修订："+proposal.review_revision));
  for(const [key,binding]of Object.entries(proposal.sources)){
    const source=el("details");source.append(el("summary",sourceNames[key]||key),el("p",binding.summary));
    for(const reference of binding.sources)for(const anchor of reference.anchors){
      const quote=el("p",anchor.quote,"source-quote"),link=el("a","原文第 "+anchor.page+" 页 ↗");
      link.href="/api/image?extraction="+encodeURIComponent(anchor.extraction_id)+"&page="+anchor.page;link.target="_blank";link.rel="noopener";
      source.append(quote,link);
    }
    provenance.append(source);
  }
  panel.append(provenance);
  const download=el("a","查看完整提案记录 ↗","download");download.href="/api/proposal?id="+encodeURIComponent(proposal.id);download.target="_blank";download.rel="noopener";panel.append(download);
}

$("feedback-target").addEventListener("change",feedbackExamples);
$("feedback-history").addEventListener("change",()=>{if($("feedback-history").value)perform(()=>feedbackOpen($("feedback-history").value));});
$("feedback-form").addEventListener("submit",event=>{
  event.preventDefault();perform(async()=>{
    $("feedback-submit").disabled=true;$("message").className="";$("message").textContent="正在形成修订提案并计算影响…";
    try{
      /** @type {Object} request Exact feedback authoring context; submitting does not adopt the proposal. */
      const request={run:state.run.id,selection:state.run.selection.id,target:JSON.parse($("feedback-target").value),
        text:$("feedback-text").value,actor:$("feedback-actor").value,intent:$("feedback-intent").value};
      const proposal=await api("/api/feedback",request);await feedbackLoad(proposal.id);
      $("message").textContent="反馈与提案已保存。查看差异、影响和待完成检查。";
    }finally{$("feedback-submit").disabled=false;}
  });
});
