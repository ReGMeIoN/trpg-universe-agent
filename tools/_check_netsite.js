/* 前端静态自检：不需要浏览器。
   1) index.html 里定义的 id → app.js 里 $('#x') 引用的 id 是否都存在（防"点不动/白屏"）
   2) CSS 属性名里是否混进了非 ASCII 垃圾字符（粘贴事故）
   3) data.js 里封面/立绘路径指向的文件是否真的存在

   用法: node tools/_check_netsite.js
*/
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'site');
const html = fs.readFileSync(path.join(SITE, 'index.html'), 'utf8');
const js = fs.readFileSync(path.join(SITE, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(SITE, 'style.css'), 'utf8');

let bad = 0;

// 1) id 一致性
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const refs = new Set([...js.matchAll(/\$\('#([A-Za-z0-9_-]+)'\)/g)].map(m => m[1]));
const missing = [...refs].filter(r => !ids.has(r));
console.log(`[1] index.html 定义 ${ids.size} 个 id；app.js 引用 ${refs.size} 个`);
if (missing.length) { bad++; console.log('    ✘ app.js 引用了不存在的 id:', missing.join(', ')); }
else console.log('    ✔ 引用全部存在');

// 2) CSS 里混入非 ASCII 的「属性名」
const cssLines = css.split('\n');
const junk = [];
cssLines.forEach((ln, i) => {
  const m = ln.match(/^\s*([^\s:{};]+)\s*:/);
  if (m && /[^\x00-\x7F]/.test(m[1])) junk.push(`L${i + 1}: ${m[1]}`);
});
console.log(`[2] CSS 检查 ${cssLines.length} 行`);
if (junk.length) { bad++; console.log('    ✘ 属性名里混入非 ASCII:', junk.join(' | ')); }
else console.log('    ✔ 无垃圾字符');

// 3) 资源路径存在性
const dataJs = fs.readFileSync(path.join(SITE, 'data.js'), 'utf8');
const win = {};
new Function('window', dataJs)(win);
const N = win.NET;
const paths = new Set();
Object.values(N.covers || {}).forEach(m => Object.values(m).forEach(p => paths.add(p)));
N.chars.forEach(c => { if (c.avatar) { paths.add(c.avatar.thumb); paths.add(c.avatar.full); } });
const miss = [...paths].filter(p => !fs.existsSync(path.join(SITE, p)));
console.log(`[3] 资源路径 ${paths.size} 个`);
if (miss.length) { bad++; console.log('    ✘ 缺文件:', miss.slice(0, 8).join(', '), miss.length > 8 ? `…共 ${miss.length}` : ''); }
else console.log('    ✔ 全部存在');

console.log(`\n数据：${N.chars.length} 角色 / ${N.rels.length} 关系 / ${N.groups.length} 团 · 封面 ${Object.values(N.covers).reduce((s, m) => s + Object.keys(m).length, 0)} 张`);
console.log(bad ? `\n✘ 有 ${bad} 项问题` : '\n✔ 全部通过');
process.exit(bad ? 1 : 0);
