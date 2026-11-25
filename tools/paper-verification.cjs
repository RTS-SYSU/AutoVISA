/** Check a reviewed correspondence between a published PDF and a Rocq certificate. */
const {execFile} = require('node:child_process');
const {createHash} = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {promisify} = require('node:util');

const run = promisify(execFile);
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const pdfHash = '1f44ec4906fb5ffa8ccd9bfd5c24adf7bd140a83b84cd2587263d1ee28d9fb31';
const sourceDirectory = path.resolve(__dirname, '../proofs/papers/poet-2022');
const modules = ['task_set', 'tsk02', 'PaperClaim'];
const publishedCertificate = {
  'task_set.v':'44d3c87956805290dcaf56e28a32dcb03f7bc4b16f99e9d1c23a250eb4a83ff4',
  'tsk02.v':'3baad2aef3d4e05619ca594dd025637c57ef2021ae438dcdcae23d723c6e7a7f',
};
const claim = {
  title: 'Foundational Response-Time Analysis as Explainable Evidence of Timeliness',
  doi: '10.4230/LIPIcs.ECRTS.2022.19',
  page: 11,
  locator: 'Listing 2, lines 18–29 and 143–173',
  statement: 'Task 2 has a response-time bound of 60 ms and a deadline of 100 ms.',
  scope: 'Fully preemptive fixed-priority scheduling on one ideal processor, with the two tasks in Listing 1 and the arrival-sequence hypotheses in Listing 2.',
  method: 'Replay of the authors’ POET certificate, with a separate typed Rocq claim fixed to task 2 and the published numbers.',
  theorem: 'PaperClaim.listing_2_task_2_meets_deadline',
};

let inFlight;

async function replay() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'autovisa-paper-'));
  const steps = [];
  const sources = {};
  const local = process.platform === 'win32' && process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, 'AutoVISA') : null;
  const nativeBin = local && path.join(local, 'Rocq-Platform-9.0', 'bin');
  const nativeProsa = local && path.join(local, 'Prosa-0.6');
  const binaries = process.env.AUTOVISA_PAPER_ROCQ_BIN ||
    (nativeBin && await fs.access(path.join(nativeBin, 'rocq.exe')).then(() => nativeBin, () => null));
  const prosa = process.env.AUTOVISA_PAPER_PROSA_ROOT ||
    (nativeProsa && await fs.access(nativeProsa).then(() => nativeProsa, () => null));
  const loadPath = prosa ? ['-R', path.resolve(prosa), 'prosa'] : [];
  const env = {...process.env};
  for (const key of ['COQPATH', 'ROCQPATH', 'COQFLAGS', 'ROCQFLAGS']) delete env[key];
  if (binaries) {
    env.PATH = path.resolve(binaries) + path.delimiter + env.PATH;
    if (process.platform === 'win32') {
      const packages = path.resolve(binaries, '../lib');
      env.ROCQLIB ||= path.join(packages, 'coq');
      env.OCAMLPATH ||= packages;
    }
  }

  async function check(label, program, args) {
    const exe = binaries ? path.resolve(binaries, program + (process.platform === 'win32' ? '.exe' : '')) : program;
    try {
      const {stdout, stderr} = await run(exe, args, {cwd:dir, env, timeout:300000, maxBuffer:32 * 1024 * 1024, windowsHide:true});
      const output = stdout + stderr;
      steps.push({label, ok:true, output:output.trim().slice(-10000)});
      return output;
    } catch (error) {
      const output = (error.stdout || '') + (error.stderr || '');
      steps.push({label, ok:false, output:(output || error.message).trim().slice(-10000)});
      throw new Error(label + ' failed. See the checker log.');
    }
  }

  try {
    for (const name of modules) {
      const file = name + '.v';
      const bytes = await fs.readFile(path.join(sourceDirectory, file));
      sources[file] = {sha256:sha256(bytes), text:bytes.toString('utf8')};
      if (publishedCertificate[file] && sources[file].sha256 !== publishedCertificate[file]) {
        throw new Error('The reviewed POET certificate source changed: ' + file);
      }
      await fs.writeFile(path.join(dir, file), bytes);
    }
    const version = await check('Rocq version', 'rocq', ['--version']);
    if (!/version 9\.0\./i.test(version)) throw new Error('This certificate uses Rocq 9.0 and Prosa 0.6.');
    let claimOutput;
    for (const name of modules) {
      claimOutput = await check('Compile ' + name, 'rocq', [
        'compile', '-q', '-w', '-notation-incompatible-prefix,-notation-overridden', ...loadPath, name + '.v',
      ]);
    }
    const closed = [...claimOutput.matchAll(/^Closed under the global context\s*$/gm)].length;
    if (closed !== 2) throw new Error('The published claim or the numeric deadline uses global assumptions.');
    steps.push({label:'Audit assumptions of both exported declarations', ok:true, output:'Both declarations are closed under the global context.'});
    await check('Replay proof and imported dependencies', 'rocqchk', ['-silent', '-o', ...loadPath, 'PaperClaim']);
    return {status:'verified', checkedAt:new Date().toISOString(), claim, pdfHash, sources, steps};
  } catch (error) {
    return {status:'error', claim, pdfHash, steps, message:error.message};
  } finally {
    await fs.rm(dir, {recursive:true, force:true});
  }
}

async function verifyPaper(bytes) {
  const digest = sha256(bytes);
  if (digest !== pdfHash) return {status:'unsupported', pdfHash:digest};
  if (!inFlight) inFlight = replay().finally(() => { inFlight = undefined; });
  return inFlight;
}

async function servePaperVerification(request, response, port) {
  const reply = (status, body) => {
    response.writeHead(status, {'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store'});
    response.end(JSON.stringify(body));
  };
  if (request.method !== 'POST' || request.headers['content-type'] !== 'application/pdf' ||
      !['127.0.0.1', 'localhost'].some(host => !request.headers.origin || request.headers.origin === 'http://' + host + ':' + port)) {
    reply(400, {message:'Send a PDF from the local workspace.'});
    return;
  }
  try {
    const parts = [];
    let length = 0;
    for await (const chunk of request) {
      length += chunk.length;
      if (length > 20 * 1024 * 1024) {
        reply(413, {message:'The PDF exceeds the certificate-check size limit.'});
        return;
      }
      parts.push(chunk);
    }
    reply(200, await verifyPaper(Buffer.concat(parts)));
  } catch {
    reply(500, {message:'The local certificate check could not complete.'});
  }
}

if (require.main === module) {
  fs.readFile(process.argv[2]).then(verifyPaper).then(result => {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    process.exitCode = result.status === 'verified' ? 0 : 1;
  }).catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = {servePaperVerification};
