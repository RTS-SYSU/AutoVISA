/** Local MSA workbench; all mutations go through versioned server Interfaces. */
"use strict";
/** @type {Object} Current project, editable draft and explicitly selected result identities. */
const state={catalog:null,project:null,draft:null,preview:null,freeze:null,result:null};
/** @param {string} id DOM identity. @returns {HTMLElement} Existing element. */
const $=id=>document.getElementById(id);
/** @param {string} tag Element tag. @param {string} text Safe visible text. @returns {HTMLElement} New element. */
function el(tag,text=""){const node=document.createElement(tag);node.textContent=text;return node;}
/** @param {HTMLElement} parent Container. @param {string} title Label. @param {Function} action Click handler. @returns {HTMLButtonElement} Control. */
function button(parent,title,action){const node=el("button",title);node.type="button";node.onclick=()=>perform(action);parent.append(node);return node;}
/** @param {Function} action Asynchronous operation. @returns {Promise<void>} User-visible completion or failure. */
async function perform(action){try{$("notice").className="";await action();}catch(error){$("notice").className="error";$("notice").textContent=error.message;}}
/** @param {string} path Same-origin API path. @param {Object|undefined} body JSON mutation body. @returns {Promise<Object>} Verified server response. */
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-Review-Token":state.catalog.token},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw Error(value.message||"操作失败");return value;}
/** @param {string} text Status visible during local operations. */
function notice(text){$("notice").textContent=text;}
/** @param {HTMLElement} parent Container. @param {string} title Field label. @param {string} value Current text. @param {Function} change Draft update. @param {Object} options Input kind. @returns {HTMLElement} Input. */
function field(parent,title,value,change,options={}){
  /** @type {HTMLElement} Accessible label and field; no user HTML is interpreted. */
  const label=el("label",title),input=el(options.choices?"select":options.multiline?"textarea":"input");
  if(options.choices)for(const [key,text] of options.choices){const option=el("option",text);option.value=key;input.append(option);}
  input.value=value??"";input.oninput=()=>{if(options.invalidate!==false)state.preview=null;change(input.value);};
  if(options.wide)label.className="wide";label.append(input);parent.append(label);return input;
}
/** @param {HTMLElement} parent Container. @param {string} title Collapsible label. @param {Object|string} value Archived data. */
function details(parent,title,value){const box=el("details"),summary=el("summary",title);box.append(summary,el("pre",typeof value==="string"?value:JSON.stringify(value,null,2)));parent.append(box);}
/** @param {Object|null} tree Structured expression. @returns {string} Editable supported notation or JSON for richer expressions. */
function notation(tree){
  if(!tree)return "";if(tree.op==="var")return tree.name;if(tree.op==="nat")return String(tree.value);
  if(tree.op==="call")return tree.symbol+"("+tree.args.map(notation).join(", ")+")";
  /** @type {Object} Fixed infix spellings handled by the server parser. */
  const tokens={add:"+",sub:"-",mul:"*",div:"/",le:"<=",lt:"<",eq:"==",and:"and"};
  if(tokens[tree.op])return "("+notation(tree.left)+" "+tokens[tree.op]+" "+notation(tree.right)+")";
  return JSON.stringify(tree,null,2);
}
/** @returns {Promise<void>} Reload project choices without changing selected history. */
async function catalog(){
  state.catalog=await api("/api/msa/catalog");$("projects").replaceChildren();
  for(const project of state.catalog.projects)button($("projects"),project.name,()=>open(project.id));
  $("model-note").textContent="模型偏好：OpenAI "+state.catalog.model.model+" · "+state.catalog.model.reasoning_effort+
    "。当前未启用外部调用，先完成 MSA 与本地检查；自动语义抽取需配置材料范围和费用上限。";
}
/** @param {string} project Stable project ID. @param {string|null} revision Historical version. @returns {Promise<void>} Displayed exact revision. */
async function open(project,revision=null){
  state.project=await api("/api/msa/project?id="+project+(revision?"&revision="+revision:""));
  state.draft=structuredClone(state.project.document);state.preview=null;
  $("result").hidden=true;$("review").hidden=true;state.freeze=null;state.result=null;
  history.replaceState(null,"","/msa?project="+project+(revision?"&revision="+revision:""));
  render();notice((state.catalog.testing?"验收数据 · ":"")+"已打开修订 "+state.project.revision.slice(0,12)+"；核对与证明状态分别记录。");
  await historyPanel();await paper();
}
/** @returns {void} Render editable semantic content and explicit review choices. */
function render(){
  /** @type {HTMLElement} Main input surface, recreated only after explicit structural operations. */
  const root=$("editor");root.replaceChildren();root.append(el("h2",state.draft.title));
  root.append(el("p","所有条件均由你确认。修改数学内容后，相关目标需要重新核对。"));
  if(state.project.revision!==state.project.head)root.append(el("p","正在查看历史修订；保存新修改前请打开最新版本。"));
  const grid=el("div");grid.className="grid";root.append(grid);
  field(grid,"标题",state.draft.title,value=>state.draft.title=value);
  field(grid,"领域能力",state.draft.scope.adapter,value=>state.draft.scope.adapter=value,{choices:[["unselected","暂未选择"],...Object.entries(state.catalog.capabilities).map(([key,value])=>[key,value.title])]});
  field(grid,"时间域",state.draft.scope.time,value=>state.draft.scope.time=value,{choices:[["unspecified","暂未确定"],["integer_ticks","整数时间"],["continuous","连续时间（当前未适配）"]]});
  field(grid,"证明路线",state.draft.proof_mode,value=>state.draft.proof_mode=value,{choices:[["independent","独立构造"],["library_reuse","允许库定理复用"]]});
  field(grid,"原始 MSA 描述",state.draft.description,value=>state.draft.description=value,{multiline:true,wide:true});
  root.append(el("h3","变量与单位"));
  for(const symbol of state.draft.symbols)entry(root,symbol,true);
  button(root,"＋ 添加变量",()=>{state.draft.symbols.push({key:"variable_"+state.draft.symbols.length,sort:"Nat",unit:"",description:"",sources:[],decision:"pending"});render();});
  root.append(el("h3","模型条件 · 分析方法 · 候选目标"));
  for(const item of state.draft.items)entry(root,item,false);
  const row=el("div");row.className="row";root.append(row);
  for(const [category,title,role] of [["model","模型条件","model_definition"],["analysis","分析定义","analysis_definition"],["goal","目标","guarantee_statement"]])
    button(row,"＋ "+title,()=>{state.draft.items.push({key:category+"_"+state.draft.items.length,category,title,description:"",parameters:[],result:category==="analysis"?"Nat":"Prop",expression:null,material_role:role,sources:[],decision:"pending"});render();});
  const targets=el("div");targets.id="goal-controls";root.append(targets);renderTargets();
  const actions=el("div");actions.className="row";root.append(actions);
  button(actions,"预览修订与影响",preview);
  const download=el("a","导出当前已保存修订");download.href="/api/msa/export?id="+state.project.id+"&revision="+state.project.revision;actions.append(download);
  details(root,"当前保存版本的冻结阻碍",state.project.blockers);
}
/** Refresh target choices after renaming without interrupting the active text field. */
function renderTargets(){
  /** @type {HTMLElement|null} Dedicated target area, absent during initial form construction. */
  const root=$("goal-controls");if(!root)return;root.replaceChildren();
  root.append(el("h3","选择本轮目标"));
  for(const goal of state.draft.items.filter(item=>item.category==="goal")){
    const label=el("label",goal.title+" · "+goal.key),input=el("input");label.className="check";input.type="checkbox";input.checked=state.draft.selected.includes(goal.key);
    input.onchange=()=>{state.draft.selected=input.checked?[...state.draft.selected,goal.key]:state.draft.selected.filter(key=>key!==goal.key);state.preview=null;};label.prepend(input);root.append(label);
  }
  field(root,"主要目标",state.draft.primary,value=>state.draft.primary=value||null,{choices:[["","请选择"],...state.draft.items.filter(item=>item.category==="goal").map(item=>[item.key,item.title])]});
  /** @type {HTMLSelectElement} Source targets follow the current draft identities. */
  const select=$("source-target"),selected=select.value;select.replaceChildren();
  for(const item of [...state.draft.symbols,...state.draft.items]){
    const option=el("option",item.key);option.value=item.key;select.append(option);
  }
  if([...select.options].some(option=>option.value===selected))select.value=selected;
}
/** @param {Object} item Renamed entity. @param {string} value New stable key. */
function rename(item,value){
  /** @type {string} Previous key used to preserve the user's explicit goal selection. */
  const previous=item.key;item.key=value;
  state.draft.selected=state.draft.selected.map(key=>key===previous?value:key);
  if(state.draft.primary===previous)state.draft.primary=value;
  renderTargets();
}
/** @param {HTMLElement} parent Container. @param {Object} item Mutable draft entity. @param {boolean} symbol Whether this is a variable. */
function entry(parent,item,symbol){
  /** @type {HTMLElement} Entity card and its accessible form fields. */
  const card=el("article"),grid=el("div");card.className="entry";grid.className="grid";card.append(el("h3",symbol?"变量 "+item.key:item.title),grid);parent.append(card);
  field(grid,"身份（英文小写）",item.key,value=>rename(item,value));
  if(symbol){
    field(grid,"类型",item.sort,value=>item.sort=value);field(grid,"单位",item.unit,value=>item.unit=value);
  }else{
    field(grid,"标题",item.title,value=>{item.title=value;renderTargets();});
    field(grid,"类别",item.category,value=>{item.category=value;renderTargets();},{choices:[["model","模型条件"],["analysis","分析定义"],["goal","目标"]]});
    field(grid,"显式参数（例 own:Nat,other:Nat）",item.parameters.map(p=>p.join(":")).join(","),value=>item.parameters=value.trim()?value.split(",").map(p=>p.trim().split(":").map(s=>s.trim())):[]);
    field(grid,"结果类型",item.result,value=>item.result=value,{choices:[["Nat","Nat"],["Prop","Prop"]]});
    field(grid,"材料角色",item.material_role,value=>item.material_role=value,{choices:[["model_definition","模型定义"],["analysis_definition","分析方法"],["guarantee_statement","保证声明"],["background","背景"],["author_proof","作者证明"],["scope_limit","范围限制"]]});
    /** @type {HTMLTextAreaElement} Expression editor holds text until the user requests a preview. */
    const expression=field(grid,"数学表达式（复杂表达式可填写 JSON）",item._text??notation(item.expression),value=>item._text=value,{multiline:true,wide:true});
    expression.placeholder="total_budget(c, interference) <= deadline";
  }
  field(grid,"说明",item.description,value=>item.description=value,{multiline:true,wide:true});
  /** @type {Object|undefined} Existing hand-written origin; PDF and derived origins remain separately retained. */
  let manual=item.sources.find(source=>source.kind==="manual");
  const setSource=(key,value)=>{if(!manual){manual={kind:"manual",author:"",note:""};item.sources.push(manual);}manual[key]=value;};
  field(grid,"手工来源作者",manual?.author||"",value=>setSource("author",value));
  field(grid,"手工来源说明",manual?.note||"",value=>setSource("note",value),{multiline:true});
  field(grid,"核对状态",item.decision,value=>item.decision=value,{choices:[["pending","待核对"],["confirmed","已核对"],["excluded","明确排除"]]});
  details(card,"全部来源与定位",item.sources);
}
/** @returns {Promise<Object>} Draft with editor text converted into typed-IR input structures. */
async function documentInput(){
  /** @type {Object} Copy keeps transient editor fields out of the persisted schema. */
  const draft=structuredClone(state.draft);
  for(const item of draft.items){if("_text" in item){const text=item._text.trim();item.expression=!text?null:text.startsWith("{")?JSON.parse(text):(await api("/api/msa/expression",{source:text})).expression;delete item._text;}}
  return draft;
}
/** @returns {Promise<void>} Show exact proposed edits before any new revision is committed. */
async function preview(){
  const draft=await documentInput();
  state.preview=await api("/api/msa/preview",{project:state.project.id,expected:state.project.revision,document:draft});
  state.draft=draft;
  const root=$("review");root.hidden=false;root.replaceChildren(el("h2","修订预览"));
  root.append(el("p",state.preview.mathematics_changed?"数学内容发生变化，相关核对状态将按下方结果更新。":"结构化数学内容未变；来源与文字修订仍单独保留。"));
  details(root,"具体差异",state.preview.changes);details(root,"保存后的核对阻碍",state.preview.blockers);
  const grid=el("div");grid.className="grid";root.append(grid);
  /** @type {Object} Human attribution attached to this exact preview. */
  const review={actor:"local user",reason:"核对本次 MSA 修订。"};
  field(grid,"核对人",review.actor,value=>review.actor=value,{invalidate:false});field(grid,"修订说明",review.reason,value=>review.reason=value,{invalidate:false});
  button(root,"采用预览并保存修订",async()=>{
    if(!state.preview)throw Error("内容已变化，请重新预览。");
    const saved=await api("/api/msa/commit",{project:state.project.id,expected:state.project.revision,document:state.draft,preview:state.preview.token,...review});
    root.hidden=true;await catalog();await open(saved.id);notice("修订已保存，原始版本仍可查看。");
  });
  notice("预览已生成，尚未写入新修订。");
}
/** @returns {Promise<void>} Display source history and frozen result choices. */
async function historyPanel(){
  const root=$("history");root.replaceChildren(el("h3","修订版本"));
  for(const revision of state.project.history)button(root,"v"+revision.generation+" · "+revision.id.slice(0,8),()=>open(state.project.id,revision.id));
  const panel=$("runs");panel.hidden=false;panel.replaceChildren(el("h2","冻结与检查"));
  panel.append(el("p","冻结只表示语义核对完成。映射生成精确目标；证明检查另行产生证据。"));
  button(panel,"冻结当前已保存修订",async()=>{
    const frozen=await api("/api/msa/freeze",{project:state.project.id,expected:state.project.revision,actor:"local user",reason:"确认已保存的模型、方法、目标及来源。"});
    await open(state.project.id);await frozenPanel(frozen.id);notice("语义上下文已冻结，尚不代表目标已证明。");
  }).disabled=state.project.blockers.length>0||state.project.revision!==state.project.head;
  for(const frozen of state.project.freezes)button(panel,"冻结 "+frozen.id.slice(0,12)+" · 修订 "+frozen.revision.slice(0,8),()=>frozenPanel(frozen.id));
}
/** @param {string} freeze Exact frozen context ID. @returns {Promise<void>} Pinned context and results. */
async function frozenPanel(freeze){
  state.freeze=freeze;
  const root=$("result");root.hidden=false;root.replaceChildren(el("h2","冻结上下文 "+freeze.slice(0,12)));
  const link=el("a","原始冻结记录");link.href="/api/msa/frozen?id="+freeze;link.target="_blank";root.append(link);
  button(root,"映射到 Analysis IR",async()=>{notice("正在映射结构化数学内容…");const mapped=await api("/api/msa/map",{freeze});await showResult(mapped.id);notice("映射已完成；所选目标仍需证明检查。");});
  for(const result of await api("/api/msa/results?freeze="+freeze))button(root,(result.kind==="mapping"?"映射":"证明")+" "+result.id.slice(0,12),()=>showResult(result.id));
}
/** @param {string} id Exact archived mapping or proof ID. @returns {Promise<void>} Rendered immutable receipt. */
async function showResult(id){
  state.result=await api("/api/msa/result?id="+id);
  /** @type {Object} Evidence remains pinned even when the editor has a newer draft. */
  const record=state.result,root=$("result");root.hidden=false;root.replaceChildren(el("h2",(record.kind==="mapping"?"映射":"证明")+"记录"));
  root.append(el("p","状态："+record.status),el("p","绑定冻结："+record.freeze),el("p","记录："+id));
  button(root,"返回该冻结的全部记录",()=>frozenPanel(record.freeze));
  const original=el("a","打开原始结果 JSON");original.href="/api/msa/result?id="+id;original.target="_blank";root.append(original);
  if(record.kind==="mapping"){
    root.append(el("p","能力："+(record.capability?.title||"未适配")+" · 证明路线："+record.proof_mode));
    details(root,"来源与修订对应",record.bindings);details(root,"共享前提",record.premises);details(root,"未完成的映射义务",record.gaps);
    for(const goal of record.goals)details(root,goal.key+" · "+goal.status+" · "+goal.proof_status,goal.rocq||goal);
    details(root,"生成的定义",record.source);
    /** @type {Object} Explicit small check budget; each selected goal consumes at most one attempt. */
    const budget={checks:1};
    field(root,"本次检查次数上限（1–8）","1",value=>budget.checks=Number(value));
    button(root,"运行真实 Rocq 检查",async()=>{notice("正在执行 Rocq 精确类型、内核、假设与依赖检查；Prosa 首次检查可能需要数分钟…");
      const proof=await api("/api/msa/prove",{mapping:id,max_checks:budget.checks});await showResult(proof.id);
      notice(proof.status==="proved"?"所选检查目标已通过；结果仅覆盖此处列出的前提与目标。":"本轮已结束，未完成义务与诊断已保存。");
    }).disabled=record.status==="blocked";
  }else{
    root.append(el("p","路线："+record.route+" · 实际检查 "+record.usage.checks+"/"+record.budget.checks+" · 模型调用 "+record.usage.model_calls));
    if(record.error)details(root,"环境或映射诊断",record.error);
    for(const goal of record.goals){
      root.append(el("h3",goal.key+" · "+(goal.status==="proved"?"已证明":"仍开放")));
      details(root,"精确义务与使用资源",{obligation:goal.obligation,reason:goal.reason,message:goal.message,reused_resources:goal.reused_resources});
      if(goal.evidence){const links=el("div");links.className="links";root.append(links);
        for(const [name,digest] of Object.entries(goal.evidence.files)){if(name.startsWith("vo/"))continue;
          const link=el("a",name);link.href="/api/msa/artifact?result="+id+"&digest="+digest;link.target="_blank";links.append(link);}
      }
    }
    details(root,"冻结的检查环境与依赖",record.environment);details(root,"本轮能力边界",record.limitations);
  }
}
/** @returns {Promise<void>} Bind the original PDF, if present, without adding model assumptions. */
async function paper(){
  $("paper").hidden=!state.project.papers.length;if($("paper").hidden)return;
  const select=$("source-target");select.replaceChildren();
  for(const entry of [...state.draft.symbols,...state.draft.items]){const option=el("option",entry.key);option.value=entry.key;select.append(option);}
  await loadPage();
}
/** @returns {Promise<void>} Display exact extracted text and original PDF pixels together. */
async function loadPage(){
  const extraction=state.project.papers[0].extraction,page=Number($("page-number").value);
  const result=await api("/api/page?extraction="+extraction+"&page="+page);
  $("page-number").max=result.count;$("page-text").value=result.text;
  $("page-issues").textContent=result.issues?.map(issue=>issue.code+": "+issue.message).join("\n")||"";$("page-image").src="/api/image?extraction="+extraction+"&page="+page;
}
/** @returns {Promise<void>} Attach an exact code-point source anchor to a draft entity. */
async function attachSource(){
  const area=$("page-text"),extraction=state.project.papers[0].extraction,page=Number($("page-number").value);
  const start=Array.from(area.value.slice(0,area.selectionStart)).length,end=Array.from(area.value.slice(0,area.selectionEnd)).length;
  if(start===end)throw Error("请先选择原文中的文字。");
  const entry=[...state.draft.symbols,...state.draft.items].find(item=>item.key===$("source-target").value);
  if(!entry)throw Error("请先添加条目，再重新打开项目以选择引用目标。");
  const located=await api("/api/reference?extraction="+extraction+"&page="+page+"&start="+start+"&end="+end);
  entry.sources.push({kind:"pdf",anchor:located.anchor});entry.decision="pending";state.preview=null;render();notice("来源已加入草稿，请预览并保存修订。");
}
/** @param {Object|null} document Imported or example MSA. @returns {Promise<void>} New unreviewed workspace. */
async function create(document=null){
  const result=await api("/api/msa/create",{name:document?.title||$("new-name").value,document,actor:"local user"});await catalog();await open(result.id);
}
$("create").onclick=()=>perform(()=>create());
$("budget-example").onclick=()=>perform(async()=>create(await api("/api/msa/example?name=execution-budget")));
$("prosa-example").onclick=()=>perform(async()=>create(await api("/api/msa/example?name=prosa-ceil")));
$("json-file").onchange=event=>perform(async()=>{const file=event.target.files[0];if(file)await create(JSON.parse(await file.text()));event.target.value="";});
$("pdf-file").onchange=event=>perform(async()=>{const file=event.target.files[0];if(!file)return;notice("正在导入 PDF 文字与版面定位…");
  const response=await fetch("/api/msa/pdf",{method:"POST",headers:{"Content-Type":"application/pdf","X-Review-Token":state.catalog.token,"X-Filename":encodeURIComponent(file.name)},body:file});
  const result=await response.json();if(!response.ok)throw Error(result.message);await catalog();await open(result.id);event.target.value="";
  notice("PDF 已导入；可核对原文并填写 MSA。当前尚未运行自动语义抽取。");
});
$("page-load").onclick=()=>perform(loadPage);$("source-add").onclick=()=>perform(attachSource);
perform(async()=>{await catalog();const query=new URLSearchParams(location.search);if(query.has("project"))await open(query.get("project"),query.get("revision"));else notice((state.catalog.testing?"验收目录 · ":"")+"可新建 MSA、导入 JSON 或导入 PDF。");});
