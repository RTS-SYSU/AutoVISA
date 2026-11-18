"use strict";

/** @type {Object} continuationState Current immutable proposal and its latest decision/adoption observations. */
const continuationState={proposal:null,review:null};
/** @type {Object} endNames Termination reasons remain separate from proof-completion status. */
const endNames={strategy_exhausted:"本轮可用规则已执行",budget_exhausted:"达到本轮检查限额",
  goals_completed:"所选目标全部完成",execution_failed:"执行遇到问题"};
/** @type {Object} decisionNames Human-facing author choices, which never serve as proof evidence. */
const decisionNames={confirm:"确认修订",reject:"拒绝修订",request_revision:"要求补充修订"};
/** @type {Object} inheritanceReasons Reasons the child cannot attach an old receipt as applicable evidence. */
const inheritanceReasons={environment_changed:"检查环境或实现版本变化",context_changed:"上下文版本变化",
  derivation_dependency_changed:"实际依赖的推导关系已改变",exact_target_or_premises_changed:"精确目标或联合前提变化",
  goal_revised:"目标版本变化",context_revised:"上下文已有新版本",proof_not_accepted:"原尝试没有通过检查"};

/**
 * Load consent and adoption state for a proposal without changing its immutable contents.
 * @param {Object} proposal Saved W05-a proposal currently displayed.
 * @returns {Promise<void>} Rendered concrete decision and linked-run controls.
 */
async function continuationLoad(proposal){
  /** @type {Object} reviewed Exact review token, decision history and adoption summaries. */
  const reviewed=await api("/api/proposal-review?id="+encodeURIComponent(proposal.id));
  continuationState.proposal=proposal;continuationState.review=reviewed;
  continuationRender();
}

/**
 * Build a literal link to a saved run or its original proposal.
 * @param {string} run Saved execution identity.
 * @param {string} label Link text.
 * @param {string|null} proposal Optional original proposal to open within that run.
 * @returns {HTMLAnchorElement} Same-origin history link.
 */
function continuationLink(run,label,proposal=null){
  /** @type {HTMLAnchorElement} link Literal same-origin history destination. */
  const link=el("a",label,"download");
  link.href="/reasoning?run="+encodeURIComponent(run)+(proposal?"&proposal="+encodeURIComponent(proposal):"");
  return link;
}

/**
 * Display the exact mathematical decision, original route and independently budgeted adoption.
 * @returns {void}
 */
function continuationRender(){
  /** @type {Object} reviewed, proposal, plan Saved inputs and the concrete reviewed graph revision. */
  const reviewed=continuationState.review,proposal=continuationState.proposal,plan=reviewed.plan;
  $("proposal-adoption")?.remove();
  /** @type {HTMLElement} section Decision controls live beside the impact summary and before detailed differences. */
  const section=el("section","","proposal-adoption");section.id="proposal-adoption";
  section.append(el("p","DECISION → ADOPTION → LINKED RUN","eyebrow"),el("h3","确认与采用"));
  section.append(el("p",reviewed.adoptions.length?"已登记 "+reviewed.adoptions.length+" 个关联运行，原提案与原证据继续保留。":"采用后创建独立运行，使用这份提案绑定的路线版本。"));
  if(reviewed.based_on_historical_selection)section.append(el("p","本次从提案原路线建立分支；不会覆盖原运行后来选择的路线。","muted"));
  if(!plan.ready)for(const reason of plan.blockers)section.append(el("p",reason,"pending"));
  if(plan.requires_confirmation){
    section.append(el("p","关键数学决定：核对下面的具体变化，并记录你的决定。人工确认表示接受修订方案，证明仍由检查器判断。","pending"));
    /** @type {Object} change One concrete direction or joint-premise operation in the reviewed plan. */
    for(const change of plan.changes){
      section.append(el("p",change.action==="remove_connection"?"移除原方向的活动连接；原回执留在历史运行。":
        change.action==="add_pending_connection"?feedbackName(change.from)+" → "+feedbackName(change.to)+"：新增待证连接，实例化与证明均待完成。":
        "检查新联合前提对原义务的充分性。"));
    }
  }
  /** @type {Object|null} head Latest append-only decision, including a rejection or request for revision. */
  const head=reviewed.current_decision;
  if(head)section.append(el("p","最新决定："+decisionNames[head.choice]+" · "+head.actor+" · "+head.reason,"decision-current"));
  /** @type {HTMLDetailsElement} decisions Optional decision form expands automatically for critical mathematics. */
  const decisions=el("details");decisions.open=plan.requires_confirmation;
  decisions.append(el("summary",plan.requires_confirmation?"记录关键数学决定":"记录处理决定（可选）"));
  /** @type {HTMLElement} form, choice, actor, reason, save Controls for an attributable decision on this version. */
  const form=el("form"),choice=el("select"),actor=el("input"),reason=el("textarea"),save=el("button","保存决定","secondary");
  choice.id="decision-choice";actor.id="decision-actor";reason.id="decision-reason";
  actor.required=true;actor.maxLength=80;actor.value=$("feedback-actor").value||"本地用户";
  reason.required=true;reason.maxLength=4000;reason.rows=3;reason.placeholder="说明接受、拒绝或要求修订的原因";
  /** @type {string} key, label Stored decision value and its localized presentation. */
  for(const [key,label]of Object.entries(decisionNames)){
    /** @type {HTMLOptionElement} option A supported decision; incomplete plans cannot be confirmed. */
    const option=el("option",label);option.value=key;option.disabled=key==="confirm"&&!plan.ready;choice.append(option);
  }
  if(!plan.ready)choice.value="request_revision";
  /** @type {string|HTMLElement} label, control Visible caption and its associated editable field. */
  for(const [label,control]of [["决定",choice],["决定人",actor],["理由",reason]]){
    /** @type {HTMLLabelElement} caption Accessible association with the exact field identity. */
    const caption=el("label",label);caption.htmlFor=control.id;form.append(caption,control);
  }
  save.type="submit";form.append(save);decisions.append(form);section.append(decisions);
  /** @param {SubmitEvent} event Local form submission handled by the shared serialized action boundary. */
  form.addEventListener("submit",event=>{
    event.preventDefault();perform(async()=>{
      save.disabled=true;
      try{
        await api("/api/proposal-decision",{proposal:proposal.id,preview:plan.token,expected:head?.id||null,
          choice:choice.value,actor:actor.value,reason:reason.value});
        await continuationLoad(proposal);$("message").className="";$("message").textContent="决定已保存，绑定此提案的具体数学变化。";
      }finally{save.disabled=false;}
    });
  });
  /** @type {HTMLElement} controls Adoption author and a per-run limit, independent of every earlier run. */
  const controls=el("div","","adoption-controls"),budget=el("input"),author=el("input"),button=el("button",
    reviewed.adoptions.length?"再次采用并新建关联运行 →":"采用提案并开启关联运行 →","primary");
  budget.id="adoption-budget";budget.type="number";budget.min="1";budget.max="32";budget.step="1";budget.value="12";
  author.id="adoption-actor";author.value=$("feedback-actor").value||"本地用户";author.maxLength=80;
  /** @type {string|HTMLElement} label, control Visible caption and its associated editable field. */
  for(const [label,control]of [["本轮最多证明检查次数",budget],["发起人",author]]){
    /** @type {HTMLLabelElement} caption Accessible association with the exact field identity. */
    const caption=el("label",label);caption.htmlFor=control.id;controls.append(caption,control);
  }
  /** @type {boolean} approved A confirmation can authorize only this exact reviewed plan. */
  const approved=head?.choice==="confirm"&&head.preview===plan.token;
  button.disabled=!plan.ready||(plan.requires_confirmation&&!approved)||(!!head&&!approved);
  controls.append(el("p","本轮只执行本地规则与 Rocq 检查；复用证据不计为新的证明尝试。","muted"),button);
  if(button.disabled&&plan.ready)controls.append(el("p","记录对此版本的确认后，可以开启关联运行。","muted"));
  section.append(controls);
  button.addEventListener("click",()=>perform(async()=>{
    button.disabled=true;
    try{
      /** @type {Object} command Immutable adoption inputs; a retry keeps the same command identity. */
      const command={proposal:proposal.id,preview:plan.token,decision:head?.id||null,
        budget:{max_proof_attempts:Number(budget.value)},actor:author.value};
      /** @type {string} storageKey, signature Exact command binding for browser retry recovery. */
      const storageKey="autorta-adoption/"+proposal.id,signature=JSON.stringify(command);
      /** @type {Object|null} cached Previous in-flight command saved in this browser session. */
      const cached=JSON.parse(sessionStorage.getItem(storageKey)||"null");
      /** @type {string} requestId Reused for an identical retry and renewed for a deliberate new run. */
      const requestId=cached?.signature===signature?cached.id:crypto.randomUUID().replaceAll("-","");
      sessionStorage.setItem(storageKey,JSON.stringify({signature,id:requestId}));
      $("message").className="";$("message").textContent="正在核对继承证据并执行本轮证明检查，完成后保存关联运行…";
      /** @type {Object} result Saved execution or an explicit unfinished reservation. */
      const result=await api("/api/adopt-proposal",{...command,request_id:requestId});
      if(!result.result){
        $("message").textContent="关联运行已登记，尚无完成记录；再次点击会查询同一运行。";
        return;
      }
      sessionStorage.removeItem(storageKey);
      await openRun(result.run);await loadHistory();
      $("message").textContent="关联运行已保存："+(endNames[result.result.end_reason]||result.result.status)+"。查看新图、证据继承和开放义务。";
    }finally{button.disabled=false;}
  }));
  if(reviewed.decisions.length){
    /** @type {HTMLDetailsElement} history Read-only sequence of original decision records. */
    const history=el("details");history.append(el("summary","决定历史 · "+reviewed.decisions.length+" 条"));
    /** @type {Object} item One decision, including prior rejection or confirmation. */
    for(const item of reviewed.decisions)history.append(el("p",decisionNames[item.choice]+" · "+item.actor+" · "+item.reason));
    section.append(history);
  }
  if(reviewed.adoptions.length){
    section.append(el("h4","已关联运行"));
    /** @type {Object} item Independent execution registered by an adoption command. */
    for(const item of reviewed.adoptions){
      /** @type {HTMLElement} row A finished-run link or an explicit registered-only state. */
      /** @type {HTMLElement} row Link to the child result, or its pending reservation label. */
    const row=el("p");
      if(item.status==="registered")row.append(el("span",item.run.slice(0,12)+" · 已登记，尚无完成记录"));
      else row.append(continuationLink(item.run,item.run.slice(0,12)+" · "+(endNames[item.end_reason]||item.status)));
      section.append(row);
    }
  }
  $("proposal-panel").insertBefore(section,$("proposal-panel").querySelector(".proposal-diff"));
}

/**
 * Show parentage, per-run usage, exact inheritance and children beside the current graph.
 * @returns {Promise<void>} Rendered lineage for either an original or linked execution.
 */
async function continuationLineage(){
  /** @type {Object} run Original or revised immutable execution currently shown. */
  const run=state.run,children=await api("/api/linked-runs?run="+encodeURIComponent(run.id));
  /** @type {HTMLElement} panel Parent/child navigation and evidence inheritance summary. */
  const panel=$("run-lineage");panel.hidden=!run.parent&&!children.length;panel.replaceChildren();
  if(panel.hidden)return;
  panel.append(el("p","LINKED EXECUTION","eyebrow"),el("h2",run.parent?"关联运行与证据继承":"此运行的后续分支"));
  if(run.parent){
    panel.append(continuationLink(run.parent,"打开原运行 ↗"),document.createTextNode("　"),
      continuationLink(run.parent,"查看采用的提案与决定 ↗",run.proposal));
    /** @type {number} reused, rechecked Distinct old receipts attached or excluded in the child. */
    /** @type {HTMLAnchorElement} comparison Open the actual direct parent/child version picker. */
    const comparison=el("a","比较父子运行 →","download");comparison.href="/compare?child="+encodeURIComponent(run.id);panel.append(el("p"),comparison);
    const reused=run.inheritance.filter(item=>item.disposition==="reused").length;
    const rechecked=run.inheritance.length-reused;
    panel.append(el("p",(endNames[run.end_reason]||run.status)+" · 本轮检查 "+run.usage.proof_attempts+" / "+run.budget.max_proof_attempts+
      " 次 · 复用 "+reused+" 份原回执 · "+rechecked+" 份原回执未直接复用"));
    panel.append(el("p","这是读取父运行历史的修订过程。原模型与目标保持绑定，各节点状态按实际证据显示。","muted"));
    /** @type {Object} total Known ancestry usage; legacy unknown cost remains explicitly unknown. */
    const total=run.cumulative_usage;
    panel.append(el("p","沿此父链已知证明尝试："+total.known_proof_attempts+"；本轮外部调用费用："+run.usage.external_cost_usd+
      "。"+(total.unknown_cost_runs.length?"历史中有 "+total.unknown_cost_runs.length+" 轮费用未记录，继续保留待核对状态。":""),"muted"));
    /** @type {HTMLDetailsElement} details Individual inheritance decisions with original receipt links. */
    const details=el("details");details.append(el("summary","逐项查看证据继承与重检原因"));
    /** @type {Object} item One checked receipt and its precise reuse or recheck reasons. */
    for(const item of run.inheritance){
      /** @type {HTMLElement} row, link Read-only explanation and original evidence destination. */
      const row=el("p"),link=el("a",item.attempt.slice(0,12)+" ↗");
      link.href="/api/derivation-evidence?run="+encodeURIComponent(item.from_run)+"&attempt="+encodeURIComponent(item.attempt);
      link.target="_blank";link.rel="noopener";
      row.append(link,document.createTextNode(" · "+(item.disposition==="reused"?"已复用":item.reasons.map(reason=>inheritanceReasons[reason.code]||reason.code).join("；"))));
      details.append(row);
    }
    panel.append(details);
  }
  /** @type {Object} child One linked execution, including failed, partial or unfinished outcomes. */
  for(const child of children){
    /** @type {HTMLElement} row Link to the child result, or its pending reservation label. */
    const row=el("p");
    row.append(child.status==="registered"?el("span",child.run.slice(0,12)+" · 已登记"):
      continuationLink(child.run,"后续运行 "+child.run.slice(0,12)+" · "+(endNames[child.end_reason]||child.status)));
    panel.append(row);
  }
}
