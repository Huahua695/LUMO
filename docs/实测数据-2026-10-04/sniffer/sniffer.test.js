const fs = require('fs');
const SRC = fs.readFileSync(process.argv[2], 'utf8');

let pass = 0, fail = 0, fails = [];
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; fails.push(name); console.log('  FAIL ' + name + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
}
const tick = async () => { await Promise.resolve(); await Promise.resolve(); };

function makeEl(tag, doc) {
  const e = {
    tagName: String(tag).toUpperCase(), _doc: doc,
    style: {}, children: [], parentNode: null,
    textContent: '', value: '', readOnly: false, id: '',
    _h: {}, _focused: 0, _selected: 0, _shadow: null,
    appendChild(c) { c.parentNode = e; e.children.push(c); return e; },
    removeChild(c) { const i = e.children.indexOf(c); if (i < 0) throw new Error('not child'); e.children.splice(i, 1); c.parentNode = null; return e; },
    addEventListener(t, f) { e._h[t] = f; },
    focus() { e._focused++; },
    select() { e._selected++; },
    attachShadow(o) {
      if (doc && doc._noShadow) throw new Error('attachShadow unsupported');
      const sr = makeEl('#shadow-root', doc); sr._isShadow = true; sr.mode = o && o.mode;
      e._shadow = sr; return sr;
    },
  };
  return e;
}
function walk(n, out) { out.push(n); (n.children || []).concat(n._shadow ? [n._shadow] : []).forEach(c => walk(c, out)); return out; }

const MIX = {
  res: [
    { name: 'https://a.com/master.m3u8?tok=1' },
    { name: 'https://a.com/master.m3u8?tok=1' },
    { name: 'https://a.com/dash.mpd' },
    { name: 'https://a.com/seg-1.m4s' }, { name: 'https://a.com/seg-2.m4s' }, { name: 'https:////seg-3.m4s' },
    { name: 'https://cdn.b.com/clip.mp4?v=2' },
    { name: 'https://cdn.b.com/song.m4a' },
    { name: 'https://a.com/app.css' },
    { name: 'blob:https://www.page.com/0c90a6aa-1111' },
    { name: 'https://weird.com/x"onmouseover=alert(1)<img src=y>.mp4' },
  ],
  dom: [
    { tagName: 'VIDEO', src: 'blob:https://www.page.com/aaaa' },
    { tagName: 'VIDEO', src: 'https://cdn.b.com/clip.mp4?v=2' },
    { tagName: 'AUDIO', src: 'https://cdn.b.com/song.m4a' },
    { tagName: 'SOURCE', src: 'https://a.com/master.m3u8?tok=1' },
    { tagName: 'SOURCE', src: '' },
    { tagName: 'VIDEO', src: 'https://cdn.c.com/stream/noext' },
    { tagName: 'VIDEO', src: 'javascript:alert(1)' },
  ],
  page: 'https://www.page.com/watch/1?qs=2',
};

function build(scenario, opts) {
  opts = opts || {};
  const res = JSON.parse(JSON.stringify(scenario.res));
  const dom = JSON.parse(JSON.stringify(scenario.dom || []));
  const PG = scenario.page;

  const doc = makeEl('#document', null);
  doc._noShadow = !!opts.noShadow;
  doc.documentElement = makeEl('html', doc);
  doc.body = makeEl('body', doc);
  if (opts.appendThrows) doc.documentElement.appendChild = function () { throw new Error('append blocked'); };
  doc.createElement = t => makeEl(t, doc);
  doc.getElementById = id => doc.documentElement.children.filter(c => c.id === id)[0] || null;
  doc.write = () => { throw new Error('document.write must not be called'); };
  doc.querySelectorAll = () => dom.map(d => ({ src: d.src, currentSrc: d.currentSrc, tagName: d.tagName }));

  const opened = [];
  function newPopup() {
    const pd = makeEl('#document', null);
    pd.documentElement = makeEl('html', pd);
    pd.body = makeEl('body', pd);
    pd.createElement = t => makeEl(t, pd);
    pd.write = () => { throw new Error('popup write forbidden'); };
    return pd;
  }
  const clipCalls = [];
  const nav = {};
  if (!opts.noClipboard) {
    nav.clipboard = {
      writeText(t) {
        clipCalls.push(t);
        if (opts.clipReject) return Promise.reject(new Error('NotAllowedError'));
        if (opts.clipThrow) throw new Error('boom');
        return Promise.resolve();
      }
    };
  }
  const sel = { _target: null, _text: '', calls: 0,
    removeAllRanges() { sel._target = null; sel._text = ''; },
    selectAllChildren(e) { sel.calls++; sel._target = e; sel._text = e.textContent; },
    toString() { return sel._text; } };
  const win = {
    _mq: [], getSelection: () => sel,
    matchMedia(q) { win._mq.push(q); return { matches: !!opts.dark, media: q }; },
    open(a, b, c) { const pd = newPopup(); opened.push({ url: a, doc: pd }); return { document: pd }; },
  };
  if (opts.openThrows) win.open = function () { throw new Error('popup blocked'); };
  const loc = { href: PG };
  const perf = { getEntriesByType: t => (t === 'resource' ? res : []) };
  const alerted = [];

  let err = null;
  try {
    new Function('window', 'document', 'performance', 'navigator', 'location', 'matchMedia', 'alert', SRC)
      (win, doc, perf, nav, loc, win.matchMedia, m => alerted.push(m));
  } catch (e) { err = e; }

  const popNodes = opened.reduce((a, o) => a.concat(walk(o.doc.documentElement, []), walk(o.doc.body, [])), []);
  const all = walk(doc.documentElement, []).concat(popNodes);
  return {
    doc, win, err, opened, clipCalls, alerted, all,
    texts: all.filter(n => n.textContent).map(n => n.textContent),
    areas: all.filter(n => n.style.userSelect === 'all'),
    sel,
    copies: all.filter(n => n.style.userSelect === 'all').map(n => n.textContent)
      .concat(all.filter(n => n.tagName === '#shadow-root' ? false : (n.textContent && /^https?:/.test(n.textContent) && n.style.userSelect !== 'all')).map(n => n.textContent)),
    attached: doc.documentElement.children.length > 0,
    shadowUsed: !!doc.documentElement.children[0] && !!doc.documentElement.children[0]._shadow,
  };
}

function pure(v) { return typeof v === 'string' && /^https?:\/\/\S+$/.test(v) && v.indexOf(',') < 0; }
// 载荷必须逐字等于 原URL + '#sgref=' + encodeURIComponent(页面URL)：
// 这一条同时排除标签粘连、HTML 截断、重复、丢参数
const EXPECT = [
 'https://a.com/master.m3u8?tok=1','https://a.com/dash.mpd','https://cdn.b.com/clip.mp4?v=2',
 'https://weird.com/x"onmouseover=alert(1)<img src=y>.mp4','https://cdn.c.com/stream/noext','https://cdn.b.com/song.m4a',
].map(u => u + '#sgref=' + encodeURIComponent(MIX.page)).sort();
function exact(list) { return JSON.stringify(list.slice().sort()) === JSON.stringify(EXPECT); }
function clean(v){return /^https?:\/\//.test(v)&&v.indexOf(',')<0&&v.indexOf(String.fromCharCode(10))<0&&v.indexOf(String.fromCharCode(13))<0;}
function refOf(v) { const i = v.indexOf('#sgref='); return i < 0 ? '' : decodeURIComponent(v.slice(i + 7)); }

async function main() {
console.log('\n=== 场景 1 · 常规混合：覆盖层路径 ===');
let r = build(MIX, {});
ok('脚本无异常', r.err === null, r.err && r.err.message);
ok('未调用 window.open', r.opened.length === 0, r.opened.length);
ok('host 已挂到 documentElement', r.attached);
ok('使用了 shadow root', r.shadowUsed);
ok('全程未用 document.write / innerHTML', !/document\.write|innerHTML/.test(SRC));
ok('条目数 = 6（HLS+DASH+clip.mp4+weird.mp4+song.m4a+noext）', r.areas.length === 6, r.areas.map(a => a.textContent));
ok('每条载荷都无粘连/无换行/无逗号', r.copies.every(clean), r.copies.filter(v => !clean(v)));
ok('载荷集合逐字等于 6 条 原URL+#sgref（最强断言）', exact(r.copies), r.copies.slice().sort());
ok('每条载荷自带来源页 Referer', r.areas.every(a => refOf(a.textContent) === MIX.page), r.areas.map(a => a.textContent));
ok('含双引号/尖括号的 URL 原样保存在 value（非标记拼接）', r.areas.some(a => a.textContent.startsWith('https://weird.com/x"onmouseover=alert(1)<img src=y>.mp4#sgref=')), r.areas.map(a => a.textContent));
ok('清单去重（同 m3u8 只 1 条）', r.areas.filter(a => a.textContent.includes('master.m3u8')).length === 1, r.areas.filter(a => a.textContent.includes('master.m3u8')).length);
ok('跨节去重：同一 URL 不同时出现在清单与视频两节', (() => {
  const s = new Set(r.copies.map(u => u.split('#')[0]));
  return s.size === r.copies.length;
})(), r.copies);
ok('DOM 与资源表的同一 mp4 合并为 1 条', r.areas.filter(a => a.textContent.includes('clip.mp4')).length === 1, r.areas.map(a => a.textContent));
ok('无扩展名的 DOM <video> 仍归入视频', r.areas.some(a => a.textContent.startsWith('https://cdn.c.com/stream/noext')), r.areas.map(a => a.textContent));
ok('javascript: 伪协议绝不进入可复制列表', !r.copies.some(u => /javascript:/i.test(u)), r.copies);
ok('m4s 不进可复制列表', !r.copies.some(a => /\.m4s/.test(a)));
ok('css 不进可复制列表', !r.copies.some(a => /\.css/.test(a)));
ok('计数标题：流媒体清单（2）', r.texts.includes('流媒体清单（2）'), r.texts.filter(t => /^(流媒体清单|视频|音频)（/.test(t)));
ok('计数标题：视频（3）', r.texts.includes('视频（3）'), r.texts.filter(t => /^视频（/.test(t)));
ok('计数标题：音频（1）', r.texts.includes('音频（1）'), r.texts.filter(t => /^音频（/.test(t)));
ok('m4s 提示走"主清单已列出"分支', r.texts.some(t => t.includes('m4s 分片') && t.includes('其主清单已在上方列出')), r.texts.filter(t => t.includes('m4s')));
ok('blob 计数提示为 2', r.texts.some(t => t.includes('2 个 blob: 播放源')), r.texts.filter(t => t.includes('blob')));
ok('来源页 URL 作为文本展示', r.texts.some(t => t === '来源页（Referer）：' + MIX.page));
ok('Cookie 兜底提示存在', r.texts.some(t => t.includes('设置 → Cookie')));
ok('样式全部走 CSSOM 属性赋值（无 style 字符串/setAttribute/<style>）', !/setAttribute\(\s*['"]style|\.style\s*=|<style/.test(SRC));
ok('面板是唯一 fixed 节点，top 16px 且 z-index 顶层', (() => { const p = r.all.filter(n => n.style.position === 'fixed'); return p.length === 1 && String(p[0].style.zIndex) === '2147483647' && p[0].style.top === '16px'; })(), r.all.filter(n => n.style.position === 'fixed').length);
ok('载荷容器是 user-select:all 的普通元素（无 textarea 裁切/焦点描边）', r.areas.length>0 && r.areas.every(a => a.style.userSelect === 'all') && !/textarea/i.test(SRC));
ok('无任何 emoji', !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(SRC));

console.log('\n=== 场景 2 · 复制按钮：clipboard 成功 ===');
r = build(MIX, {});
let btns = r.all.filter(n => n.tagName === 'BUTTON' && n.textContent === '复制');
ok('复制按钮数量与条目一致', btns.length === r.areas.length, btns.length + '/' + r.areas.length);
btns[0]._h.click();
ok('点击调用 clipboard 且载荷逐字等于框内值', r.clipCalls.length === 1 && r.clipCalls[0] === r.areas[0].textContent, r.clipCalls);
ok('点击时已原生全选整段载荷（Ctrl+C 兜底可用）', r.sel.calls >= 1 && r.sel._target === r.areas[0] && r.sel._text === r.areas[0].textContent, r.sel);
await tick();
ok('promise 落定后按钮文字变「已复制」', btns[0].textContent === '已复制', btns[0].textContent);

console.log('\n=== 场景 3 · clipboard 被拒（NotAllowedError） ===');
r = build(MIX, { clipReject: true });
btns = r.all.filter(n => n.tagName === 'BUTTON' && n.textContent === '复制');
let unhanded = false;
process.once('unhandledRejection', () => { unhanded = true; });
btns[0]._h.click();
ok('降级时仍然选中', r.sel.calls >= 1 && r.sel._text === r.areas[0].textContent);
await tick();
ok('rejection 被 then(onRejected) 吃掉，无未处理 rejection', !unhanded);
ok('按钮文字变「已选中」', btns[0].textContent === '已选中', btns[0].textContent);

console.log('\n=== 场景 4 · clipboard 缺失 / 同步抛错 ===');
r = build(MIX, { noClipboard: true });
btns = r.all.filter(n => n.tagName === 'BUTTON' && n.textContent === '复制');
let threw = false; try { btns[0]._h.click(); } catch (e) { threw = true; }
ok('navigator.clipboard 缺失不抛异常', !threw);
ok('缺失时降级为「已选中」', btns[0].textContent === '已选中', btns[0].textContent);
r = build(MIX, { clipThrow: true });
btns = r.all.filter(n => n.tagName === 'BUTTON' && n.textContent === '复制');
threw = false; try { btns[0]._h.click(); } catch (e) { threw = true; }
ok('writeText 同步抛异常被 try 捕获', !threw && btns[0].textContent === '已选中', btns[0].textContent);

console.log('\n=== 场景 5 · attachShadow 不支持 → 光 DOM 内联样式 ===');
r = build(MIX, { noShadow: true });
ok('脚本无异常', r.err === null, r.err && r.err.message);
ok('仍未弹窗', r.opened.length === 0);
ok('host 仍挂上 documentElement', r.attached);
ok('退化为无 shadow 容器', r.shadowUsed === false);
ok('条目与载荷不降级（逐字等于场景 1）', r.areas.length === 6 && exact(r.areas.map(a => a.textContent)), r.areas.length);
ok('样式仍靠内联 CSSOM（不依赖样式表）', r.all.some(n => n.style.position === 'fixed'));

console.log('\n=== 场景 6 · appendChild 也失败 → window.open 纯文本兜底 ===');
r = build(MIX, { appendThrows: true });
ok('脚本无异常', r.err === null, r.err && r.err.message);
ok('兜底调用 window.open 一次', r.opened.length === 1, r.opened.length);
ok('兜底用 about:blank', r.opened[0] && r.opened[0].url === 'about:blank');
ok('兜底载荷 6 条且逐字正确', r.copies.length === 6 && exact(r.copies) && r.copies.every(clean), r.copies);
ok('兜底页含来源页文本', r.texts.some(t => t === '来源页（Referer）：' + MIX.page));
ok('兜底未使用 innerHTML / document.write', !/innerHTML|document\.write/.test(SRC));
r = build(MIX, { appendThrows: true, openThrows: true });
ok('连弹窗也被拦时给 alert 而非静默失败', r.alerted.length === 1 && r.alerted[0].includes('控制台'), r.alerted);

console.log('\n=== 场景 7 · 只有 m4s 无清单（B站形态） ===');
r = build({ res: [{ name: 'https://a.com/1.m4s' }, { name: 'https://a.com/2.m4s' }], dom: [{ tagName: 'VIDEO', src: 'blob:https://a.com/x' }] }, {});
ok('提示"未找到 .mpd 主清单——MSE，嗅探不适用"', r.texts.some(t => t.includes('未找到 .mpd 主清单') && t.includes('嗅探不适用')), r.texts.filter(t => t.includes('m4s')));
ok('无条目', r.areas.length === 0);
ok('三个空节各显示「无」', r.texts.filter(t => t === '无').length === 3, r.texts.filter(t => t === '无').length);
ok('空结果也挂覆盖层（否则用户以为没反应）', r.attached);

console.log('\n=== 场景 8 · 完全没发现媒体 ===');
r = build({ res: [{ name: 'https://a.com/app.js' }], dom: [] }, {});
ok('提示缓冲区上限 250 与"丢弃的是新条目"', r.texts.some(t => t.includes('250 条') && t.includes('溢出时丢弃的是新条目')), r.texts);
ok('提示刷新后播放时立即点击', r.texts.some(t => t.includes('开始播放时立即点击')));
ok('未误报 m4s/blob 提示', !r.texts.some(t => /blob: 播放源|m4s 分片/.test(t)));

console.log('\n=== 场景 9 · 暗色模式 ===');
r = build(MIX, { dark: true });
let pnl = r.all.filter(n => n.style.position === 'fixed')[0];
ok('查询了 prefers-color-scheme:dark', (r.win._mq || []).includes('(prefers-color-scheme:dark)'));
ok('面板底色取暗色', pnl.style.background === '#1a1a1a', pnl.style.background);
ok('暗色下正文色取亮色', pnl.style.color === '#e8e8e8', pnl.style.color);
r = build(MIX, {});
pnl = r.all.filter(n => n.style.position === 'fixed')[0];
ok('亮色下取 #ffffff / #1a1a1a', pnl.style.background === '#ffffff' && pnl.style.color === '#1a1a1a');

console.log('\n=== 场景 10 · URL 自身含 # 时不追加第二个 fragment ===');
r = build({ res: [{ name: 'https://a.com/x.m3u8#t=5' }], dom: [] }, {});
ok('载荷等于原 URL（无 sgref）', r.areas.length === 1 && r.areas[0].textContent === 'https://a.com/x.m3u8#t=5', r.areas.map(a => a.textContent));
ok('仍是纯净 URL', r.areas.every(a => pure(a.textContent)));

console.log('\n=== 场景 11 · 关闭按钮真的移除 host ===');
r = build(MIX, {});
const close = r.all.filter(n => n.tagName === 'BUTTON' && n.textContent === '关闭');
ok('有且仅有一个关闭按钮', close.length === 1, close.length);
ok('host 已挂载', r.doc.documentElement.children.length === 1);
close[0]._h.click();
ok('点击后从 documentElement 移除', r.doc.documentElement.children.length === 0);

console.log('\n=== 场景 12 · mpd-only（DASH 文件形态） ===');
r = build({ res: [{ name: 'https://a.com/manifest.mpd' }], dom: [] }, {});
ok('.mpd 归入流媒体清单且可复制', r.areas.length === 1 && r.areas[0].textContent.indexOf('https://a.com/manifest.mpd#sgref=') === 0, r.areas.map(a => a.textContent));
ok('标签为 DASH', r.texts.includes('DASH'));

console.log('\n=== 场景 13 · 重复点击书签不留两个覆盖层 ===');
r = build(MIX, {});
try {
  new Function('window', 'document', 'performance', 'navigator', 'location', 'matchMedia', 'alert', SRC)
    (r.win, r.doc, { getEntriesByType: () => JSON.parse(JSON.stringify(MIX.res)) }, { clipboard: { writeText: () => Promise.resolve() } }, { href: MIX.page }, r.win.matchMedia, () => { });
} catch (e) { }
ok('同一页面二次注入后 documentElement 仍只有一个 host', r.doc.documentElement.children.length === 1, r.doc.documentElement.children.map(c => c.id));

console.log('\n总计 ' + pass + ' 通过 / ' + fail + ' 失败' + (fail ? '：' + fails.join(' | ') : ''));
process.exit(fail ? 1 : 0);
}
main();
