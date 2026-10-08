/* 排障用：生成一个「去掉启动动画与主界面」的测试页，用来隔离是哪一块把 headless 浏览器搞崩的。
   用法: node tools/_mk_test_page.js [boot|home|both]
*/
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'site');

const which = process.argv[2] || 'both';
let h = fs.readFileSync(path.join(SITE, 'index.html'), 'utf8');

function cut(html, startMark, endMark) {
  const a = html.indexOf(startMark);
  if (a < 0) return html;
  const b = html.indexOf(endMark, a);
  if (b < 0) return html;
  return html.slice(0, a) + html.slice(b);
}

if (which === 'bare' || which === 'bare-nosvg' || which === 'bare-noboot') {
  h = h.replace('<link rel="stylesheet" href="style.css">', '');
  h = h.replace('<script src="app.js"></script>', '');
  h = h.replace('<script src="data.js"></script>', '');
  if (which === 'bare-nosvg') {
    const a = h.indexOf('<svg viewBox="0 0 120 132"');
    const b = h.indexOf('</svg>', a);
    if (a >= 0 && b > a) h = h.slice(0, a) + h.slice(b + 6);
  }
  if (which === 'bare-noboot') {
    h = cut(h, '<div class="boot" id="boot">', '<!-- ── 主界面');
  }
  fs.writeFileSync(path.join(SITE, '_test.html'), h);
  console.log(`已生成 site/_test.html（${which}）`);
  process.exit(0);
}
if (which === 'nojs') {
  h = h.replace('<script src="app.js"></script>', '');
  fs.writeFileSync(path.join(SITE, '_test.html'), h);
  console.log('已生成 site/_test.html（去掉了 app.js）');
  process.exit(0);
}
if (which === 'nocss') {
  h = h.replace('<link rel="stylesheet" href="style.css">', '');
  h = h.replace('<script src="app.js"></script>', '');
  fs.writeFileSync(path.join(SITE, '_test.html'), h);
  console.log('已生成 site/_test.html（去掉了 style.css 与 app.js）');
  process.exit(0);
}

if (which === 'boot' || which === 'both') {
  h = cut(h, '<div class="boot" id="boot">', '<!-- ── 主界面');
}
if (which === 'home' || which === 'both') {
  h = cut(h, '<div class="home" id="home">', '<!-- ── 背景层');
}
// 同时把 app.js 里的启动流程换成直接渲染总览（免得等 boot 元素）
fs.writeFileSync(path.join(SITE, '_test.html'), h);
console.log(`已生成 site/_test.html（去掉: ${which}）`);
console.log('  boot 还在:', h.includes('id="boot"'), '| home 还在:', h.includes('id="home"'));
