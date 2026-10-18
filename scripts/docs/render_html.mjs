#!/usr/bin/env node
/** Render a supplied normative Markdown-formatted source without changing its text. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [modulePath, sourcePath, outputPath] = process.argv.slice(2);
if (!modulePath || !path.isAbsolute(modulePath) || !sourcePath || !outputPath) throw Error('Usage: node render_html.mjs ABSOLUTE_MARKED_MODULE SOURCE OUTPUT');
if (JSON.parse(fs.readFileSync(path.resolve(path.dirname(modulePath), '../package.json'))).version !== '17.0.5') throw Error('Pinned marked/17.0.5 required');
const {marked} = await import(pathToFileURL(modulePath));
const source=fs.readFileSync(sourcePath,'utf8');
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const seen=new Map();
const renderer=new marked.Renderer();
renderer.heading=function(token) {
 const label=this.parser.parseInline(token.tokens);
 const base=token.text.toLowerCase().replace(/<[^>]+>/g,'').replace(/&[^;]+;/g,'').replace(/[^\p{L}\p{N}\p{M}_\s-]/gu,'').trim().replace(/\s/g,'-');
 const count=seen.get(base)||0;seen.set(base,count+1);
 return `<h${token.depth} id="${base}${count?'-'+count:''}">${label}</h${token.depth}>\n`;
};
const body=marked.parse(source,{gfm:true,renderer});
const title=(source.match(/^#\s+(.+)$/m)||[])[1]||path.basename(sourcePath);
const style=path.posix.relative(path.posix.dirname(outputPath),'docs/documentation.css');
fs.mkdirSync(path.dirname(outputPath),{recursive:true});
fs.writeFileSync(outputPath,`<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(title)}</title><link rel="stylesheet" href="${style}"></head>\n<body><main>\n${body}</main></body></html>\n`);
console.log(JSON.stringify({source:sourcePath,source_sha256:crypto.createHash('sha256').update(fs.readFileSync(sourcePath)).digest('hex'),output:outputPath,output_sha256:crypto.createHash('sha256').update(fs.readFileSync(outputPath)).digest('hex'),parser:'marked/17.0.5',parser_module_sha256:crypto.createHash('sha256').update(fs.readFileSync(modulePath)).digest('hex')}));
