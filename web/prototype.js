/**
 * Clickable research-workbench prototype; all mutable data stays in memory.
 * No request is made to the application's API, an LLM, or a proof checker.
 * Refreshing the page restores the demonstration. Real functionality is deferred.
 */
"use strict";

/** @type {Record<string, string>} Consistent, authored 24px line icon paths. */
const ICONS = {
  home: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  paper: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  graph: '<rect x="2" y="3" width="6" height="5" rx="1"/><rect x="16" y="3" width="6" height="5" rx="1"/><rect x="9" y="16" width="6" height="5" rx="1"/><path d="M5 8v4h14V8M12 12v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  back: '<path d="M19 12H5m5-5-5 5 5 5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
  edit: '<path d="m15 4 5 5M4 16l-1 5 5-1L21 7a2 2 0 0 0 0-3l-1-1a2 2 0 0 0-3 0z"/>',
  search: '<circle cx="10" cy="10" r="6.5"/><path d="m15 15 5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  reset: '<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  play: '<path d="m8 4 12 8-12 8z"/>',
  pause: '<path d="M8 4v16M16 4v16"/>',
  minus: '<path d="M5 12h14"/>',
  fit: '<path d="M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 3v.1"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>'
};

/** @type {HTMLElement} Root replaced on navigation and meaningful state changes. */
const app = document.getElementById("app");
/** @type {HTMLDialogElement} Native dialog provides focus trapping and Escape support. */
const dialog = document.getElementById("dialog");
/** @type {number|undefined} Timer for the current transient notification. */
let toastTimer;
/** @type {number|undefined} Timer for a clearly labeled simulated run. */
let runTimer;
/** @type {HTMLElement|null} Element that should regain focus when a dialog closes. */
let dialogTrigger = null;

/**
 * Create the case_11 scenario without implying that its main theorem is proved.
 * @returns {Object} Independent, editable in-memory project state.
 */
function makeSample() {
  return {
    id: "case11", name: "单处理器任务的按期完成保证", kind: "sample", fileName: "Deadline Monotonic Scheduling.pdf", pdf: "prototype-assets/case11.pdf",
    fields: [
      { id: "processor", label: "处理器", value: "一个处理器，任务可以被抢占", category: "model", source: "论文第 2 页 · 模型条件", page: 2, confirmed: false },
      { id: "arrival", label: "任务到达", value: "相邻两次释放，至少间隔 T", category: "model", source: "论文第 4–5 页 · 零星任务", page: 4, confirmed: false },
      { id: "limits", label: "时间约束", value: "0 < C ≤ D ≤ T", category: "model", source: "论文第 2 页 · 模型条件", page: 2, confirmed: false },
      { id: "schedule", label: "调度顺序", value: "截止期越短，优先级越高", category: "model", source: "论文第 2 页 · 优先级分配", page: 2, confirmed: false },
      { id: "independent", label: "任务关系", value: "任务相互独立，无阻塞、无自挂起", category: "model", source: "首版模型约定", page: null, confirmed: false },
      { id: "domain", label: "时间范围", value: "先使用整数时间", category: "model", source: "首版范围选择", page: null, confirmed: false, scope: true },
      { id: "iteration", label: "迭代测试", value: "逐次计算所需时间；若在截止期内满足条件，则接受该任务。", category: "method", source: "论文第 4 页 · Fig. 3", page: 4, confirmed: false }
    ],
    goals: [
      { id: "sufficient", title: "测试通过的任务，都能按期完成", description: "覆盖约定模型下的所有合法任务释放。", selected: true },
      { id: "necessary", title: "不能通过测试的任务，是否一定超期", description: "另一个目标，需要单独证明必要性。", selected: false },
      { id: "optimal", title: "这个优先级顺序，是否是最优选择", description: "需要比较不同优先级分配方式。", selected: false }
    ], run: "idle", decision: false, feedback: [], activity: []
  };
}

/** @type {Object} View state and data for this throwaway, session-only prototype. */
const state = { projects: [makeSample()], activeId: "case11", page: "home", reviewTab: "model", selectedNode: "bridge", graphView: "canvas", scale: 1, filter: "all", query: "", sourceField: "iteration", sourceCollapsed: false };

/**
 * Escape all user-controlled strings before interpolating them into markup.
 * @param {unknown} value User text or an attribute value.
 * @returns {string} HTML-safe text.
 */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

/**
 * Render one decorative icon; accessible labels belong to its containing control.
 * @param {string} name Key from the authored icon collection.
 * @returns {string} Inline SVG markup.
 */
function icon(name) { return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.paper}</svg>`; }

/** @returns {Object} The project selected by the current in-memory navigation. */
function project() { return state.projects.find(item => item.id === state.activeId) || state.projects[0]; }

/**
 * Count review work without treating a selected goal as a proof result.
 * @param {Object} current Project to inspect.
 * @returns {{total:number,confirmed:number,goals:number,ready:boolean}} Review progress.
 */
function progress(current = project()) {
  /** @type {number} Number of source/model fields explicitly confirmed in this session. */
  const confirmed = current.fields.filter(field => field.confirmed).length;
  /** @type {number} Number of selected targets. */
  const goals = current.goals.filter(goal => goal.selected).length;
  return { total: current.fields.length, confirmed, goals, ready: current.fields.length > 0 && confirmed === current.fields.length && goals > 0 };
}

/**
 * Show short action feedback without interrupting the task.
 * @param {string} message Plain-language result of an interaction.
 */
function notify(message) {
  /** @type {HTMLElement} Live region shared by all prototype interactions. */
  const toast = document.getElementById("toast");
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("visible");
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 3500);
}

/**
 * Generate route links so browser back/forward navigation remains meaningful.
 * @param {string} page Destination page.
 * @returns {string} Hash route bound to the selected project.
 */
function route(page) { return `#${page}/${encodeURIComponent(state.activeId)}`; }

/**
 * Navigate without persistence or touching the real application.
 * @param {string} page Home, review, or workbench.
 */
function navigate(page) {
  if (location.hash === route(page)) { state.page = page; render(); }
  else location.hash = route(page);
}

/** Read supported hash routes; unknown project IDs safely return to the sample. */
function readRoute() {
  /** @type {string[]} Route segments contain only page and local project identifiers. */
  const segments = location.hash.slice(1).split("/");
  state.page = ["home", "review", "workbench"].includes(segments[0]) ? segments[0] : "home";
  if (state.projects.some(item => item.id === segments[1])) state.activeId = segments[1];
  render();
  window.scrollTo({ top: 0 });
  document.getElementById("main").focus({ preventScroll: true });
}

/**
 * Render the persistent shell and the requested page.
 * @param {boolean} keepScroll Preserve document position after an in-place edit.
 */
function render(keepScroll = true) {
  /** @type {Object} Selected project used by the shell and page. */
  const current = project();
  /** @type {Record<string,string>} Plain-language navigation names. */
  const titles = { home: "项目首页", review: "资料核对", workbench: "推导工作台" };
  /** @type {number} Previous scroll offset for non-navigation interactions. */
  const scrollY = window.scrollY;
  app.innerHTML = `<div class="shell">
    <aside class="sidebar">
      <a class="brand" href="${route("home")}" aria-label="autoRTA 项目首页"><svg class="brand-mark" viewBox="0 0 32 34" aria-hidden="true"><path d="m4 28 12-22 12 22M9 20h14" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16" cy="6" r="3" fill="#2945af"/></svg><span class="brand-name">autoRTA</span></a>
      <div class="workspace-label">我的研究空间</div>
      <nav class="nav" aria-label="主导航">${Object.entries(titles).map(([page, title], index) => `<a href="${route(page)}" class="${state.page === page ? "active" : ""}" ${state.page === page ? 'aria-current="page"' : ""}>${icon(["home", "paper", "graph"][index])}<span class="nav-label">${title}</span>${page === "review" && !progress().ready ? '<span class="nav-count">待核对</span>' : ""}</a>`).join("")}</nav>
      <div class="sidebar-project"><span class="small muted">当前项目</span><strong>${escapeHtml(current.name)}</strong><span class="badge ${current.run === "done" ? "green" : "blue"}">${current.kind === "sample" ? "示例项目" : "本次会话"}</span></div>
      <div class="sidebar-bottom"><button class="button quiet compact" data-action="help" aria-label="查看原型使用说明">${icon("help")}<span>使用说明</span></button><button class="button quiet compact" data-action="reset" aria-label="重置原型演示">${icon("reset")}<span>重新体验</span></button><div class="small">交互原型 · v0.1<br>刷新后恢复初始状态</div></div>
    </aside>
    <div class="main-column"><header class="topbar"><div class="breadcrumbs">研究空间 <span>/</span><strong>${titles[state.page]}</strong></div><div class="row"><span class="prototype-label">示例内容 · 未连接分析服务</span><span class="avatar" aria-hidden="true">研</span></div></header>
    <main id="main" tabindex="-1" class="page ${state.page === "review" ? "review-page" : state.page === "workbench" ? "workbench-page" : "home-page"}">${state.page === "home" ? homePage() : state.page === "review" ? reviewPage() : workbenchPage()}</main></div>
  </div>`;
  if (keepScroll) window.scrollTo({ top: scrollY });
  if (state.page === "home") renderProjectRows();
}

/** @returns {string} Project overview, continuation task and import choices. */
function homePage() {
  /** @type {Object} Current project, whose next step drives the large continuation panel. */
  const current = project();
  /** @type {boolean} A prepared or started project can continue to the derivation view. */
  const canContinue = progress().ready || current.run !== "idle";
  return `<div class="page-heading"><div><h1>从一个问题，开始研究</h1><p>导入资料，确认目标，再看每一步如何得到结论。</p></div><button class="button" data-action="import">${icon("plus")}新建项目</button></div>
    <section class="continue-panel" aria-labelledby="continue-title"><div class="continue-content"><span class="badge ${canContinue ? "green" : "amber"}"><span class="status-dot"></span>${current.run === "decision" ? "有一项决定待确认" : canContinue ? "可以继续推导" : "等待你核对资料"}</span><h2 id="continue-title">${escapeHtml(current.name)}</h2><p>${current.run === "done" ? "本轮演示已结束。查看完成了哪些步骤，以及还缺哪些证明。" : canContinue ? "条件和目标已确认，接下来查看推导路线与待解决的问题。" : "先检查论文里的条件与目标，确认这就是你要研究的问题。"}</p><div class="continue-actions"><button class="button primary" data-action="navigate" data-page="${canContinue ? "workbench" : "review"}">${canContinue ? "打开工作台" : "核对资料"}${icon("arrow")}</button><span class="small muted">${current.kind === "sample" ? "case_11 示例" : "仅保留在当前页面"}</span></div><div class="mini-route" aria-label="导入资料、核对内容、推导验证、查看结果"><span>导入资料</span><span>核对内容</span><span>推导验证</span><span>查看结果</span></div></div><div class="paper-teaser" aria-hidden="true"><img src="prototype-assets/case11-page4.png" width="155" height="201" alt=""><span class="paper-teaser-caption">case_11 · 论文第 4 页</span></div></section>
    <div class="section-heading"><h2>开始新的研究</h2><span class="small muted">两种输入方式</span></div>
    <section class="start-options" aria-label="新项目输入方式"><button class="start-option" data-action="import" id="drop-target">${icon("upload")}<span><strong>上传论文 PDF</strong><p>选择文件，或拖到这里</p></span>${icon("arrow").replace('class="icon"','class="icon trailing"')}</button><button class="start-option" data-action="manual">${icon("edit")}<span><strong>手动描述问题</strong><p>填写模型、方法和想证明的结论</p></span>${icon("arrow").replace('class="icon"','class="icon trailing"')}</button></section>
    <div class="section-heading"><h2>我的项目 <span class="small muted">${state.projects.length}</span></h2><button class="text-button" data-action="sample">打开示例</button></div>
    <div class="list-toolbar"><div class="filter-set" aria-label="项目筛选"><button data-action="filter" data-filter="all" class="${state.filter === "all" ? "active" : ""}" aria-pressed="${state.filter === "all"}">全部</button><button data-action="filter" data-filter="pending" class="${state.filter === "pending" ? "active" : ""}" aria-pressed="${state.filter === "pending"}">待处理</button></div><label class="search">${icon("search")}<span class="visually-hidden">搜索项目</span><input id="project-search" name="project-search" autocomplete="off" placeholder="搜索项目…" value="${escapeHtml(state.query)}"></label></div><div id="project-list" class="project-list"></div>
    <p class="home-note">${icon("info")}原型中的文件和修改只保留在当前页面，不会发送给模型。</p>`;
}

/** Refresh the small project list without moving focus out of its search input. */
function renderProjectRows() {
  /** @type {Object[]} Projects matching the active text and status filters. */
  const matches = state.projects.filter(item => item.name.toLowerCase().includes(state.query.toLowerCase()) && (state.filter !== "pending" || item.run !== "done"));
  document.getElementById("project-list").innerHTML = matches.length ? matches.map(item => `<article class="project-row"><div class="row"><span class="project-icon">${icon("paper")}</span><div class="grow"><h3>${escapeHtml(item.name)}</h3><p>${item.kind === "sample" ? "case_11 · 示例" : item.kind === "pdf" ? "PDF · 本次会话" : "手动输入 · 本次会话"} · ${item.goals.filter(goal => goal.selected).length} 个目标</p></div></div><span class="badge ${item.run === "done" ? "green" : "amber"}">${item.run === "done" ? "演示结束" : item.run === "decision" ? "待确认" : progress(item).ready ? "可开始" : "待核对"}</span><button class="button compact" data-action="open-project" data-id="${item.id}">${progress(item).ready ? "打开工作台" : "继续核对"}${icon("arrow")}</button></article>`).join("") : '<div class="empty-state">没有找到项目。试试其他名称或切换“全部”。</div>';
}

/** @returns {string} Small sequential progress indicator for the review task. */
function steps() {
  return `<div class="steps" aria-label="当前步骤：核对内容"><span class="step done"><span class="step-num">${icon("check")}</span>导入资料</span><span class="step-line"></span><span class="step active"><span class="step-num">2</span>核对内容</span><span class="step-line"></span><span class="step"><span class="step-num">3</span>推导验证</span><span class="step-line"></span><span class="step"><span class="step-num">4</span>查看结果</span></div>`;
}

/** @returns {string} A source view appropriate to the actual origin of this project. */
function sourcePane() {
  /** @type {Object} Current source owner. */
  const current = project();
  /** @type {Object|undefined} Field whose source the user last inspected. */
  const field = current.fields.find(item => item.id === state.sourceField);
  /** @type {boolean} Original page images are reserved for the bundled sample. */
  const imageSource = current.kind === "sample" && (!field || field.page);
  /** @type {number} Page corresponding to the selected source reference. */
  const page = field?.page || (current.kind === "sample" ? 4 : 1);
  /** @type {string} Visible source body; arbitrary files never inherit sample content. */
  let sourceBody;
  if (imageSource) {
    sourceBody = `<div class="document-scroll"><div class="document-sheet"><img src="prototype-assets/case11-page${page}.png" width="1224" height="1584" alt="case_11 论文第 ${page} 页原文">${state.sourceField === "iteration" ? '<div class="source-box focused" aria-hidden="true"></div>' : ""}</div></div><div class="source-caption">${icon("eye")}第 ${page} 页 · ${state.sourceField === "iteration" ? "高亮区域为 Fig. 3 算法" : escapeHtml(field?.source || "论文原文")}</div>`;
  } else if (current.kind === "sample") {
    sourceBody = `<div class="source-text"><h3>${escapeHtml(field.source)}</h3><p style="margin-top:14px">${escapeHtml(field.value)}</p><p class="muted small" style="margin-top:20px">这是项目的模型约定，不是论文原文。${field.scope ? "结果仅覆盖整数时间；连续时间需要另外建立。" : "采用前需要明确确认。"}</p><button class="button compact" style="margin-top:20px" data-action="source" data-id="iteration">返回论文页图</button></div>`;
  } else if (current.pdf) {
    sourceBody = `<div class="file-placeholder">${icon("paper")}<h3>${escapeHtml(current.fileName)}</h3><p>文件已选好，仅保留在当前浏览器。</p><a class="button compact" href="${escapeHtml(current.pdf)}" target="_blank" rel="noopener">打开所选 PDF${icon("external")}</a><p class="small muted">内嵌预览与自动抽取后续接入。<br>可以先在右侧手动补充内容。</p></div>`;
  } else {
    sourceBody = `<div class="source-text">${escapeHtml(current.originalText || "你填写的模型、方法与目标会显示在这里。")}</div><div class="source-caption">${icon("edit")}手动输入 · 无论文页码</div>`;
  }
  return `<section class="document-pane" aria-label="来源资料"><div class="pane-toolbar"><span class="row">${icon("paper")}<strong>${current.kind === "manual" ? "原始输入" : "论文原文"}</strong></span><div class="row"><button class="text-button source-toggle" style="display:none" data-action="toggle-source">${state.sourceCollapsed ? "展开" : "收起"}</button>${current.pdf ? `<a href="${escapeHtml(current.pdf)}#page=${page}" target="_blank" rel="noopener" class="text-button">打开 PDF${icon("external")}</a>` : ""}</div></div>${sourceBody}</section>`;
}

/** @returns {string} Source-linked editable fields, target choices and next action. */
function reviewPage() {
  /** @type {Object} Project whose draft is currently being reviewed. */
  const current = project();
  /** @type {ReturnType<typeof progress>} Explicit review state for the footer. */
  const review = progress();
  /** @type {Object[]} Fields visible in the current review tab. */
  const fields = current.fields.filter(field => field.category === state.reviewTab);
  /** @type {string} Next actionable label instead of a generic submit button. */
  const nextLabel = state.reviewTab === "model" ? "继续核对方法" : state.reviewTab === "method" ? "选择证明目标" : review.ready ? "进入推导工作台" : "回到待核对项";
  return `<div class="page-heading"><div><h1>先确认，我们理解对了</h1><p>${escapeHtml(current.name)}</p></div><button class="button quiet compact" data-action="navigate" data-page="home">${icon("back")}项目首页</button></div>${steps()}<div class="review-layout ${state.sourceCollapsed ? "source-collapsed" : ""}">${sourcePane()}
    <section class="review-pane" aria-label="待核对内容"><div class="tabs" role="tablist" aria-label="核对内容分类">${[["model", "模型条件"], ["method", "分析方法"], ["goals", "证明目标"]].map(([tab, title]) => `<button role="tab" id="tab-${tab}" aria-selected="${state.reviewTab === tab}" aria-controls="review-content" data-action="review-tab" data-tab="${tab}" class="${state.reviewTab === tab ? "active" : ""}">${title}<span class="tab-count">${tab === "goals" ? current.goals.length : current.fields.filter(item => item.category === tab).length}</span></button>`).join("")}</div>
    <div class="review-intro"><span class="muted">${state.reviewTab === "goals" ? "选择本轮想解决的问题" : "检查内容，也可以直接修改"}</span>${state.reviewTab === "goals" ? `<span class="badge blue">已选 ${review.goals} 项</span>` : fields.length ? '<button class="text-button" data-action="confirm-tab">确认本页内容</button>' : ""}</div>
    <div id="review-content" class="field-list" role="tabpanel" aria-labelledby="tab-${state.reviewTab}">${state.reviewTab === "goals" ? current.goals.map(goal => `<div class="goal-option"><input id="goal-${goal.id}" name="goals" type="checkbox" data-goal="${goal.id}" ${goal.selected ? "checked" : ""}><label for="goal-${goal.id}"><strong>${escapeHtml(goal.title)}</strong><p>${escapeHtml(goal.description)}</p></label></div>`).join("") : fields.map(field => `<article class="field-item"><div class="field-label">${escapeHtml(field.label)}${field.scope ? '<span class="badge amber">范围选择</span>' : ""}</div><p class="field-value">${escapeHtml(field.value)}</p>${field.scope ? '<p class="scope-note">这个选择只覆盖整数时间，需要你确认。</p>' : ""}<div class="field-tools"><button class="text-button" data-action="source" data-id="${field.id}">${field.page ? `查看来源 · 第 ${field.page} 页` : current.kind === "sample" ? "查看约定" : "查看输入"}</button><button class="text-button" data-action="edit-field" data-id="${field.id}" aria-label="修改${escapeHtml(field.label)}">修改</button><button class="text-button confirm ${field.confirmed ? "confirmed" : ""}" data-action="confirm-field" data-id="${field.id}" aria-pressed="${field.confirmed}">${field.confirmed ? icon("check") + "已确认" : "确认"}</button></div></article>`).join("")}${(!fields.length && state.reviewTab !== "goals") || (!current.goals.length && state.reviewTab === "goals") ? `<div class="empty-state"><h3>${current.kind === "pdf" ? "论文已选好，等待补充内容" : "这里还没有内容"}</h3><p class="small" style="margin:9px 0 18px">自动抽取后续接入，先手动填写即可体验流程。</p><button class="button" data-action="fill-current">${icon("edit")}手动补充</button></div>` : ""}</div></section></div>
    <div class="review-footer"><div class="review-progress"><span class="progress-track" aria-hidden="true"><span style="width:${review.total ? review.confirmed / review.total * 100 : 0}%"></span></span><span>${review.confirmed}/${review.total} 项已核对${state.reviewTab === "goals" ? ` · 已选 ${review.goals} 个目标` : ""}</span></div><div class="row">${state.reviewTab !== "model" ? '<button class="button quiet compact" data-action="previous-tab">上一步</button>' : ""}<button class="button primary" data-action="review-next" ${!current.fields.length ? "disabled" : ""}>${nextLabel}${icon("arrow")}</button></div></div><p class="review-notice">${review.ready ? "演示会使用当前已确认内容；修改后需重新核对。" : "确认只表示你认可输入内容，是否成立还要经过证明检查。"}</p>`;
}

/** @returns {Object[]} Five meaningful sample nodes for the two-sided proof view. */
function nodes() {
  /** @type {Object} Project controlling the simulated node states. */
  const current = project();
  /** @type {boolean} Whether the bridge decision has been explicitly accepted. */
  const resolved = current.decision;
  return [
    { id: "model", title: progress().ready ? "已确认的模型" : "待核对的模型", hint: `${current.fields.filter(field => field.category === "model").length} 项条件`, status: progress().ready ? "checked" : "open", label: "从条件出发", body: "这里汇集本轮使用的模型条件。每项条件都能回到资料核对页查看来源。", formula: current.kind === "sample" ? "0 &lt; C ≤ D ≤ T" : "用户确认的模型条件" },
    { id: "service", title: "任务能得到多少执行时间", hint: "建立执行时间的下界", status: current.run === "idle" ? "open" : "checked", label: "正向推导 · 示例", body: "先排除被高优先级任务占用的时间，再计算当前任务至少能得到多少执行时间。", formula: "可用时间 − 干扰时间" },
    { id: "bridge", title: "把两侧结论连接起来", hint: resolved ? "排序规则已确认" : "还差一个调度条件", status: resolved ? "checked" : "decision", label: resolved ? "已确认 · 示例" : "需要你的确认", body: resolved ? "同截止期任务按固定任务顺序排序。接下来仍需证明服务界限与调度行为之间的联系。" : "截止期相同的任务，需要一个稳定的先后顺序，才能继续连接两侧结论。", formula: "可用执行时间 ≥ 所需执行时间" },
    { id: "response", title: "截止前能否完成执行", hint: "拆解需要满足的条件", status: "open", label: "从目标倒推 · 示例", body: "要证明按期完成，需要说明每个合法作业在截止前得到的执行时间足够。", formula: "完成时间 ≤ 截止时间" },
    { id: "goal", title: "任务都能按期完成", hint: "本轮主要目标", status: "open", label: "待证明", body: current.goals.filter(goal => goal.selected).map(goal => goal.title).join("；") || "请先选择一个证明目标。", formula: "所有合法作业，都满足截止期" }
  ];
}

/** @returns {string} Central graph or its accessible sequential alternative. */
function graphContent() {
  if (state.graphView === "list") return `<div class="route-list">${nodes().map((node, index) => `<div class="route-row"><span class="step-num">${index + 1}</span><button data-action="node" data-id="${node.id}"><strong>${escapeHtml(node.title)}</strong><p>${escapeHtml(node.label)}</p></button>${icon("arrow")}</div>`).join("")}</div>`;
  return `<div class="graph-scroll-hint" style="display:none">左右滑动查看全图，点击节点查看详情。</div><div class="graph-viewport"><div class="graph-board" style="transform:scale(${state.scale})"><span class="column-label left">从已知条件出发</span><span class="column-label center">连接两侧结论</span><span class="column-label right">从目标向后拆解</span><svg class="graph-lines" viewBox="0 0 760 470" aria-hidden="true"><defs><marker id="arrow-left" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="#76a99c"/></marker><marker id="arrow-right" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 10 5 0 10z" fill="#8a9dd0"/></marker></defs><path class="edge left" marker-end="url(#arrow-left)" d="M123 183V269"/><path class="edge right" marker-end="url(#arrow-right)" d="M637 183V269"/><path class="edge left" marker-end="url(#arrow-left)" d="M220 320H244Q258 320 258 300V243Q258 224 279 224"/><path class="edge right" marker-end="url(#arrow-right)" d="M540 320H516Q502 320 502 300V243Q502 224 481 224"/><path class="edge dashed" d="M380 274v125"/><text x="380" y="426" text-anchor="middle" fill="#8a7149" font-size="11">${project().decision ? "连接关系仍待真实证明检查" : "待补齐的联系"}</text></svg>${nodes().map(node => `<button data-action="node" data-id="${node.id}" class="node position-${node.id} ${node.status} ${state.selectedNode === node.id ? "selected" : ""}" aria-pressed="${state.selectedNode === node.id}"><span class="node-state"><span class="status-dot"></span>${escapeHtml(node.label)}</span><span class="node-title">${escapeHtml(node.title)}</span><span class="node-hint">${escapeHtml(node.hint)}</span></button>`).join("")}</div></div>`;
}

/** @returns {string} Context-sensitive details, with evidence reachable on demand. */
function inspector() {
  /** @type {Object} Currently selected graph node. */
  const node = nodes().find(item => item.id === state.selectedNode) || nodes()[2];
  return `<aside class="inspector" aria-label="所选节点详情"><div class="inspector-head"><span class="badge ${node.status === "decision" ? "amber" : node.status === "checked" ? "green" : "blue"}">${escapeHtml(node.label)}</span><h2 style="margin-top:11px">${escapeHtml(node.title)}</h2></div><div class="inspector-body"><div><h3>这一步在做什么</h3><p>${escapeHtml(node.body)}</p></div><div><h3>要建立的关系</h3><div class="formula">${node.formula}</div></div><div class="detail-links">${node.id === "bridge" && !project().decision ? `<button class="button primary" data-action="decision" ${project().run !== "decision" ? "disabled" : ""}>确认排序规则${icon("arrow")}</button>${project().run !== "decision" ? '<span class="small muted">开始演示后可处理这项决定。</span>' : ""}` : ""}<button class="detail-link" data-action="evidence">查看证明记录${icon("external")}</button><button class="detail-link" data-action="navigate" data-page="review">回到条件与来源${icon("arrow")}</button><button class="detail-link" data-action="feedback">提出修改意见${icon("edit")}</button></div></div></aside>`;
}

/** @returns {string} Bidirectional reasoning view with honest demonstration states. */
function workbenchPage() {
  /** @type {Object} Project controlling the run header and activity list. */
  const current = project();
  /** @type {string} Task-specific guidance at the top of the workbench. */
  let strip = progress().ready ? `<span>${icon("play")}</span><p class="grow">条件与目标已确认。可以开始体验推导流程。</p><button class="button primary compact" data-action="start-run">开始演示${icon("arrow")}</button>` : `<span>${icon("paper")}</span><p class="grow">先核对资料并选择目标，再开始分析。</p><button class="button primary compact" data-action="navigate" data-page="review">去核对资料${icon("arrow")}</button>`;
  if (current.kind !== "sample") strip = `<span>${icon("info")}</span><p class="grow">已保留你的输入。推导功能后续接入；先查看 case_11 示例。</p><button class="button primary compact" data-action="sample-workbench">体验示例流程</button>`;
  else if (current.run === "running") strip = '<span class="simulation-progress" aria-hidden="true"></span><p class="grow">正在演示路线展开… 未运行真实证明检查。</p><button class="button compact" data-action="pause-run">暂停</button>';
  else if (current.run === "paused") strip = '<span>' + icon("pause") + '</span><p class="grow">演示已暂停，当前内容保留。</p><button class="button primary compact" data-action="start-run">继续演示</button>';
  else if (current.run === "decision") strip = `<span>${icon("info")}</span><p class="grow"><strong>需要你确认一个条件</strong><br>截止期相同的任务，按什么顺序执行？</p><button class="button primary compact" data-action="decision">查看并确认${icon("arrow")}</button>`;
  else if (current.run === "done") strip = `<span>${icon("check")}</span><p class="grow"><strong>本轮演示结束</strong><br>主目标仍待证明，可以查看剩余问题。</p><button class="button primary compact" data-action="results">查看结果${icon("arrow")}</button>`;
  return `<div class="page-heading"><div><h1>推导工作台</h1><p>${escapeHtml(current.name)}</p></div><div class="row"><button class="button quiet compact" data-action="budget">${icon("clock")}预算与用量</button><button class="button compact" data-action="feedback">${icon("edit")}提出修改</button></div></div><div class="next-strip ${current.run === "decision" ? "decision-strip" : current.run === "done" ? "result-strip" : ""}" role="status">${strip}</div>
    ${current.kind === "sample" ? `<div class="workbench-layout"><div><section class="graph-pane" aria-label="双向推导图"><div class="graph-toolbar"><div class="graph-tabs"><strong>双向推导</strong><span class="muted">示例路线 v1</span></div><div class="graph-tools"><button class="text-button" data-action="toggle-graph">${state.graphView === "canvas" ? "列表视图" : "画布视图"}</button><button class="icon-button" data-action="zoom-out" aria-label="缩小推导图">${icon("minus")}</button><button class="icon-button" data-action="zoom-in" aria-label="放大推导图">${icon("plus")}</button><button class="icon-button" data-action="fit" aria-label="适应画布宽度">${icon("fit")}</button></div></div>${graphContent()}<div class="graph-legend"><span><i class="legend-line"></i>正向推导</span><span><i class="legend-line back"></i>目标拆解</span><span><i class="legend-line gap"></i>待建立联系</span><span>所有节点状态均为演示</span></div></section><section class="activity"><div class="activity-heading">${icon("clock")}本轮动态<span class="small muted">仅示例流程</span></div><ul>${current.activity.length ? current.activity.map((entry, index) => `<li><time>步骤 ${index + 1}</time><span>${escapeHtml(entry)}</span></li>`).join("") : '<li><span>开始演示后，这里会显示每一步进展。</span></li>'}</ul></section></div>${inspector()}</div>` : `<section class="document-pane" style="margin-top:20px"><div class="pane-toolbar"><strong>本轮选择的目标</strong><span class="badge">尚未推导</span></div><div class="dialog-body stack">${current.goals.filter(goal => goal.selected).map(goal => `<p>${escapeHtml(goal.title)}</p>`).join("") || '<p class="muted">还未选择目标。</p>'}<p class="small muted">不会用示例的模型条件或图替代你的输入。</p><button class="button" data-action="navigate" data-page="review">继续编辑我的资料</button></div></section>`}`;
}

/**
 * Open a focused dialog and retain a best-effort return target.
 * @param {string} title Accessible dialog name.
 * @param {string} subtitle Short explanation under the title.
 * @param {string} body Trusted markup with escaped user strings.
 * @param {string} footer Action markup.
 */
function openDialog(title, subtitle, body, footer = '<button class="button primary" data-action="close-dialog">知道了</button>') {
  dialogTrigger = document.activeElement;
  dialog.innerHTML = `<div class="dialog-head"><div><h2 id="dialog-title">${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div><button class="icon-button" data-action="close-dialog" aria-label="关闭对话框">${icon("close")}</button></div><div class="dialog-body">${body}</div><div class="dialog-footer">${footer}</div>`;
  if (!dialog.open) dialog.showModal();
}

/** Close a native dialog and restore focus when its triggering element still exists. */
function closeDialog() { dialog.close(); if (dialogTrigger?.isConnected) dialogTrigger.focus(); }

/**
 * Open PDF selection. The selected bytes never leave the browser.
 * @param {File|null} droppedFile Optional file supplied by drag-and-drop.
 */
function importDialog(droppedFile = null) {
  openDialog("上传论文 PDF", "先预览论文，再补充要研究的问题。", `<div class="form-field"><label for="import-name">项目名称</label><input id="import-name" name="project-name" autocomplete="off" placeholder="例如：任务响应时间分析…"></div><label class="upload-area" id="file-drop">${icon("upload")}<strong>选择 PDF，或拖到这里</strong><p>文件仅在本地浏览器中预览</p><input id="pdf-input" type="file" accept=".pdf,application/pdf" aria-label="选择论文 PDF"></label><p id="file-status" class="small muted" style="margin-top:13px">此原型支持文件预览，自动抽取后续接入。</p><p id="import-error" class="form-error" role="alert"></p>`, '<button class="button quiet" data-action="close-dialog">取消</button><button class="button primary" data-action="create-pdf">打开资料核对</button>');
  state.pendingFile = droppedFile;
  if (droppedFile) showPendingFile();
}

/** Update the file-selection feedback without replacing the native file input. */
function showPendingFile() {
  /** @type {File|undefined} File selected using either file input or drop zone. */
  const file = state.pendingFile;
  if (!file) return;
  document.getElementById("file-status").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB · 仅预览，不自动抽取`;
  if (!document.getElementById("import-name").value) document.getElementById("import-name").value = file.name.replace(/\.pdf$/i, "");
}

/**
 * Present three familiar text fields for manual MSA input, without exposing IR.
 * @param {boolean} updateCurrent True when filling an imported project's missing content.
 */
function manualDialog(updateCurrent = false) {
  state.editCurrent = updateCurrent;
  openDialog(updateCurrent ? "补充研究内容" : "描述你的研究问题", "用你熟悉的语言写，之后还可以修改。", `<div class="form-field"><label for="manual-name">项目名称</label><input id="manual-name" name="project-name" autocomplete="off" value="${updateCurrent ? escapeHtml(project().name) : ""}" placeholder="例如：固定优先级任务分析…"></div><div class="form-field"><label for="manual-model">模型条件</label><textarea id="manual-model" name="model" placeholder="有哪些任务？使用什么调度方式？…"></textarea></div><div class="form-field"><label for="manual-method">分析方法</label><textarea id="manual-method" name="method" placeholder="准备如何计算或分析？…"></textarea></div><div class="form-field"><label for="manual-goal">想证明什么</label><textarea id="manual-goal" name="goal" placeholder="例如：满足这些条件时，所有任务都能按期完成…"></textarea></div><p id="manual-error" class="form-error" role="alert"></p>`, '<button class="button quiet" data-action="close-dialog">取消</button><button class="button primary" data-action="create-manual">进入资料核对</button>');
}

/**
 * Invalidate simulated analysis when confirmed inputs change.
 * @param {Object} current Edited project.
 */
function invalidateRun(current) {
  clearTimeout(runTimer);
  current.run = "idle";
  current.decision = false;
  current.activity = [];
}

/** Advance the simulated run to an explicit decision, never to a claimed proof. */
function startRun() {
  /** @type {Object} Stable project reference retained across navigation. */
  const current = project();
  if (current.kind !== "sample" || !progress().ready) return;
  current.run = "running";
  current.activity = ["已保留本轮条件和所选目标（演示）", "展开正向推导与目标拆解（演示）"];
  render();
  clearTimeout(runTimer);
  runTimer = window.setTimeout(() => {
    current.run = current.decision ? "done" : "decision";
    current.activity.push(current.decision ? "演示结束；主目标仍待真实证明" : "发现相同截止期下的排序规则需要确认");
    if (project().id === current.id) render();
    notify(current.decision ? "演示结束，可以查看结果。" : "有一项排序规则需要你确认。");
  }, 1600);
}

/** Show the exact proposed mathematical change before applying it in the demo. */
function decisionDialog() {
  openDialog("截止期相同，怎么排先后？", "这会补充一项模型条件，需要你明确选择。", '<div class="change-preview"><div><span class="small muted">当前约定</span><p>截止期越短，优先级越高；相同截止期的顺序未指定。</p></div><div><span class="small muted">拟补充</span><p>相同截止期的任务，始终按固定任务序号排序。</p></div></div><p class="small muted" style="margin-top:14px">影响：后续结论将依赖这项排序约定，仍需检查相应证明。</p><label class="choice"><input type="radio" name="decision" value="fixed"><div>采用固定任务顺序<span>确认后继续演示推导流程。</span></div></label><label class="choice"><input type="radio" name="decision" value="later" checked><div>暂不决定<span>保留当前进度，稍后再处理。</span></div></label>', '<button class="button quiet" data-action="close-dialog">返回工作台</button><button class="button primary" data-action="apply-decision">应用选择</button>');
}

/** Display outcome boundaries prominently instead of a misleading success badge. */
function resultsDialog() {
  openDialog("本轮结果", "以下是界面演示，不是真实检查回执。", `<div class="evidence-summary"><strong>主要目标尚未证明</strong><p>示例展示了从资料核对到数学决定确认的操作流程。</p></div><div class="result-rows"><div class="result-row"><strong>输入与目标</strong><span class="badge green">已核对</span></div><div class="result-row"><strong>相同截止期的排序规则</strong><span class="badge ${project().decision ? "green" : "amber"}">${project().decision ? "已确认" : "待确认"}</span></div><div class="result-row"><strong>调度行为与执行时间的联系</strong><span class="badge amber">待证明</span></div><div class="result-row"><strong>所有任务按期完成</strong><span class="badge amber">待证明</span></div><div class="result-row"><strong>真实模型调用／证明检查</strong><span>0 次／0 次</span></div></div>`, '<button class="button quiet" data-action="close-dialog">返回工作台</button><button class="button primary" data-action="feedback">提出修改意见</button>');
}

/**
 * Route all button interactions through one small prototype dispatcher.
 * @param {HTMLElement} button Clicked control carrying a data-action attribute.
 */
function act(button) {
  /** @type {string} Declarative action attached to the clicked control. */
  const action = button.dataset.action;
  /** @type {Object} Project current at the time of the interaction. */
  const current = project();
  if (action === "navigate") { closeDialog(); navigate(button.dataset.page); }
  else if (action === "close-dialog") closeDialog();
  else if (action === "import") importDialog();
  else if (action === "manual") manualDialog();
  else if (action === "fill-current") manualDialog(true);
  else if (action === "sample" || action === "sample-workbench") { state.activeId = "case11"; state.reviewTab = "model"; navigate(action === "sample" ? "review" : "workbench"); }
  else if (action === "open-project") { state.activeId = button.dataset.id; state.reviewTab = "model"; navigate(progress().ready ? "workbench" : "review"); }
  else if (action === "filter") { state.filter = button.dataset.filter; render(); }
  else if (action === "review-tab") { state.reviewTab = button.dataset.tab; render(); document.getElementById(`tab-${state.reviewTab}`).focus(); }
  else if (action === "previous-tab") { state.reviewTab = state.reviewTab === "goals" ? "method" : "model"; render(); }
  else if (action === "toggle-source") { state.sourceCollapsed = !state.sourceCollapsed; render(); }
  else if (action === "source") { state.sourceField = button.dataset.id; state.sourceCollapsed = false; render(); document.querySelector(".document-pane").scrollIntoView({ block: "nearest", behavior: "smooth" }); notify("已定位到这项内容的来源。"); }
  else if (action === "confirm-field") { /** @type {Object} Field whose review flag is toggled by its control. */ const field = current.fields.find(item => item.id === button.dataset.id); field.confirmed = !field.confirmed; if (!field.confirmed) invalidateRun(current); render(); notify(field.confirmed ? "这项内容已确认。" : "已取消确认，可继续修改。"); }
  else if (action === "confirm-tab") { current.fields.filter(field => field.category === state.reviewTab).forEach(field => { field.confirmed = true; }); render(); notify("本页内容已确认，继续下一步。"); }
  else if (action === "review-next") {
    if (state.reviewTab === "model") state.reviewTab = "method";
    else if (state.reviewTab === "method") state.reviewTab = "goals";
    else if (progress().ready) { navigate("workbench"); return; }
    else { /** @type {Object|undefined} First unconfirmed field determines the next review tab. */ const missing = current.fields.find(field => !field.confirmed); if (missing) state.reviewTab = missing.category; notify(missing ? "先确认这些内容，再开始分析。" : "请至少选择一个证明目标。"); }
    render();
  }
  else if (action === "edit-field") {
    /** @type {Object} Field whose current value is shown before editing. */
    const field = current.fields.find(item => item.id === button.dataset.id);
    state.editField = field.id;
    openDialog(`修改${escapeHtml(field.label)}`, "保存后需要重新确认这项内容。", `<div class="form-field"><label for="field-value">${escapeHtml(field.label)}</label><textarea id="field-value" name="field-value" rows="4">${escapeHtml(field.value)}</textarea><p>${escapeHtml(field.source)}</p></div><p id="edit-error" class="form-error" role="alert"></p>`, '<button class="button quiet" data-action="close-dialog">取消</button><button class="button primary" data-action="save-field">保存修改</button>');
  }
  else if (action === "save-field") {
    /** @type {string} Trimmed replacement text; empty fields stay in the editor. */
    const value = document.getElementById("field-value").value.trim();
    if (!value) { document.getElementById("edit-error").textContent = "请填写内容后再保存。"; document.getElementById("field-value").focus(); return; }
    /** @type {Object} Existing source metadata is retained while the value is revised. */
    const field = current.fields.find(item => item.id === state.editField);
    field.value = value; field.confirmed = false; field.revised = true; invalidateRun(current); closeDialog(); render(); notify("修改已保留在本次会话，请重新确认。");
  }
  else if (action === "create-pdf") {
    /** @type {File|undefined} File chosen by the user, never uploaded to a server. */
    const file = state.pendingFile;
    if (!file || !/\.pdf$/i.test(file.name)) { document.getElementById("import-error").textContent = "请选择一个 PDF 文件。"; document.getElementById("pdf-input").focus(); return; }
    /** @type {string} Short project identifier independent of the file's name. */
    const id = `project-${Date.now()}`;
    state.projects.push({ id, name: document.getElementById("import-name").value.trim() || file.name, kind: "pdf", fileName: file.name, pdf: URL.createObjectURL(file), fields: [], goals: [], run: "idle", decision: false, feedback: [], activity: [] });
    state.activeId = id; state.reviewTab = "model"; state.sourceField = ""; closeDialog(); navigate("review");
  }
  else if (action === "create-manual") {
    /** @type {string[]} Required input names keep the manual form small and predictable. */
    const names = ["name", "model", "method", "goal"];
    /** @type {Record<string,string>} Trimmed values captured only after submission. */
    const values = Object.fromEntries(names.map(name => [name, document.getElementById(`manual-${name}`).value.trim()]));
    /** @type {string|undefined} First empty field to receive accessible focus. */
    const missing = names.find(name => !values[name]);
    if (missing) { document.getElementById("manual-error").textContent = "请补充项目名称、模型、方法和目标。"; document.getElementById(`manual-${missing}`).focus(); return; }
    /** @type {Object} New project or imported project currently receiving its semantic content. */
    const target = state.editCurrent ? current : { id: `project-${Date.now()}`, kind: "manual", run: "idle", decision: false, feedback: [], activity: [] };
    target.name = values.name;
    target.originalText = `模型条件\n${values.model}\n\n分析方法\n${values.method}\n\n证明目标\n${values.goal}`;
    target.fields = [{ id: "user-model", label: "模型条件", value: values.model, category: "model", source: "用户手动输入", confirmed: false }, { id: "user-method", label: "分析方法", value: values.method, category: "method", source: "用户手动输入", confirmed: false }];
    target.goals = [{ id: "user-goal", title: values.goal, description: "来自你的手动输入，可作为本轮目标。", selected: true }];
    invalidateRun(target); if (!state.editCurrent) state.projects.push(target);
    state.activeId = target.id; state.reviewTab = "model"; state.sourceField = "user-model"; closeDialog(); navigate("review");
  }
  else if (action === "node") { state.selectedNode = button.dataset.id; render(); if (window.innerWidth < 1180) document.querySelector(".inspector").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  else if (action === "toggle-graph") { state.graphView = state.graphView === "canvas" ? "list" : "canvas"; render(); }
  else if (action === "zoom-in" || action === "zoom-out") { state.scale = Math.max(.45, Math.min(1.35, state.scale + (action === "zoom-in" ? .1 : -.1))); render(); }
  else if (action === "fit") { /** @type {HTMLElement|null} Visible canvas bounds determine a requested fit operation. */ const viewport = document.querySelector(".graph-viewport"); if (viewport) { state.scale = Math.min(1, viewport.clientWidth / document.querySelector(".graph-board").offsetWidth); render(); } }
  else if (action === "start-run") startRun();
  else if (action === "pause-run") { clearTimeout(runTimer); current.run = "paused"; render(); }
  else if (action === "decision") decisionDialog();
  else if (action === "apply-decision") {
    /** @type {string} A mathematical decision is applied only after an explicit radio choice. */
    const choice = dialog.querySelector('input[name="decision"]:checked').value;
    closeDialog();
    if (choice === "fixed") { current.decision = true; current.run = "done"; current.activity.push("已确认：相同截止期按固定任务顺序排序", "演示结束；主目标和调度桥接仍待真实证明"); render(); notify("排序约定已确认。查看本轮结果与剩余问题。"); }
    else notify("保持待确认状态，稍后可以继续。");
  }
  else if (action === "results") resultsDialog();
  else if (action === "evidence") openDialog("证明记录", "与所选节点关联的检查证据。", '<div class="evidence-summary"><strong>尚无真实检查记录</strong><p>这次原型没有调用 Rocq。图中状态只演示页面如何呈现结果。</p></div><div class="result-rows"><div class="result-row"><span>后续展示</span><strong>证明文件与检查结果</strong></div><div class="result-row"><span>可追溯内容</span><strong>条件、依赖和运行版本</strong></div><div class="result-row"><span>当前证据</span><strong>0 份</strong></div></div>');
  else if (action === "budget") openDialog("预算与实际用量", "原型不调用模型，不产生模型费用。", '<div class="result-rows"><div class="result-row"><strong>模型请求</strong><span>0 次</span></div><div class="result-row"><strong>证明检查</strong><span>0 次</span></div><div class="result-row"><strong>实际费用</strong><span>¥0</span></div></div><p class="small muted" style="margin-top:18px">接入服务后，这里将设置本轮上限，并展示实际消耗。</p>');
  else if (action === "feedback") openDialog("你想调整哪里？", "意见先保留在本次原型会话中，尚不自动修改推导。", `<div class="form-field"><label for="feedback-text">修改意见</label><textarea id="feedback-text" name="feedback" rows="4" placeholder="例如：先把任务到达条件解释清楚…"></textarea></div>${current.feedback.length ? `<p class="small muted">已记录 ${current.feedback.length} 条意见</p><ul class="small">${current.feedback.map(text => `<li>${escapeHtml(text)}</li>`).join("")}</ul>` : ""}<p id="feedback-error" class="form-error" role="alert"></p>`, '<button class="button quiet" data-action="close-dialog">取消</button><button class="button primary" data-action="save-feedback">记录意见</button>');
  else if (action === "save-feedback") { /** @type {string} Feedback remains local and is not executed as an instruction. */ const text = document.getElementById("feedback-text").value.trim(); if (!text) { document.getElementById("feedback-error").textContent = "请写下想调整的内容。"; return; } current.feedback.push(text); closeDialog(); notify("意见已记录在本次会话，尚未生成修订提案。"); }
  else if (action === "help") openDialog("从这里开始体验", "三个页面，一条完整操作路径。", '<div class="stack"><p><strong>1. 项目首页</strong><br><span class="muted small">打开 case_11 示例，或选择 PDF、手动填写。</span></p><p><strong>2. 资料核对</strong><br><span class="muted small">查看来源、修改内容，确认各页后选择目标。</span></p><p><strong>3. 推导工作台</strong><br><span class="muted small">点击节点，体验排序决定确认，查看剩余问题。</span></p><div class="dialog-note">页面可点击，分析与证明结果为演示。刷新会清除本次修改。</div></div>');
  else if (action === "reset") openDialog("重新体验原型？", "当前页面里的文件、修改和意见会被清除。", '<p>已保存的平台项目和证明记录不会受影响。</p>', '<button class="button quiet" data-action="close-dialog">保留当前内容</button><button class="button primary" data-action="confirm-reset">重新开始</button>');
  else if (action === "confirm-reset") { clearTimeout(runTimer); state.projects.filter(item => item.pdf?.startsWith("blob:")).forEach(item => URL.revokeObjectURL(item.pdf)); state.projects = [makeSample()]; Object.assign(state, { activeId: "case11", reviewTab: "model", selectedNode: "bridge", sourceField: "iteration", query: "", filter: "all", graphView: "canvas", scale: 1 }); closeDialog(); navigate("home"); notify("已恢复初始示例。"); }
}

/** Dispatch clicks from dynamic markup, retaining native keyboard button behavior. */
document.addEventListener("click", event => {
  /** @type {HTMLElement|null} Skip navigation moves focus without changing the page route. */
  const skipLink = event.target.closest(".skip-link");
  if (skipLink) {
    event.preventDefault();
    document.getElementById("main").focus({ preventScroll: true });
    return;
  }
  /** @type {HTMLElement|null} Closest actionable button, if the event came from one. */
  const button = event.target.closest("[data-action]");
  if (button && !button.disabled) act(button);
});

/** Keep search responsive and controlled locally without rerendering the input itself. */
document.addEventListener("input", event => {
  if (event.target.id === "project-search") { state.query = event.target.value; renderProjectRows(); }
});

/** Apply checkbox changes and file selection after native controls commit them. */
document.addEventListener("change", event => {
  if (event.target.dataset.goal) {
    /** @type {Object} Selected target whose inclusion the user explicitly changed. */
    const goal = project().goals.find(item => item.id === event.target.dataset.goal);
    goal.selected = event.target.checked; invalidateRun(project()); render(); document.getElementById(`goal-${goal.id}`).focus();
  }
  if (event.target.id === "pdf-input") { state.pendingFile = event.target.files[0]; showPendingFile(); }
});

/** Accept local PDF drops only on visible import targets. */
document.addEventListener("dragover", event => {
  /** @type {HTMLElement|null} File target under the pointer. */
  const target = event.target.closest("#drop-target, #file-drop");
  if (target) { event.preventDefault(); target.classList.add("drag-over"); }
});
/** Remove the temporary drag highlight when leaving a drop target. */
document.addEventListener("dragleave", event => event.target.closest("#drop-target, #file-drop")?.classList.remove("drag-over"));
/** Convert dropped files into the same selection flow as the native file picker. */
document.addEventListener("drop", event => {
  /** @type {HTMLElement|null} Verified drop target so unrelated drops are not intercepted. */
  const target = event.target.closest("#drop-target, #file-drop");
  if (!target) return;
  event.preventDefault(); target.classList.remove("drag-over");
  /** @type {File|undefined} First file, matching the single-paper prototype scope. */
  const file = event.dataTransfer.files[0];
  if (!file || !/\.pdf$/i.test(file.name)) { notify("请拖入一个 PDF 文件。"); return; }
  if (target.id === "drop-target") importDialog(file); else { state.pendingFile = file; showPendingFile(); }
});

/** Arrow keys traverse the review tab list without interfering with text editing. */
document.addEventListener("keydown", event => {
  if (event.target.getAttribute("role") !== "tab" || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  /** @type {string[]} Ordered review tabs for accessible directional navigation. */
  const tabs = ["model", "method", "goals"];
  state.reviewTab = tabs[(tabs.indexOf(state.reviewTab) + (event.key === "ArrowRight" ? 1 : 2)) % 3];
  render(); document.getElementById(`tab-${state.reviewTab}`).focus();
});
window.addEventListener("hashchange", readRoute);
readRoute();
