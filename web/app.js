/** Local source-review client. All mathematical state is validated again on the server. */
"use strict";

/**
 * @type {Object}
 * @property {string} token Same-origin write token obtained from the local catalog.
 * @property {Object|null} project Current workspace response, including its exact revision.
 * @property {string} active Item key or reserved panel name.
 * @property {Array} sources Editable copies of the active item's references.
 * @property {Object|null} page Current physical page with Unicode source text.
 * @property {Object|null} preview Exact pending patch or freeze preview.
 * @property {boolean} dirty Whether unsaved form edits need explicit discard.
 * @property {boolean} busy Whether an operation currently owns the UI.
 */
const model = {token: "", project: null, active: "", sources: [], page: null, preview: null, dirty: false, busy: false};
/** @type {Object<string,string>} labels Human-facing names for normalized fields and audit changes. */
const labels = {expression:"数学表达式",priority:"优先级规则",equal_deadline_tie_break:"同截止期排序",
  release_pattern:"释放模式",minimum_separation_symbol:"最小间隔符号",captures:"原文关系符",
  execution_bound:"执行量与截止期",deadline_bound:"截止期与周期",relation:"关系符",
  interference:"干扰函数",initial:"迭代初值",accept:"接受条件",update:"迭代更新",reject:"拒绝条件",
  taskset:"任务集判定",direction:"保证方向",summary:"陈述与解释",normalized:"规范化表达",
  material_role:"材料角色",decision:"核对状态",sources:"来源引用",statement:"范围选择",
  normalization_origin:"解释来源",selected:"所选目标",primary:"主要目标"};
/** @type {Object<string,string>} roles Allowed source roles shown to reviewers. */
const roles = {model_definition:"模型定义",analysis_definition:"分析定义",guarantee_statement:"保证声明",
  background:"背景介绍",scope_limit:"范围说明",author_proof:"作者证明"};
/** @type {Object<string,string>} decisions Display names for explicit review decisions. */
const decisions = {pending:"待核对",confirmed:"已核对",excluded:"不纳入"};
/** @type {Object<string,string>} origins Interpretation provenance labels. */
const origins = {captured_operators:"关系符来自原文",rule_interpretation:"本地规则解释 · 需核对",
  reviewed_formula_template:"公式解释模板 · 请对照页图",user_revision:"人工修订 · 原始抽取保留"};

/**
 * Resolve a fixed UI element.
 * @param {string} id Element identifier from index.html.
 * @returns {HTMLElement} Matching element.
 */
function $(id) { return document.getElementById(id); }

/**
 * Create a node without interpreting source text as HTML.
 * @param {string} tag HTML tag name.
 * @param {string} text Literal display text.
 * @param {string} className Optional CSS class.
 * @returns {HTMLElement} Detached element.
 */
function node(tag, text = "", className = "") {
  const element = document.createElement(tag); // element receives untrusted paper content only through textContent.
  element.textContent = text;
  element.className = className;
  return element;
}

/**
 * Display a persistent operation result.
 * @param {string} text User-facing message.
 * @param {boolean} error Whether to use the error appearance.
 */
function notify(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "error" : "";
  $("message").hidden = false;
}

/**
 * Call the local JSON interface.
 * @param {string} path Fixed route with encoded identifiers where needed.
 * @param {Object|null} body Optional JSON request body.
 * @returns {Promise<Object>} Decoded response.
 * @throws {Error} For a rejected operation, including stale revisions.
 */
async function api(path, body = null) {
  const options = body === null ? {} : {method:"POST", headers:{"Content-Type":"application/json","X-Review-Token":model.token}, body:JSON.stringify(body)};
  const response = await fetch(path, options); // response is checked before any returned state is displayed.
  const value = await response.json();
  if (!response.ok) throw new Error(value.message || "操作失败");
  return value;
}

/**
 * Serialize visible actions and make failures accessible.
 * @param {Function} operation Asynchronous action to execute.
 * @returns {Promise<void>} Completion after resetting the busy state.
 */
async function run(operation) {
  if (model.busy) return;
  model.busy = true;
  document.body.classList.add("busy");
  try { await operation(); } catch (error) { notify(error.message, true); }
  finally { model.busy = false; document.body.classList.remove("busy"); }
}

/**
 * Confirm discarding unsaved edits when navigating away.
 * @returns {boolean} Whether navigation can proceed.
 */
function discard() {
  if (model.dirty && !window.confirm("当前修改尚未保存。是否放弃这些修改？")) return false;
  model.dirty = false;
  return true;
}

/**
 * Populate a select with literal labels.
 * @param {HTMLSelectElement} select Target select control.
 * @param {Array<Array<string>>} entries Value/label pairs.
 * @param {string} value Desired selected value.
 */
function options(select, entries, value = "") {
  select.replaceChildren(...entries.map(([key, title]) => {
    const option = node("option", title); // option value is an opaque server identity or enumerated role.
    option.value = key;
    return option;
  }));
  select.value = value;
}

/**
 * Refresh project and saved-draft pickers without changing the selected revision.
 * @returns {Promise<Object>} Current catalog.
 */
async function refreshCatalog() {
  const catalog = await api("/api/catalog"); // token stays in page memory, never in URLs or localStorage.
  model.token = catalog.token;
  $("test-banner").hidden = !catalog.testing;
  options($("projects"), [["","新建核对项目"], ...catalog.projects.map(p => [p.id,p.name])], model.project?.project || "");
  options($("drafts"), catalog.drafts.map((draft,index) => [draft.id,"草稿 " + (index+1) + " · " + draft.id.slice(0,10)]),
    catalog.drafts[0]?.id || "");
  $("create").disabled = catalog.drafts.length === 0;
  return catalog;
}

/**
 * Open a workspace revision and show its first relevant source.
 * @param {string} id Workspace identity.
 * @param {string} revision Optional historical revision.
 * @returns {Promise<void>} Completion after source rendering.
 */
async function openProject(id, revision = "") {
  model.project = await api("/api/project?id=" + encodeURIComponent(id) + (revision ? "&revision=" + encodeURIComponent(revision) : ""));
  model.dirty = false;
  if (!model.project.state.items.some(item => item.key === model.active) && !model.active.startsWith("@"))
    model.active = model.project.state.items[0]?.key || "@goals";
  render();
  const active = model.project.state.items.find(item => item.key === model.active);
  await loadPage(active?.sources[0]?.anchors[0]?.page || 1);
  if (active) await focusReference(active.sources[0].anchors[0]);
}

/**
 * Render workspace navigation and the current editor.
 */
function render() {
  const project = model.project; // project retains both viewed revision and current head.
  if (!project) return;
  $("empty").hidden = true;
  $("workspace").hidden = false;
  $("freeze").disabled = project.revision !== project.head;
  $("project-title").textContent = project.name;
  $("project-note").textContent = "case_11 · 独立构建证明 · 原文与项目范围分别核对";
  $("projects").value = project.project;
  $("revision-label").textContent = "修订 " + project.history.find(row => row.id === project.revision).generation + " · " + project.revision.slice(0,10);
  $("gate-count").textContent = project.blockers.length ? project.blockers.length + " 项冻结检查待处理" : "核对条件已满足，可预览冻结";
  $("historical").hidden = project.revision === project.head;
  options($("history"),project.history.map(row => [row.id,"修订 " + row.generation + " · " + row.id.slice(0,8)]),project.revision);
  $("progress").textContent = project.state.items.filter(item => item.decision === "confirmed").length + " / " + project.state.items.length;
  $("items").replaceChildren();
  for (const [category,title] of [["model","模型条件与范围"],["analysis","分析方法"],["goal","候选目标"]]) {
    $("items").append(node("div",title,"group-label"));
    for (const item of project.state.items.filter(value => value.category === category)) {
      const button = node("button","","item-nav " + item.decision + (model.active === item.key ? " active" : ""));
      button.title = item.title + " · " + decisions[item.decision];
      button.append(node("span","","dot"),node("span",item.title));
      button.addEventListener("click",() => run(async () => {
        if (!discard()) return;
        model.active = item.key;
        renderEditor();
        for (const sibling of $("items").querySelectorAll("button")) sibling.classList.toggle("active", sibling === button);
        await focusReference(item.sources[0].anchors[0]);
      }));
      $("items").append(button);
    }
  }
  renderEditor();
}

/**
 * Add an accessible labeled form control.
 * @param {HTMLElement} parent Container receiving the field.
 * @param {string} title Visible label.
 * @param {HTMLElement} control Input, textarea or select.
 * @returns {HTMLElement} Inserted control.
 */
function field(parent, title, control) {
  const wrapper = node("label",title); // Wrapping controls provides a native accessible name.
  wrapper.append(control);
  parent.append(wrapper);
  control.addEventListener("input",() => {model.dirty = true;});
  return control;
}

/**
 * Render editable string leaves of an existing normalized expression.
 * @param {HTMLElement} parent Field container.
 * @param {Object} value Normalized object being edited.
 * @param {Array<string>} path Current key path.
 */
function normalizedFields(parent, value, path = []) {
  for (const [key,child] of Object.entries(value)) {
    const next = [...path,key]; // next is recorded on the control to rebuild the same tree shape.
    if (child && typeof child === "object") normalizedFields(parent,child,next);
    else {
      const input = node("textarea","","formula");
      input.value = child;
      input.rows = String(child).length > 60 ? 3 : 2;
      input.dataset.path = JSON.stringify(next);
      field(parent,labels[key] || key,input);
    }
  }
}

/**
 * Render the active candidate or workspace panel.
 */
function renderEditor() {
  const editor = $("editor"); // Editor content is replaced only after navigation or a committed revision.
  editor.replaceChildren();
  $("cite-selection").disabled = model.active.startsWith("@") || model.project.revision !== model.project.head;
  if (model.active === "@goals") renderGoals(editor);
  else if (model.active === "@scope") renderScope(editor);
  else if (model.active === "@audit") renderAudit(editor);
  else {
    const item = model.project.state.items.find(value => value.key === model.active);
    model.sources = structuredClone(item.sources);
    const kicker = node("div","","section-kicker");
    kicker.append(node("span",item.category === "goal" ? "候选保证 · 尚未证明" : "来源核对","eyebrow"),
      node("span",decisions[item.decision],"badge " + item.decision));
    editor.append(kicker,node("h2",item.title),node("p",origins[item.normalization_origin] || item.normalization_origin,"muted"));
    const summary = node("textarea"); summary.id = "item-summary"; summary.rows = 4; summary.value = item.summary;
    field(editor,"陈述与解释",summary);
    const normalized = node("div"); normalized.id = "normalized-fields";
    normalizedFields(normalized,item.normalized);
    editor.append(normalized);
    const role = node("select"); role.id = "item-role"; options(role,Object.entries(roles),item.material_role);
    field(editor,"材料角色",role);
    const notes = node("div","","review-notes");
    notes.append(node("strong","确认前请核对"));
    const list = node("ul");
    for (const issue of item.review_issues) list.append(node("li",issue));
    if (item.requires.length) list.append(node("li","依赖：" + item.requires.map(key => titleFor(key)).join("、")));
    notes.append(list); editor.append(notes);
    editor.append(node("h3","原文引用"));
    const refs = node("div"); refs.id = "references"; editor.append(refs);
    renderReferences();
    const decision = node("select"); decision.id = "item-decision"; options(decision,Object.entries(decisions),item.decision);
    field(editor,"本次核对结论",decision);
    editor.append(node("p","确认表示已核对本条来源、数学解释和上述问题；不表示已完成证明。","muted"));
    const button = node("button","预览本条修订","primary");
    button.addEventListener("click",() => run(previewItem));
    editor.append(button);
  }
  if (model.project.revision !== model.project.head)
    for (const control of editor.querySelectorAll("input,textarea,select,button:not(.link-button)")) control.disabled = true;
}

/**
 * Render current source quotations, preserving exact PDF text.
 */
function renderReferences() {
  const refs = $("references"); // Source removals edit only the pending overlay, never the original extraction.
  refs.replaceChildren();
  model.sources.forEach((source,index) => {
    const group = node("div");
    source.anchors.forEach(anchor => {
      const header = node("div","","quote-head");
      const locate = node("button","第 " + anchor.page + " 页 · 定位原文 ↗","link-button");
      locate.addEventListener("click",() => run(() => focusReference(anchor)));
      header.append(locate);
      group.append(header,node("div",anchor.quote,"quote"));
    });
    const remove = node("button","移除此组引用","remove-source");
    remove.disabled = model.project.revision !== model.project.head;
    remove.addEventListener("click",() => {model.sources.splice(index,1);model.dirty = true;renderReferences();});
    group.append(remove); refs.append(group);
  });
}

/**
 * Resolve an item key for preview and dependency labels.
 * @param {string} key Stable semantic item key.
 * @returns {string} Readable title or original key.
 */
function titleFor(key) {return model.project.state.items.find(item => item.key === key)?.title || key;}

/**
 * Collect the active item editor without accepting identity or proof-status edits.
 * @returns {Promise<void>} Display of the exact-change preview.
 */
async function previewItem() {
  const item = model.project.state.items.find(value => value.key === model.active);
  const normalized = structuredClone(item.normalized); // Rebuild only existing string leaves.
  for (const input of $("normalized-fields").querySelectorAll("textarea")) {
    const path = JSON.parse(input.dataset.path);
    let parent = normalized;
    for (const key of path.slice(0,-1)) parent = parent[key];
    parent[path.at(-1)] = input.value;
  }
  await previewPatch({items:{[item.key]:{summary:$("item-summary").value,normalized,material_role:$("item-role").value,
    sources:model.sources,decision:$("item-decision").value}}});
}

/**
 * Render selection of one or more goals and a primary goal.
 * @param {HTMLElement} editor Panel container.
 */
function renderGoals(editor) {
  editor.append(node("p","PROOF TARGETS","eyebrow"),node("h2","选择需要证明的目标"),
    node("p","所有所选目标都会进入冻结快照，分别保持未证明状态。","muted"));
  for (const item of model.project.state.items.filter(value => value.category === "goal")) {
    const card = node("div","","goal-card");
    const checkbox = node("input"); checkbox.type = "checkbox"; checkbox.value = item.key; checkbox.className = "goal-check";
    checkbox.checked = model.project.state.selected.includes(item.key);
    const label = node("label"); label.append(checkbox,node("span",item.title));
    const primary = node("input"); primary.type = "radio"; primary.name = "primary"; primary.value = item.key;
    primary.checked = model.project.state.primary === item.key;
    const primaryLabel = node("label","","primary-choice"); primaryLabel.append(primary,node("span","登记为主要目标"));
    card.append(label,node("p",item.summary),node("span",decisions[item.decision],"badge " + item.decision),primaryLabel);
    checkbox.addEventListener("change",() => {model.dirty = true;if (!checkbox.checked) primary.checked = false;});
    primary.addEventListener("change",() => {model.dirty = true;checkbox.checked = true;});
    editor.append(card);
  }
  const button = node("button","预览目标选择","primary");
  button.addEventListener("click",() => run(async () => {
    const selected = [...editor.querySelectorAll(".goal-check:checked")].map(input => input.value);
    const primary = editor.querySelector('input[name="primary"]:checked')?.value || selected[0] || null;
    await previewPatch({selected,primary});
  }));
  editor.append(button);
}

/**
 * Render editable, separately sourced formalization choices.
 * @param {HTMLElement} editor Panel container.
 */
function renderScope(editor) {
  editor.append(node("p","FORMALIZATION SCOPE","eyebrow"),node("h2","项目的形式化范围"),
    node("p","整数时间等原有选择已由 D12 / D13 确认。修改将产生范围变体，并要求重新核对目标。","muted"));
  for (const choice of model.project.state.project_choices.choices) {
    const card = node("div","","scope-card");
    const input = node("textarea"); input.rows = 3; input.value = choice.statement; input.dataset.choice = choice.id;
    field(card,choice.decisions.join(" / ") + " · " + decisions[choice.decision],input);
    card.append(node("p","依据：已保存的数学合同；本次编辑与原决定分别留存。"));
    editor.append(card);
  }
  const button = node("button","预览并确认范围修订","primary");
  button.addEventListener("click",() => run(async () => {
    const choices = {};
    for (const input of editor.querySelectorAll("[data-choice]"))
      choices[input.dataset.choice] = {statement:input.value,decision:"confirmed"};
    await previewPatch({choices});
  }));
  editor.append(button);
}

/**
 * Render review attribution and historical frozen contexts.
 * @param {HTMLElement} editor Panel container.
 */
function renderAudit(editor) {
  editor.append(node("p","REVISION HISTORY","eyebrow"),node("h2","变更与冻结记录"));
  const audit = model.project.audit; // Attribution identifies the local reviewer, without claiming account authentication.
  editor.append(node("p","本修订核对人：" + audit.actor),node("p",audit.reason,"muted"));
  for (const change of audit.changes) editor.append(diffNode(change));
  for (const freeze of model.project.freezes) {
    const block = node("div","","audit-event");
    block.append(node("p","冻结上下文 · " + freeze.id.slice(0,12)),node("p","绑定修订 " + freeze.revision.slice(0,12),"muted"));
    const download = node("a","下载完整上下文","download");
    download.href = "/api/frozen?id=" + encodeURIComponent(freeze.id) + "&download=1";
    block.append(download);
    /** @type {HTMLElement} receipts Retained mapping history for this exact freeze. */
    const receipts = node("div");
    /** @type {HTMLButtonElement} mapping Runs the compiler for the selected immutable context. */
    const mapping = node("button","生成 Analysis IR / 检查 Rocq 目标","secondary");
    mapping.addEventListener("click",() => run(async () => {
      notify("正在生成声明并运行 Rocq 检查，请稍候。");
      /** @type {Object} result Persisted translation receipt; never a theorem proof receipt. */
      const result = await api("/api/map",{freeze:freeze.id});
      notify((mappingStatuses[result.status] || result.status) + "。主目标仍未证明。");
      await renderMappings(receipts,freeze.id);
    }));
    block.append(mapping,receipts); editor.append(block);
    renderMappings(receipts,freeze.id).catch(error => notify(error.message,true));
  }
  if (!model.project.freezes.length) editor.append(node("p","尚未冻结上下文。","muted"));
}


/** @type {Object<string,string>} mappingStatuses Mapping and checker outcomes, separate from proof status. */
const mappingStatuses = {mapped:"声明及对应关系检查通过",partial:"部分目标已映射，其余保留缺口",
  blocked:"范围或目标尚不支持",failed:"检查失败"};

/**
 * Restore checked mapping history after navigation or a page reload.
 * @param {HTMLElement} host Container belonging to one frozen context.
 * @param {string} freeze Immutable context identity.
 * @returns {Promise<void>} Rendered receipts and explicit differences.
 */
async function renderMappings(host,freeze) {
  /** @type {Array<Object>} receipts Verified summaries returned by the local evidence store. */
  const receipts = await api("/api/mappings?freeze=" + encodeURIComponent(freeze));
  host.replaceChildren();
  for (const receipt of receipts) {
    /** @type {HTMLElement} card Outcome and gaps for one historical compiler run. */
    const card = node("div","","audit-event");
    card.append(node("p",(mappingStatuses[receipt.status] || receipt.status) + " · 主目标未证明"));
    /** @type {HTMLAnchorElement} output Opens the complete IR, provenance and checker receipt. */
    const output = node("a","查看映射、来源与检查回执 · " + receipt.id.slice(0,12),"download");
    output.href = "/api/mapping?id=" + encodeURIComponent(receipt.id);
    output.target = "_blank"; output.rel = "noopener";
    card.append(output);
    if (["mapped","partial"].includes(receipt.status)) {
      /** @type {HTMLAnchorElement} derive Opens the W04 workspace for this exact checked mapping. */
      const derive = node("a","进入双向推导 →","download");
      derive.href = "/reasoning?mapping=" + encodeURIComponent(receipt.id);
      card.append(derive);
    }
    for (const issue of receipt.issues)
      card.append(node("p",[issue.item,issue.field,issue.code,issue.message].filter(Boolean).join(" · "),"muted"));
    host.append(card);
  }
}

/**
 * Translate review enums without changing stored mathematical content.
 * @param {*} value Original value included in the preview.
 * @param {string} fieldName Kind of edited field.
 * @returns {string} Human-readable representation.
 */
function displayChange(value, fieldName) {
  if (fieldName === "decision") return decisions[value] || value;
  if (fieldName === "material_role") return roles[value] || value;
  if (fieldName === "normalization_origin") return origins[value] || value;
  if (fieldName === "primary") return value ? titleFor(value) : "未选择";
  if (fieldName === "selected") return value.map(titleFor).join("、") || "未选择";
  return typeof value === "string" ? value : JSON.stringify(value,null,2);
}

/**
 * Build a before/after comparison using literal values.
 * @param {Object} change Server-provided field difference.
 * @returns {HTMLElement} Comparison block.
 */
function diffNode(change) {
  const block = node("div","","diff");
  block.append(node("div",titleFor(change.object) + " · " + (labels[change.field] || change.field),"diff-title"));
  const values = node("div","","diff-values");
  for (const [title,value] of [["之前",change.before],["之后",change.after]]) {
    const column = node("div");
    column.append(node("span",title,"muted"),node("pre",displayChange(value,change.field)));
    values.append(column);
  }
  block.append(values);
  return block;
}

/**
 * Show a prepared edit; the returned digest binds confirmation to these exact values.
 * @param {Object} patch Whitelisted field edits.
 * @returns {Promise<void>} Preview display.
 */
async function previewPatch(patch) {
  const preview = await api("/api/preview",{project:model.project.project,expected:model.project.revision,patch});
  model.preview = {kind:"edit",patch,expected:model.project.revision,project:model.project.project,...preview};
  $("preview-title").textContent = "核对变更与影响";
  $("preview-content").replaceChildren(...preview.changes.map(diffNode));
  if (preview.affected_goals.length) $("preview-content").append(node("p","需要重新核对：" + preview.affected_goals.map(titleFor).join("、"),"notice"));
  $("preview-content").append(node("p",preview.prior_evidence,"muted"));
  showConfirmation(false);
}

/**
 * Reset the confirmation form before displaying a preview.
 * @param {boolean} freezing Whether this preview creates a frozen context.
 */
function showConfirmation(freezing) {
  $("confirm-check").checked = false;
  $("confirm-action").disabled = true;
  $("reason").value = "";
  $("reason-label").hidden = freezing;
  $("confirm-action").textContent = freezing ? "确认并冻结上下文" : "确认并保存修订";
  $("confirm-label").textContent = freezing ? "我确认上述目标、来源与范围；冻结不代表目标已证明。" : "我已核对上述变更、来源与影响。";
  $("preview-dialog").showModal();
}

/**
 * Prepare a frozen semantic input without launching any proof or model call.
 * @returns {Promise<void>} Freeze summary and blocking reasons.
 */
async function previewFreeze() {
  if (model.dirty) throw new Error("请先保存或放弃当前字段修改，再预览冻结。");
  const preview = await api("/api/freeze-preview",{project:model.project.project,expected:model.project.revision});
  model.preview = {kind:"freeze",expected:model.project.revision,project:model.project.project,...preview};
  $("preview-title").textContent = preview.blockers.length ? "冻结前还需处理" : "确认冻结上下文";
  const content = $("preview-content"); content.replaceChildren();
  for (const blocker of preview.blockers) content.append(node("div",titleFor(blocker.key) + "：" + blocker.message,"blocker"));
  const summary = node("div","","freeze-summary");
  summary.append(node("h3","所选目标"));
  for (const goal of preview.context.goals)
    summary.append(node("p",(goal.key === preview.context.primary ? "主要目标 · " : "") + goal.title + "：" + goal.summary));
  summary.append(node("h3","固定的形式化范围"));
  for (const choice of preview.context.scope.choices) summary.append(node("p",choice.statement));
  summary.append(node("p",preview.context.scope_status === "reviewed_variant" ? "范围：人工核对的修订变体。" : "范围：引用已登记数学合同。"));
  summary.append(node("p","将固定 " + preview.context.model.length + " 项模型条件、" + preview.context.analysis.length + " 项分析方法。目标保持未证明；形式编码映射将在后续阶段处理。","muted"));
  content.append(summary);
  showConfirmation(true);
}

/**
 * Persist the exact confirmed edit or freeze.
 * @returns {Promise<void>} Updated workspace and catalog.
 */
async function confirmPreview() {
  const pending = model.preview; // Capture the immutable preview even if a later refresh changes page state.
  if (!$("confirm-check").checked) return;
  const actor = $("actor").value;
  if (pending.kind === "edit") {
    if (!$("reason").value.trim()) throw new Error("请填写核对或修订说明。");
    model.project = await api("/api/commit",{project:pending.project,expected:pending.expected,patch:pending.patch,
      token:pending.token,actor,reason:$("reason").value});
    notify("新修订已保存；原始抽取与历史修订均已保留。");
  } else {
    const result = await api("/api/freeze",{project:pending.project,expected:pending.expected,token:pending.token,actor});
    model.project = await api("/api/project?id=" + encodeURIComponent(pending.project));
    model.active = "@audit";
    notify("上下文已冻结：" + result.id.slice(0,12) + "。所选目标仍未证明。");
  }
  model.dirty = false;
  $("preview-dialog").close();
  await refreshCatalog();
  render();
}

/**
 * Fetch a physical page and show the corresponding original image.
 * @param {number} number One-based physical page.
 * @returns {Promise<void>} Loaded source page.
 */
async function loadPage(number) {
  const extraction = model.project.state.extraction_id;
  model.page = await api("/api/page?extraction=" + encodeURIComponent(extraction) + "&page=" + number);
  options($("page-number"),Array.from({length:model.page.count},(_,index) => [String(index+1),String(index+1)]),String(number));
  $("page-text").textContent = model.page.text;
  $("page-image").src = "/api/image?extraction=" + encodeURIComponent(extraction) + "&page=" + number;
  $("page-image").alt = "原论文第 " + number + " 页";
  $("highlights").replaceChildren();
  $("prev-page").disabled = number <= 1;
  $("next-page").disabled = number >= model.page.count;
}

/**
 * Resolve an exact citation and highlight its source words.
 * @param {Object} anchor Saved source reference.
 * @returns {Promise<void>} Highlighted original page.
 */
async function focusReference(anchor) {
  if (!model.page || model.page.number !== anchor.page) await loadPage(anchor.page);
  const query = new URLSearchParams({extraction:anchor.extraction_id,page:anchor.page,start:anchor.start,end:anchor.end});
  const located = await api("/api/reference?" + query);
  $("highlights").replaceChildren();
  for (const box of located.boxes) {
    const highlight = node("span","","highlight");
    highlight.style.left = 100 * box.x0 / located.page_width + "%";
    highlight.style.top = 100 * box.y0 / located.page_height + "%";
    highlight.style.width = 100 * (box.x1-box.x0) / located.page_width + "%";
    highlight.style.height = 100 * (box.y1-box.y0) / located.page_height + "%";
    $("highlights").append(highlight);
  }
  $("source-hint").textContent = "第 " + anchor.page + " 页 · 已高亮当前引用；原文保持不变。";
  const box = located.boxes[0];
  if (box) $("image-view").scrollTop = Math.max(0,box.y0 / located.page_height * $("page-canvas").clientHeight - 100);
}

/**
 * Capture browser selection using Unicode codepoint offsets, not UTF-16 indices.
 * @returns {Promise<void>} Added verified source range in the pending item editor.
 */
async function citeSelection() {
  const selection = window.getSelection();
  if (!selection.rangeCount || selection.isCollapsed) throw new Error("请在右侧文字视图中选中原文。");
  const range = selection.getRangeAt(0);
  const container = $("page-text");
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer))
    throw new Error("请选择同一页的原始提取文字。");
  const prefix = range.cloneRange(); // Prefix lengths are converted from browser strings to Python-compatible codepoints.
  prefix.selectNodeContents(container);
  prefix.setEnd(range.startContainer,range.startOffset);
  const start = [...prefix.toString()].length;
  const end = start + [...range.toString()].length;
  const query = new URLSearchParams({extraction:model.project.state.extraction_id,page:model.page.number,start,end});
  const located = await api("/api/reference?" + query);
  model.sources.push({selector:"manual_range",kind:"prose",anchors:[located.anchor]});
  model.dirty = true;
  renderReferences();
  notify("已补充来源到当前编辑内容；请预览并保存修订。");
}

/**
 * Switch the original-source presentation mode.
 * @param {boolean} text Whether to show selectable extracted text.
 */
function sourceMode(text) {
  $("text-view").hidden = !text;
  $("image-view").hidden = text;
  $("text-tab").classList.toggle("active",text);
  $("image-tab").classList.toggle("active",!text);
}

/**
 * Create a pending review project from an uploaded PDF.
 * @returns {Promise<void>} Display of the imported project.
 */
async function upload() {
  const file = $("pdf-file").files[0]; // Browser supplies bytes only; server never accepts a user-provided local path.
  if (!file) throw new Error("请先选择 PDF 文件。");
  if (file.size > 20 * 1024 * 1024) throw new Error("PDF 超过 20 MiB 导入限制。");
  const response = await fetch("/api/import",{method:"POST",headers:{"Content-Type":"application/pdf",
    "X-Review-Token":model.token,"X-Filename":encodeURIComponent(file.name)},body:file});
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "导入失败");
  $("import-dialog").close();
  await refreshCatalog();
  model.active = "";
  await openProject(result.project);
  notify("PDF 已导入，来源与语义草稿等待核对。");
}

/** Register controls after deferred script loading; callbacks only route user gestures to documented actions. */
$("begin").addEventListener("click",() => $("import-dialog").showModal());
$("import-open").addEventListener("click",() => {if (discard()) $("import-dialog").showModal();});
$("upload").addEventListener("click",() => run(upload));
$("create").addEventListener("click",() => run(async () => {
  const result = await api("/api/projects",{semantic_id:$("drafts").value,name:$("new-name").value});
  $("import-dialog").close(); await refreshCatalog(); model.active = ""; await openProject(result.project);
}));
$("projects").addEventListener("change",() => run(async () => {
  if (!discard()) {$("projects").value = model.project?.project || "";return;}
  if ($("projects").value) {model.active = "";await openProject($("projects").value);}
  else $("import-dialog").showModal();
}));
$("history").addEventListener("change",() => run(async () => {
  if (discard()) await openProject(model.project.project,$("history").value);
  else $("history").value = model.project.revision;
}));
$("latest").addEventListener("click",() => run(() => openProject(model.project.project)));
for (const [id,panel] of [["goals-tab","@goals"],["scope-tab","@scope"],["audit-tab","@audit"]])
  $(id).addEventListener("click",() => {if (discard()) {model.active = panel;render();}});
$("freeze").addEventListener("click",() => run(previewFreeze));
$("confirm-check").addEventListener("change",() => {$("confirm-action").disabled = !$("confirm-check").checked ||
  (model.preview?.kind === "freeze" && model.preview.blockers.length > 0);});
$("confirm-action").addEventListener("click",() => run(confirmPreview));
$("image-tab").addEventListener("click",() => sourceMode(false));
$("text-tab").addEventListener("click",() => sourceMode(true));
$("page-number").addEventListener("change",() => run(() => loadPage(Number($("page-number").value))));
$("prev-page").addEventListener("click",() => run(() => loadPage(model.page.number-1)));
$("next-page").addEventListener("click",() => run(() => loadPage(model.page.number+1)));
$("cite-selection").addEventListener("click",() => run(citeSelection));
window.addEventListener("beforeunload",event => {if (model.dirty) {event.preventDefault();event.returnValue = "";}});
run(async () => {const catalog = await refreshCatalog();if (catalog.projects.length) await openProject(catalog.projects[0].id);});
