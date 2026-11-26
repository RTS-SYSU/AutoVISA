/** Read a local document as stable page, paragraph or line units.
 * @param {File} file User-selected source. @returns {Promise<Object>} Document with normalized text units.
 */
async function readInputDocument(file){
  /** @type {string} Lowercase filename extension selecting the reader. */
  const ext=file.name.split('.').pop().toLowerCase();
  if(file.size>32*1024*1024)throw Error('Choose a file smaller than 32 MB.');
  let units=[],unit='Line';
  if(ext==='pdf'){
    if(location.protocol==='file:')throw Error('Open the local workspace at http://127.0.0.1:8769/ to read PDFs.');
    const pdfjs=await import('./vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc='./vendor/pdfjs/pdf.worker.min.mjs';
    /** @type {Object} PDF reader with scripted evaluation disabled. */
    const task=pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false,useSystemFonts:true});
    try{
      const pdf=await task.promise;unit='Page';
      for(let i=1;i<=pdf.numPages;i++){
        const page=await pdf.getPage(i),content=await page.getTextContent();
        units.push(content.items.filter(item=>typeof item.str==='string').map(item=>item.str+(item.hasEOL?'\n':' ')).join('').trim());
        page.cleanup();
      }
    }catch(error){throw Error(error.name==='PasswordException'?'Unlock this PDF first.':'Could not read this PDF. Choose a readable digital copy.');}
    finally{await task.destroy();}
  }else if(ext==='docx'){
    unit='Paragraph';
    const archive=await JSZip.loadAsync(file),entry=archive.file('word/document.xml');
    if(!entry)throw Error('This file has no Word document body.');
    const xml=new DOMParser().parseFromString(await entry.async('string'),'application/xml');
    if(xml.getElementsByTagName('parsererror').length)throw Error('The Word document contains unreadable XML.');
    const ns=xml.documentElement.namespaceURI;
    units=Array.from(xml.getElementsByTagNameNS(ns,'p'),paragraph=>Array.from(paragraph.getElementsByTagNameNS(ns,'*')).map(node=>node.localName==='t'?node.textContent:node.localName==='tab'?'\t':node.localName==='br'?'\n':'').join(''));
  }else if(['md','markdown','txt'].includes(ext)){
    const bytes=new Uint8Array(await file.arrayBuffer());
    const encoding=bytes[0]===255&&bytes[1]===254?'utf-16le':bytes[0]===254&&bytes[1]===255?'utf-16be':'utf-8';
    try{units=new TextDecoder(encoding,{fatal:true}).decode(bytes).replace(/\r\n?/g,'\n').split('\n');}
    catch{throw Error('Save the text as UTF-8 and choose it again.');}
  }else throw Error('Choose PDF, Markdown, TXT or DOCX.');
  if(ext!=='pdf'&&!units.some(text=>text.trim()))throw Error('No readable text in this document.');
  return {id:crypto.randomUUID(),name:file.name,units,unit};
}

/** Crop the rendered page at its original canvas resolution. Box coordinates are normalized. */
function cropPdfCanvas(canvas,box){
  const left=Math.floor(box.x*canvas.width),top=Math.floor(box.y*canvas.height);
  const right=Math.min(canvas.width,Math.ceil((box.x+box.width)*canvas.width));
  const bottom=Math.min(canvas.height,Math.ceil((box.y+box.height)*canvas.height));
  const image=document.createElement('canvas');
  image.width=right-left;
  image.height=bottom-top;
  image.getContext('2d').drawImage(canvas,left,top,image.width,image.height,0,0,image.width,image.height);
  return image.toDataURL('image/png');
}

/** @returns {Promise<IDBDatabase>} Browser store for original PDF copies. */
function openPdfStore() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('autovisa-original-documents', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('pdfs');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** @param {string} id Document ID. @param {Blob} [original] New original to save.
 * @param {string} project Project owner. @returns {Promise<Blob|undefined>} Saved original on reads. */
async function originalPdf(id, original, project) {
  const db = await openPdfStore();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction('pdfs', original ? 'readwrite' : 'readonly');
      const store = transaction.objectStore('pdfs');
      const key = project + '/' + id;
      let request = original ? store.put(original, key) : store.get(key);
      if (!original) request.onsuccess = () => {
        if (!request.result) request = store.get(id); // Originals imported before ownership was recorded.
      };
      transaction.oncomplete = () => resolve(request.result);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

/** @param {string} project Project whose imported copies are being removed.
 * @param {Set<string>} legacyIds Unshared legacy originals referenced by the workspace. */
async function clearProjectPdfs(project, legacyIds) {
  const db = await openPdfStore();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction('pdfs', 'readwrite');
      const store = tx.objectStore('pdfs');
      store.delete(IDBKeyRange.bound(project+'/', project+'/\uffff'));
      for (const id of legacyIds) store.delete(id);
      tx.oncomplete = resolve;
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

/** Draw the original page, preserving columns, glyph positions and equation layout.
 * @param {HTMLElement} host Connected preview containing a canvas and status region.
 * @param {string} id Imported document identifier.
 * @param {number} number One-based page number.
 * @param {string} project Project that owns this original.
 */
async function drawOriginalPage(host, id, number, project) {
  const status = host.querySelector('[role=status]');
  let task;
  try {
    const original = await originalPdf(id, undefined, project);
    if (!host.isConnected) return;
    if (!original) {
      status.textContent = 'Choose this PDF again to view its original pages. Saved excerpts are available below.';
      return;
    }
    const pdfjs = await import('./vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = './vendor/pdfjs/pdf.worker.min.mjs';
    task = pdfjs.getDocument({data: new Uint8Array(await original.arrayBuffer()), isEvalSupported: false, useSystemFonts: true});
    const pdf = await task.promise;
    const page = await pdf.getPage(number);
    if (!host.isConnected) return;
    const canvas = host.querySelector('canvas');
    const normal = page.getViewport({scale: 1});
    const scale = Math.min(3, 2400 / Math.max(normal.width, normal.height));
    const viewport = page.getViewport({scale});
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
    await page.render({canvas, viewport}).promise;
    if (!host.isConnected) return;
    canvas.hidden = false;
    status.textContent = '';
  } catch {
    status.textContent = 'Original page unavailable. Open the source text below to read the excerpt.';
  } finally { if (task) await task.destroy(); }
}
