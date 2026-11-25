/** Source-grounded contribution extraction for the PDF-to-MSA step. */
const fs = require('node:fs');
const path = require('node:path');

/** Stable identity shown with the model in the reviewed snapshot. */
const name = 'extract-paper-contributions';
/** @param {string} id Built-in skill directory. @returns {string} Executable instructions. */
function readSkill(id) { return fs.readFileSync(path.join(__dirname, '../skills', id, 'SKILL.md'), 'utf8').replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, ''); }
const targetSkill = {id:'select-proof-targets',name:'Select proof targets',stage:'extraction',version:1,builtin:true,instructions:readSkill('select-proof-targets')};
const instructions = readSkill(name);
const sections = ['model', 'assumptions', 'analysis', 'goal'];
const citation = {unit:{type:'integer'}, quote:{type:'string'}};
/** @param {object} properties Required fields for a structured model response. */
function record(properties) {
  return {type:'object', properties, required:Object.keys(properties), additionalProperties:false};
}
const targetKinds = ['primary_target','secondary_target'];
const resultKinds = ['model','assumptions','analysis',...targetKinds,'evaluation','example'];
const statements = {type:'array', items:record({...citation, section:{type:'string',enum:resultKinds}, title:{type:'string'}, markdown:{type:'string'}})};
const schema = record({contributions:{type:'array',items:record({...citation,statements})}});

/** @param {string} message Actionable extraction diagnostic. */
function invalid(message) { return Object.assign(Error(message), {status:422}); }

/** @param {object} output Contribution groups returned by the model.
 * @param {string[]} units Numbered original PDF text units.
 * @returns {object} Editable MSA fields with citations into the original text. */
function review(output, units) {
  if (!Array.isArray(output?.contributions)) throw invalid('Invalid paper contribution response.');
  const fields = Object.fromEntries(sections.map(section => [section, []]));
  /** Formal claims stay selectable; only the first primary enters the initial draft. */
  const targets = [], notes = [];
  let offset = 0;
  const offsets = units.map(unit => {const start = offset; offset += unit.length + 1; return start;});
  /** @param {object} source Quote and one-based unit from this response. */
  function locate(source) {
    const text = Number.isInteger(source?.unit) && units[source.unit - 1];
    const quote = source?.quote;
    const start = text && typeof quote === 'string' && quote.trim() ? text.indexOf(quote) : -1;
    if (start < 0 || text.indexOf(quote,start+1) !== -1)
      throw invalid('Could not locate a contribution or statement in the cited PDF text. Retry or select its source passage manually.');
    const absolute = offsets[source.unit - 1] + start;
    return [absolute, absolute + quote.length];
  }
  for (const contribution of output.contributions) {
    const basis = locate(contribution);
    if (!Array.isArray(contribution.statements)) throw invalid('Missing contribution statements.');
    for (const item of contribution.statements) {
      if (!resultKinds.includes(item?.section) || typeof item.markdown !== 'string' || !item.markdown.trim())
        throw invalid('Incomplete contribution statement.');
      const statement = {markdown:item.markdown.trim(),anchor:locate(item),basis};
      if (targetKinds.includes(item.section)) {
        if (!item.title?.trim()) throw invalid('A candidate proof target needs a title.');
        targets.push({...statement,title:item.title.trim(),kind:item.section});
      } else if (item.section==='evaluation' || item.section==='example') {
        notes.push({...statement,kind:item.section});
      } else fields[item.section].push(statement);
    }
  }
  const first = targets.find(item=>item.kind==='primary_target');
  if (first) fields.goal.push(first);
  if (!targets.length && !notes.length && !sections.some(section => fields[section].length))
    throw invalid('No original contribution with supporting evidence was identified. Review the PDF or select passages manually.');
  return {fields,targets,notes};
}
/** Read-only Resources entry backed by the same instructions sent to the model. */
const resource = {id:name, name:'Extract paper contributions', stage:'extraction', version:2, builtin:true, instructions};
module.exports = {name, instructions, schema, review, resource, targetSkill};
