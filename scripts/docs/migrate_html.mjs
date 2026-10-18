#!/usr/bin/env node
/** One-time, source-bound Markdown to HTML migration. No guest/runtime dependency.
 * Usage: node scripts/docs/migrate_html.mjs /absolute/path/to/marked/lib/marked.esm.js
 * Inputs are inventoried tracked Markdown; immutable exceptions are never rewritten.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';

const root = process.cwd();
const markedPath = process.argv[2];
if (fs.existsSync('docs/document-map.json')) throw Error('One-time migration already applied; use an isolated original-source checkout for reproduction');
if (!markedPath || !path.isAbsolute(markedPath)) throw Error('Explicit absolute marked module required');
if (JSON.parse(fs.readFileSync(path.resolve(path.dirname(markedPath), '../package.json'))).version !== '17.0.5') throw Error('Pinned marked/17.0.5 required');
const {marked} = await import(pathToFileURL(markedPath));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const files = execFileSync('git', ['ls-files', '-z', '*.md', '*.MD'], {encoding:'utf8'}).split('\0').filter(Boolean);
const exceptions = {
  'AGENTS.md': 'Filename-sensitive agent discovery hook; narrative moves to docs/contributor-guide.html.',
  '.github/pull_request_template.md': 'Filename-sensitive GitHub template hook; guidance moves to docs/pull-request-guidance.html.',
  'docs/evidence/history/003-kernel-isolated-services-pre-final.md': 'Immutable historical evidence: retain exact original bytes and path.'
};
const special = {
  'AGENTS.md': 'docs/contributor-guide.html',
  '.github/pull_request_template.md': 'docs/pull-request-guidance.html',
  'README.md': 'docs/overview.html',
  'conformance/README.md': 'conformance/conformance-overview.html',
  'docs/evidence/README.md': 'docs/evidence/evidence-overview.html',
  'sim/README.md': 'sim/simulator-overview.html',
  'sim/host/README.md': 'sim/host/host-model-overview.html',
  'tooling/silicon/README.md': 'tooling/silicon/silicon-tooling-overview.html'
};
const mapping = Object.fromEntries(files.filter(f=>!f.startsWith('docs/evidence/history/')).map(f=>[f,special[f]||f.replace(/\.md$/i,'.html')]));
const inventory = [];
const slug = value => value.toLowerCase().replace(/<[^>]+>/g,'').replace(/&[^;]+;/g,'').replace(/[^\p{L}\p{N}\p{M}_\s-]/gu,'').trim().replace(/\s/g,'-');
function destination(href, original, target) {
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)) return href; // Pinned remote/history URLs are literal.
  const match = href.match(/^([^?#]*)(.*)$/), pathname = match[1], suffix = match[2];
  if (!pathname) return href;
  const local = path.posix.normalize(path.posix.join(path.posix.dirname(original), decodeURI(pathname)));
  const mapped = mapping[local] || local;
  return path.posix.relative(path.posix.dirname(target),mapped) + suffix;
}
for (const original of files) {
  const bytes = fs.readFileSync(original), text = bytes.toString('utf8');
  const target = mapping[original];
  if (!target) {inventory.push({original, original_sha256:sha(bytes),bytes:bytes.length,exception:exceptions[original]}); continue;}
  // Unwrap presentation delimiters only. Content before, inside and after each
  // envelope is parsed; do not regex-delete comment contents.
  let source = text.replace(/^\s*<!--\s*$/gm,'').replace(/^\s*-->\s*$/gm,'');
  const seen = new Map();
  const renderer = new marked.Renderer();
  renderer.heading = function(token) {
    const label = this.parser.parseInline(token.tokens), base=slug(token.text);
    const count=seen.get(base)||0;seen.set(base,count+1);
    return `<h${token.depth} id="${base}${count?'-'+count:''}">${label}</h${token.depth}>\n`;
  };
  renderer.link = function(token) {
    const href = destination(token.href,original,target).replaceAll('&','&amp;').replaceAll('"','&quot;');
    return `<a href="${href}">${this.parser.parseInline(token.tokens)}</a>`;
  };
  renderer.image = function(token) {
    const href=destination(token.href,original,target).replaceAll('&','&amp;').replaceAll('"','&quot;');
    return `<img src="${href}" alt="${token.text.replaceAll('&','&amp;').replaceAll('"','&quot;')}">`;
  };
  const body=marked.parse(source,{gfm:true,renderer});
  const title=(source.match(/^#\s+(.+)$/m)||[])[1]||path.posix.basename(target,'.html');
  const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const style=path.posix.relative(path.posix.dirname(target),'docs/documentation.css');
  const overview=path.posix.relative(path.posix.dirname(target),'docs/overview.html');
  const html=`<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>${escape(title)}</title>\n<link rel="stylesheet" href="${style}">\n</head>\n<body>\n<nav aria-label="Documentation"><a href="${overview}">Lemma documentation</a></nav>\n<main>\n${body}</main>\n</body>\n</html>\n`;
  fs.mkdirSync(path.posix.dirname(target),{recursive:true});fs.writeFileSync(target,html);
  inventory.push({original,current:target,original_sha256:sha(bytes),original_bytes:bytes.length,converted_sha256:sha(html)});
  if (!exceptions[original])fs.unlinkSync(original);
}
fs.writeFileSync('AGENTS.md','<!-- Read docs/contributor-guide.html in full before changing this repository. It is the canonical contributor and agent instruction source, including historical boundaries and current task precedence. Read docs/plan/CURRENT.html and the assigned task checkpoint as well. -->\n');
fs.writeFileSync('.github/pull_request_template.md','<!-- Follow docs/pull-request-guidance.html. Report the implemented scope, trust boundaries, actual evidence and remaining limits. -->\n');
const moduleBytes=fs.readFileSync(markedPath);
fs.writeFileSync('docs/document-map.json',JSON.stringify({schema:'lemma-document-map/v1',scope:'Current navigation map; original source hashes are conversion provenance, never reused evidence receipts.',converted_sha256_scope:'Initial mechanical renderer output before subsequent maintained edits; current files use their actual Git/consumed-input identities. This field is not a current-file validation receipt.',converter:'scripts/docs/migrate_html.mjs',parser:{name:'marked',version:'17.0.5',module_sha256:sha(moduleBytes)},source_base:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),source_override:['docs/plan/006-session-state.md includes preserved original-checkout append-only updates supplied at assignment start'],exceptions,documents:inventory},null,2)+'\n');
console.log(JSON.stringify({tracked_markdown:files.length,converted:inventory.filter(x=>x.current).length,exceptions:Object.keys(exceptions)}));
