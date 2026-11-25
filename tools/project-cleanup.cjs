/** Delete one workspace's server-side records, including legacy key-bound audit logs. */
const fs = require('node:fs');
const path = require('node:path');
/** In-flight registries owned by the IR, graph, proof, skill and audit services. */
const registries = [];
/** Prevent delayed requests from rebuilding a deleted UUID in this service session. */
const retired = new Set();

/** @param {Map} jobs Records with an immutable project owner.
 * @param {Function} running Whether this job can still publish data. */
function track(jobs, running) {
  registries.push({jobs, running});
}

/** @param {string} project UUID of a workspace about to create an IR snapshot. */
function requireLive(project) {
  if (retired.has(project)) throw Object.assign(Error('This project was deleted.'), {status:410});
}

/** @param {string} project Workspace ID, never a file path.
 * @param {string} root Managed artifacts directory, replaceable by an isolated test fixture.
 * @returns {{deleted:boolean}} Success is idempotent, including after partial cleanup. */
function clearProject(project, root = path.resolve(__dirname, '../artifacts')) {
  if (project !== 'example' && (typeof project !== 'string' || !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(project)))
    throw Object.assign(Error('Choose a saved project.'), {status:400});
  for (const {jobs, running} of registries) {
    if ([...jobs.values()].some(job => job.project === project && running(job)))
      throw Object.assign(Error('This project has a running job. Wait for it to finish and try again.'), {status:409});
  }
  /** IR hashes identify older reviews that predate explicit project ownership. */
  const keys = new Set();
  const owned = [];
  const reviews = [];
  for (const folder of ['analysis-ir','derivation-graphs','local-obligations','argument-reviews']) {
    const dir = path.join(root, folder);
    if (!fs.existsSync(dir)) continue;
    if (fs.lstatSync(dir).isSymbolicLink()) throw Error('Unexpected artifact directory.');
    for (const entry of fs.readdirSync(dir, {withFileTypes:true})) {
      if (!entry.isFile() || !/\.(json|tmp)$/.test(entry.name)) continue;
      const file = path.join(dir, entry.name);
      if (folder === 'argument-reviews') { reviews.push(file); continue; }
      const record = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (record.project !== project) continue;
      if (/^[0-9a-f]{64}$/.test(record.key)) keys.add(record.key);
      owned.push(file);
    }
  }
  // Remove key-only children first so an interrupted cleanup can rediscover ownership on retry.
  for (const file of reviews) {
    const record = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (record.project === project || (!record.project && keys.has(/^([a-f0-9]{64})-v\d+$/.exec(record.id)?.[1])))
      fs.unlinkSync(file);
  }
  for (const file of owned.reverse()) fs.unlinkSync(file);
  for (const {jobs} of registries)
    for (const [id, job] of jobs) if (job.project === project) jobs.delete(id);
  if (project !== 'example') retired.add(project);
  return {deleted:true};
}
module.exports = {clearProject, track, requireLive};
