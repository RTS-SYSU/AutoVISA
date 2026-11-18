"use strict";

/** @type {Object} comparisonState Exact chosen versions, saved observation and same-origin session token. */
const comparisonState={options:null,result:null,token:"",busy:false};
/** @type {Object} captions User-facing names for known goals, routes, statuses and model fields. */
const captions={
  fig3_acceptance_soundness:"Fig.3 接受充分性",fig3_exactness:"Fig.3 精确性",
  via_witness:"工作量见证 → 调度保证",via_jobs:"按任务与作业分解",proposed_bridge_from_bounds:"服务上下界 → 调度桥接",
  proved:"已证明",unproved:"未证明",open:"开放义务",unencoded:"尚未编码",complete:"完整证明通过",conditional:"条件充分性通过",
  partial:"部分完成",failed:"执行失败",completed:"全部完成",strategy_exhausted:"本轮可用规则已执行",
  budget_exhausted:"达到本轮检查限额",execution_failed:"执行遇到问题",goals_completed:"所选目标全部完成",
  mapping:"Analysis IR 映射版本",freeze:"冻结上下文",review_revision:"语义核对修订",context:"证明上下文",checker_profile:"检查器环境版本",
  domain:"形式模型",scope:"形式化范围",definitions:"分析定义",bindings:"来源与语义绑定",kernel_bindings:"形式符号对应",primary:"主要目标",
  added:"新增",removed:"移除",modified:"修改",unchanged:"相同",shared:"两侧共用原回执",new:"子运行新增回执",historical:"仅保留于父运行",
  environment_changed:"检查环境或实现版本变化",context_changed:"上下文版本变化",derivation_dependency_changed:"实际依赖的推导关系已改变",
  exact_target_or_premises_changed:"精确目标或联合前提变化",goal_revised:"目标已有新版本",context_revised:"上下文已有新版本",
  proof_not_accepted:"原尝试未通过检查"
};

/** Resolve one authored element.
 * @param {string} id Fixed HTML identity.
 * @returns {HTMLElement} Matching element.
 */
function element(id){return document.getElementById(id);}

/** Build literal text without interpreting saved feedback as markup.
 * @param {string} tag HTML tag.
 * @param {string} text Literal visible text.
 * @param {string} className Optional authored style class.
 * @returns {HTMLElement} Detached element.
 */
function make(tag,text="",className=""){
  /** @type {HTMLElement} node Safe text container. */
  const node=document.createElement(tag);node.textContent=text;node.className=className;return node;
}

/** Create a same-origin original-record link.
 * @param {string} text Visible link label.
 * @param {string} href Server-generated record destination.
 * @returns {HTMLAnchorElement} Navigable original reference.
 */
function link(text,href){
  /** @type {HTMLAnchorElement} anchor Literal link, preserving pinned route parameters. */
  const anchor=make("a",text,"download");anchor.href=href;return anchor;
}

/** Call the shared comparison Interface.
 * @param {string} path Fixed endpoint with encoded identities.
 * @param {Object|null} body Optional command; null performs a read.
 * @returns {Promise<Object>} Checked response.
 */
async function request(path,body=null){
  /** @type {Response} response Same-origin request; only saving a comparison needs a write token. */
  const response=await fetch(path,body===null?{}:{method:"POST",headers:{"Content-Type":"application/json","X-Review-Token":comparisonState.token},body:JSON.stringify(body)});
  /** @type {Object} result Response whose failure must be displayed before rendering any observation. */
  const result=await response.json();if(!response.ok)throw new Error(result.message||"无法读取比较记录");return result;
}

/** Serialize page operations and expose errors.
 * @param {Function} action Awaitable loading or comparison command.
 * @returns {Promise<void>} Completion with controls restored.
 */
async function perform(action){
  if(comparisonState.busy)return;comparisonState.busy=true;
  /** @type {HTMLElement} control Editable command controls disabled during one in-flight operation. */
  for(const control of document.querySelectorAll("button,select"))control.disabled=true;
  element("compare-message").className="";
  /** @type {Error} error Actual request or rendering failure shown to the local user. */
  try{await action();}catch(error){element("compare-message").textContent=error.message;element("compare-message").className="error";}
  finally{
    comparisonState.busy=false;
    for(const control of document.querySelectorAll("button,select"))control.disabled=!comparisonState.options;
  }
}

/** Translate a stable node identity using the original labels from both runs.
 * @param {string} key Node, route, status or model identity.
 * @returns {string} Human-readable label, falling back to the exact identifier.
 */
function name(key){
  /** @type {Object|null} saved Current comparison contains original names, not inferred matches by label. */
  const saved=comparisonState.result;key=String(key);
  return captions[key]||captions[key?.replace("goal/","")]||saved?.child.labels[key]||saved?.parent.labels[key]||key;
}

/** Render a short typed substitution.
 * @param {Object} value Original IR expression.
 * @returns {string} Readable variable/application or exact fallback JSON.
 */
function term(value){
  if(value.op==="var")return value.name;
  if(value.op==="nat")return String(value.value);
  if(value.op==="call")return "("+({prefix:"firstn",ir_initial:"initial"}[value.symbol]||value.symbol)+" "+value.args.map(term).join(" ")+")";
  return JSON.stringify(value);
}

/** Present exact before/after values with readable mathematical labels.
 * @param {string} category Model, node, edge, alignment, route or proof category.
 * @param {*} value Original value, including null for an absent record.
 * @returns {string} Literal display text.
 */
function valueText(category,value){
  if(value===null||value===undefined)return "无此记录";
  if(category==="nodes"||category==="goals")return name(value.title)+"\n"+(value.formal||"尚未编码");
  if(category==="edges")return (value.premises.map(name).join(" ∧ ")||"基础定义")+" → "+name(value.conclusion);
  if(category==="alignments")return name(value.from)+" → "+name(value.to)+"\n实例化："+(value.instantiation?
    Object.entries(value.instantiation).map(([key,item])=>key+" := "+term(item)).join("；"):"待建立")+"\n条件："+(value.conditions?.join("；")||"待明确");
  if(category==="proofs")return name(value.status)+"\n目标版本："+(value.goal||"尚未编码")+"\n完整证明回执："+(value.complete||"无");
  if(typeof value==="string")return name(value);
  return JSON.stringify(value,null,2);
}

/** Build a fixed three-column before/after table.
 * @param {Array<Object>} rows Exact keyed changes to display.
 * @param {string} category Determines readable mathematical formatting.
 * @returns {HTMLElement} Accessible table wrapper.
 */
function table(rows,category){
  /** @type {HTMLElement} wrapper, grid, header Table elements retain text values only. */
  const wrapper=make("div","","table-wrap"),grid=make("table","","comparison-table"),header=make("tr");
  /** @type {string} label Stable comparison column caption. */
  for(const label of ["内容","父运行","子运行"])header.append(make("th",label));
  /** @type {HTMLElement} head, body Column headings and exact observation rows. */
  const head=make("thead"),body=make("tbody");head.append(header);grid.append(head,body);
  /** @type {Object} item One unchanged or revised stable identity. */
  for(const item of rows){
    /** @type {HTMLElement} row, title, badge One exact identity and its visible change classification. */
    const row=make("tr"),title=make("td"),badge=make("span",name(item.change),"change-tag "+item.change);
    title.append(badge,make("div",name(item.key)));row.append(title);
    /** @type {string} side Original or revised value, kept in a consistent column. */
    for(const side of ["before","after"]){
      /** @type {HTMLElement} cell Before or after value, with long formal content available on demand. */
      const cell=make("td");cell.append(make("pre",valueText(category,item[side])));row.append(cell);
    }
    body.append(row);
  }
  wrapper.append(grid);return wrapper;
}

/** Show changed rows first and keep unchanged evidence available without hiding its existence.
 * @param {HTMLElement} container Destination section.
 * @param {string} title Section label.
 * @param {Array<Object>} rows Complete category observations.
 * @param {string} category Formatting category.
 * @returns {void}
 */
function group(container,title,rows,category){
  /** @type {Array<Object>} changed, same Structural differences and exact matches. */
  const changed=rows.filter(row=>row.change!=="unchanged"),same=rows.filter(row=>row.change==="unchanged");
  container.append(make("h3",title+" · "+changed.length+" 项变化"));
  if(changed.length)container.append(table(changed,category));
  else container.append(make("p","此项在两个固定版本中相同。","muted"));
  if(same.length){
    /** @type {HTMLDetailsElement} details Unchanged records remain inspectable with exact values. */
    const details=make("details");details.append(make("summary","查看 "+same.length+" 项相同内容"),table(same,category));container.append(details);
  }
}

/** Load exact version choices and comparison history for a child.
 * @param {string} child Saved direct-child identity.
 * @returns {Promise<void>} Picker state installed with adoption baseline as the default parent version.
 */
async function options(child){
  comparisonState.options=await request("/api/comparison-options?child="+encodeURIComponent(child));
  /** @type {Object} data Verified pair and append-only version lists. */
  const data=comparisonState.options;
  /** @type {string} side Explicit run identity owning these route revisions or original records. */
  for(const side of ["parent","child"]){
    /** @type {HTMLSelectElement} picker Exact route revisions owned by this side. */
    const picker=element(side+"-selection");picker.replaceChildren();element(side+"-id").textContent=data[side].id;
    /** @type {number|Object} index, revision Historical route order and its immutable exact choices. */
    for(const [index,revision]of data[side].selections.entries()){
      /** @type {HTMLOptionElement} option Ordered version and the primary selected route. */
      const option=make("option","版本 "+(index+1)+" · "+revision.id.slice(0,12)+" · "+name(revision.choices["goal/fig3_acceptance_soundness"]||"无所选路线"));
      option.value=revision.id;picker.append(option);
    }
    picker.value=data[side].default_selection;
  }
  element("back-run").href="/reasoning?run="+encodeURIComponent(child);
  /** @type {HTMLSelectElement} history Saved immutable comparisons, separately selected from route versions. */
  const history=element("comparison-history");history.replaceChildren(make("option","选择已保存比较"));history.firstChild.value="";
  /** @type {Object} item Saved comparison identity and creation time. */
  for(const item of data.history){
    /** @type {HTMLOptionElement} option Navigable immutable comparison, independent of current route heads. */
    const option=make("option",item.created_at.slice(0,19).replace("T"," ")+" · "+item.id.slice(0,12));
    option.value=item.id;history.append(option);
  }
  element("version-note").textContent="默认父路线为采用提案时的版本。生成后保存两个明确版本，之后切换路线不会改写此比较。";
}

/** Render immutable comparison data and original-record links.
 * @param {Object} saved Verified saved comparison.
 * @returns {void}
 */
function render(saved){
  comparisonState.result=saved;element("comparison-result").hidden=false;
  /** @type {Object} diff, summary Saved category differences and actual proof progress counts. */
  const diff=saved.differences,summary=diff.summary;
  for(const side of ["parent","child"])element(side+"-selection").value=saved[side].selection.id;
  element("comparison-history").value=saved.id;
  element("version-note").textContent="已固定比较 "+saved.id+"。下方结果绑定保存版本；调整选择后需重新生成比较。";
  /** @type {HTMLElement} overview Summary cards distinguish structural work from mathematical closure. */
  const overview=element("comparison-summary");overview.replaceChildren();
  /** @type {string|number} label, value, note Saved summary caption, actual count and its interpretation. */
  for(const [label,value,note]of [
    ["新增推导节点",summary.added_nodes,"模型与目标："+(summary.model_changed||summary.goals_changed?"有变化":"保持相同")],
    ["本轮新完成命题",summary.newly_proved.length,"重新开放："+summary.reopened.length+" 项"],
    ["子运行新增回执",summary.new_receipts,"两侧共用："+summary.shared_receipts+" 份"],
    ["主要目标",diff.obligations.some(item=>item.root==="goal/fig3_acceptance_soundness"&&item.after?.status==="proved")?"已证明":"未证明","以实际完整证明为准"]]){
    /** @type {HTMLElement} card One summarized structural or proof outcome. */
    const card=make("div","","compare-stat");card.append(make("span",label),make("strong",String(value)),make("small",note));overview.append(card);
  }
  /** @type {HTMLElement} binding, columns Original references always contain the selected route identity. */
  const binding=element("comparison-binding"),columns=make("div","","binding-grid");binding.replaceChildren(make("h2","固定版本与原始记录"));
  /** @type {string} side Explicit run identity owning these route revisions or original records. */
  for(const side of ["parent","child"]){
    /** @type {Object|HTMLElement} record, column, links Fixed input version and its original-record navigation. */
    const record=saved[side],column=make("div"),links=make("p","","binding-links");
    column.append(make("h3",side==="parent"?"父运行":"子运行"),make("code",record.run),make("p","路线 "+record.selection.id,"muted"));
    links.append(link("打开固定路线 ↗",record.links.run),link("运行原始记录 ↗",record.links.record),link("冻结上下文 ↗",record.links.freeze),link("Analysis IR ↗",record.links.mapping));
    column.append(links);columns.append(column);
  }
  binding.append(columns,link("完整比较记录 ↗","/api/comparison?id="+encodeURIComponent(saved.id)));
  binding.append(make("p","采用提案 "+saved.adoption.proposal,"muted"),
    link("查看原反馈与提案 ↗","/reasoning?run="+encodeURIComponent(saved.parent.run)+"&selection="+encodeURIComponent(saved.adoption.base_selection)+"&proposal="+encodeURIComponent(saved.adoption.proposal)));
  if(saved.decision)binding.append(make("p","采用时数学决定："+saved.decision.actor+" · "+saved.decision.reason));
  else binding.append(make("p","此提案采用时无需额外数学确认。","muted"));
  /** @type {HTMLElement} model, graph Category destinations are rebuilt only from this saved observation. */
  const model=element("model-content"),graph=element("graph-content");model.replaceChildren();graph.replaceChildren();
  model.append(make("p",summary.model_changed?"形式模型或来源绑定存在变化，见下列具体差异。":"形式模型、范围、分析定义及来源绑定相同。"));
  group(model,"模型与来源",diff.model,"model");group(model,"输入与检查版本",diff.versions,"versions");group(model,"登记目标",diff.goals,"goals");
  /** @type {string} title, key Graph category caption and exact saved comparison field. */
  for(const [title,key]of [["节点","nodes"],["推导连接","edges"],["对齐方向与实例化","alignments"],["所选路线","routes"]])group(graph,title,diff[key],key);
  renderProofs(saved);renderUsage(diff.usage);
}

/** Display actual obligations and receipts, including why a former open leaf left the selected route.
 * @param {Object} saved Version-bound comparison containing real evidence references.
 * @returns {void}
 */
function renderProofs(saved){
  /** @type {HTMLElement} panel Proof changes and selected-route obligations remain distinct. */
  const panel=element("proof-content");panel.replaceChildren();
  group(panel,"命题证明状态与回执",saved.differences.proofs,"proofs");
  /** @type {Object} item One root target with its two selected-route closures. */
  for(const item of saved.differences.obligations){
    /** @type {HTMLElement} card One root's exact old and new unresolved closures. */
    const card=make("div","","obligation-card");card.append(make("h3",name(item.root)));
    card.append(make("p","父运行："+name(item.before?.status||"无此目标")+" → 子运行："+name(item.after?.status||"无此目标")));
    /** @type {string|Array<string>} label, keys Explanation category and actual affected node identities. */
    for(const [label,keys]of [["新增开放义务",item.introduced],["仍待完成",item.retained],["已有完整证明",item.proved],["移出所选路线（不等于已证明）",item.left_route]]){
      if(keys.length)card.append(make("p",label+"："+keys.map(name).join("；")));
    }
    panel.append(card);
  }
  /** @type {HTMLDetailsElement} receipts Receipt-level history is expandable to keep open obligations prominent. */
  const receipts=make("details");receipts.append(make("summary","逐项查看证明回执 · "+saved.differences.receipts.length+" 份"));
  /** @type {Object} item One actual receipt, its owners and recorded inheritance reasons. */
  for(const item of saved.differences.receipts){
    /** @type {HTMLElement} card, links Evidence explanation and exact parent/child receipt destinations. */
    const card=make("div","","receipt"),links=make("p","","binding-links");
    card.append(make("span",name(item.change),"change-tag"),make("strong",name(item.outcome)),make("p",item.attempt,"muted"));
    /** @type {string} side Explicit run identity owning these route revisions or original records. */
  for(const side of ["parent","child"]){
      /** @type {Array<string>} owners Claim and relation owners that actually reference this receipt. */
      const owners=item[side==="parent"?"before_owners":"after_owners"];
      if(owners.length){
        card.append(make("p",(side==="parent"?"父运行":"子运行")+"："+owners.map(owner=>name(owner.slice(owner.indexOf(":")+1))).join("；")));
        links.append(link(side==="parent"?"父运行原始回执 ↗":"子运行原始回执 ↗","/api/derivation-evidence?run="+encodeURIComponent(saved[side].run)+"&attempt="+encodeURIComponent(item.attempt)));
      }
    }
    if(item.inheritance?.reasons.length)card.append(make("p","未直接复用原因："+item.inheritance.reasons.map(reason=>name(reason.code)).join("；")));
    card.append(links);receipts.append(card);
  }
  panel.append(receipts);
}

/** Show separate run budgets and totals, preserving unknown historical costs.
 * @param {Object} usage Before/after counters and numeric differences where both sides are known.
 * @returns {void}
 */
function renderUsage(usage){
  /** @type {HTMLElement} panel Usage comparison owns no proof counter or budget mutation. */
  const panel=element("usage-content");panel.replaceChildren();
  /** @type {Array<Object>} rows Literal budget and measured-use values; missing data stays explicit. */
  const rows=[];
  /** @type {string} key, label Measured field and its user-facing accounting caption. */
  for(const [key,label]of [["budget","本轮证明检查限额"],["proof_attempts","本轮实际证明尝试"],["external_calls","本轮外部模型调用"],
    ["external_cost_usd","本轮外部调用费用（USD）"],["elapsed_ms","本轮耗时（毫秒）"],["status","结果状态"],["end_reason","停止原因"]]){
    /** @type {Object} values Literal before/after measurements, including explicit unknowns. */
    const values={};
    /** @type {string} side Original or revised value, kept in a consistent column. */
    for(const side of ["before","after"]){
      /** @type {*} value Recorded budget, counter or status; null never becomes zero. */
      const value=usage[side][key];values[side]=value===null||value===undefined?"未记录":key==="budget"?String(value.max_proof_attempts):String(name(value));
    }
    rows.push({key:label,...values,change:values.before===values.after?"unchanged":"modified"});
  }
  panel.append(table(rows,"usage"),make("p","各轮预算与实际用量独立显示；复用回执不计作新的证明尝试。未记录的历史费用保持未知。","muted"));
  /** @type {string} side Independent ancestry total being explained. */
  for(const side of ["before","after"]){
    /** @type {Object} data, total Per-run accounting and the corresponding known ancestry subtotal. */
    const data=usage[side],total=data.cumulative;
    panel.append(make("p",(side==="before"?"父运行":"子运行")+"父链累计：已知证明尝试 "+total.known_proof_attempts+" 次；已知外部费用 "+total.known_external_cost_usd+" USD；费用未知运行 "+total.unknown_cost_runs.length+" 轮。"));
    if(data.attempt_count_source==="saved_events")panel.append(make("p","父运行未登记独立预算；实际证明尝试数由已保存事件统计。","muted"));
  }
}

/** Open a saved snapshot without regenerating it under the current comparison code.
 * @param {string} id Comparison content identity.
 * @returns {Promise<void>} Stable saved observation rendered at a refreshable URL.
 */
async function openComparison(id){
  /** @type {Object} saved Original comparison; picker history may evolve independently. */
  const saved=await request("/api/comparison?id="+encodeURIComponent(id));
  await options(saved.child.run);render(saved);history.replaceState(null,"","/compare?id="+encodeURIComponent(id));
  element("compare-message").textContent="已打开保存的比较；两侧路线与证据版本保持固定。";
}

/** @param {SubmitEvent} event Form submission creates only a saved comparison observation. */
element("compare-form").addEventListener("submit",event=>{
  event.preventDefault();perform(async()=>{
    /** @type {Object} pair Verified direct relation owning the explicit picker values. */
    const pair=comparisonState.options;
    element("compare-message").textContent="正在核对两侧原始记录并保存比较…";
    /** @type {Object} saved Newly persisted comparison observation, containing no new proof attempts. */
    const saved=await request("/api/comparisons",{parent:pair.parent.id,child:pair.child.id,
      parent_selection:element("parent-selection").value,child_selection:element("child-selection").value});
    await options(saved.child.run);render(saved);history.replaceState(null,"","/compare?id="+encodeURIComponent(saved.id));
    element("compare-message").textContent="比较已保存。原运行、路线与证明回执保持原样。";
  });
});
element("comparison-history").addEventListener("change",()=>{if(element("comparison-history").value)perform(()=>openComparison(element("comparison-history").value));});
perform(async()=>{
  /** @type {URLSearchParams} query Explicit saved comparison or direct child chosen from the run page. */
  const query=new URLSearchParams(location.search),catalog=await request("/api/catalog");
  comparisonState.token=catalog.token;element("test-banner").hidden=!catalog.testing;
  if(query.get("id"))await openComparison(query.get("id"));
  else if(query.get("child"))await options(query.get("child"));
  else throw new Error("请从关联运行的“比较父子运行”入口进入。");
});
