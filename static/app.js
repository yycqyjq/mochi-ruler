const $ = s => document.querySelector(s);
const DEMO = `# 第一章 入夜

天擦黑，雨又落下来了。

他把柴卸在屋檐下，捆绳一松，柴散了一地。风从门缝里钻进来，吹得灯苗歪向一边，影子在墙上晃了两下，又不动了。

屋里有股潮味，他先蹲下去，把散开的柴一根根捡回来，手指冻得发僵，捏不住细的，只好一根一根慢慢来。蹲得久了，腿发麻，他撑着膝盖站直，这才发现灶台上还搁着半碗冷粥，粥面已经结了一层。

隔壁传来孩子的哭声，哭一阵停一阵，后来就没了，他听着，没起身，只把手里的柴往灶边码齐，一根一根码得整整齐齐。

他推开半扇门，雨脚斜着扫进来，打湿了门槛，远处的山影压得很低，看不清轮廓，只看见沉沉的一片黑。他站在门口听了一阵，觉得冷，又把门合上，回到灶边坐下。

梁上洇开的一片水痕，一滴一滴落在案板上。他拿盆接住，坐在灶边听，一下，又一下，听着听着，他忽然想起从前也是这样一个雨夜，也是这样的滴答声，那时他还小，睡在里屋的炕上，听着听着就睡着了。

夜里雨小了些，他往灶膛里添了两根柴，火星暗下去，又慢慢亮起来，照见墙上挂着的锄头和扁担。

他把湿透的鞋底搁在灶灰里烤着，鞋面上腾起一点白气，慢慢散在梁下，散在那些被烟熏黑的木头上。

# 第二章 敲门

“谁？”

外头没应，雨声把什么都盖住了。

“谁在外面？”他又问了一遍，手按在门闩上没松开。

“过路的。”声音很哑，“借个屋檐，天亮就走。”

他没开门，外头那人也不催，就站在雨里。过了好一阵，门缝底下渗进来一小汪水，弯弯曲曲地爬过门槛。

他把门闩抽开一条缝，那人浑身湿透，肩上背着个布包，包得严严实实。灯一照，脸是青的，嘴唇发紫。

“进来吧。”他侧了侧身，“灶边有干柴，自己烤。”

那人道了谢，进门时在门槛上蹭了两下鞋底，才慢慢往里走。他站在门边看，看那人的手，看那人怀里的包，回过神才发现自己一直没说话。

“你一个人住？”

“嗯。”

“这地方，往东走，几天有人家？”

他想了想，摇头：“不知道，我没往东走过。”

那人不再问，蹲到灶边，把包搁在膝盖上，双手伸向火苗。屋里静下来，只有柴在响，他看着那团火，忽然觉得困。

他把那碗冷粥推过去，那人愣了一下才伸手接，指尖上的泥印在碗沿上，映着一点火光。

雨顺着屋檐往下淌，在门前的石板上砸出一层白雾，又被风斜着吹开，散进黑里，什么都看不见了。`;

let LAST = null;
let loadedText = null;
let loadedFolder = '';
let loadedMeta = null;
// 选中的维度（用于筛选下方逐项对比）；空集 = 显示全部。
let dimSel = new Set();

let toastTimer = null;
function popup(title, body, type = '') {
  const el = $('#toast');
  $('#toast-title').textContent = title;
  $('#toast-body').textContent = body;
  el.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast'; }, type === 'error' ? 5200 : 3600);
}
function closePopup() {
  clearTimeout(toastTimer);
  $('#toast').className = 'toast';
}

function showSource(meta) {
  loadedMeta = meta;
  $('#source-name').textContent = meta.name;
  $('#source-count').textContent = `${meta.files} 个文本文件`;
  $('.folder-mark').textContent = meta.kind === 'file' ? '📄' : '📁';
  $('#source-info').textContent =
    `已识别：${meta.files} 个文件\n` +
    `支持格式：${meta.formats}\n` +
    `总字数：${meta.chars.toLocaleString()}\n` +
    `识别章节：${meta.chapters} 章` +
    (meta.skipped ? `\n跳过格式：${meta.skipped} 个` : '');
  $('#sourcebar').hidden = false;
}
function removeSource() {
  loadedText = null; loadedFolder = ''; loadedMeta = null;
  $('#sourcebar').hidden = true;
  // 保留输入框里的手动补充内容，只移除文件夹来源。
  $('#hint').textContent = '已移除文件来源，输入框内容保留';
  $('#result').hidden = true; $('#empty').hidden = false;
}

function theme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('mochi-theme', next);
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(0);
  if (Math.abs(v) >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

// 逐项判定：所有分数 0–10、越高越好，所以只需和标杆分比高低，不需要方向。
function itemTag(you, bench) {
  if (you === null || you === undefined ||
    bench === null || bench === undefined) {
    return { tag: '—', cls: 'mid' };
  }
  const d = you - bench;
  if (d >= -0.5) return { tag: '达标', cls: 'ok' };
  if (d >= -2.0) return { tag: '接近', cls: 'mid' };
  return { tag: '偏低', cls: 'no' };
}

function scCls(v) {
  if (v >= 7) return 'good';
  if (v >= 4) return 'warn';
  return 'bad';
}

function num(v, n = 1) {
  return (v === null || v === undefined) ? '—' : v.toFixed(n);
}

// 五维分数卡：可点击选中 / 取消选中，用于筛选下方逐项对比。
function renderScores(d) {
  const s = d.summary;
  $('#scores').innerHTML = d.dims.map(k => {
    const v = s[k], bench = d.bench[k];
    const pct = Math.max(2, Math.min(100, v * 10));
    const bmark = Math.max(0, Math.min(100, bench * 10));
    const cls = scCls(v);
    const sel = dimSel.has(k);
    return `<div class="sc${sel ? ' sel' : ''}" data-dim="${k}"
        title="点击只看该维度的逐项对比，再点一次取消">
      <div class="k">${d.dimlabel[k]}</div>
      <div class="v ${cls}">${v.toFixed(2)}</div>
      <div class="bar" title="你 ${v.toFixed(2)}　标杆 ${bench.toFixed(2)}">
        <i style="width:${pct}%;background:var(--${cls})"></i>
        <span class="mark" style="left:${bmark}%"></span>
      </div>
      <div class="t">标杆 ${bench.toFixed(2)}</div>
    </div>`;
  }).join('');
}

// 每个维度覆盖哪些展示指标 —— 与 qc_core 各维权重表一一对应。
// 前端必须内置一份：接口若没带 dimitems（旧版后端 / 字段缺失），
// 筛选会退化成「选了等于没选」的静默空操作。
const DIM_ITEMS_FALLBACK = {
  real: ['vague', 'nego', 'dash', 'rev', 'enum', 'simile', 'sent_den',
    'para_med', 'short_run', 'tail', 'bold', 'dede', 'isde', 'onomat',
    'space', 'short', 'head', 'tell', 'cv', 'dem_lit'],
  human: ['emo', 'net_oral', 'net_dial', 'exclaim', 'redupl', 'question'],
  imm: ['imm_cog', 'imm_perc', 'imm_soma', 'breath', 'surprise', 'touch_temp'],
  rhy: ['sent_p90', 'sent_p10', 'comma_in', 'lit', 'para_cv'],
  syn: ['pron3', 'pron_start', 'sent_med', 'g_turn', 'conn_lit'],
};

// 后端带的 dimitems 直接取自权重表，是权威值；缺失或为空就用前端兜底。
function dimItemsOf(d) {
  return (d && d.dimitems && Object.keys(d.dimitems).length)
    ? d.dimitems : DIM_ITEMS_FALLBACK;
}

// 逐项对比：每项一个 0–10 分，越高越好，不需要方向表。
// 每项标签旁有一个 ? —— 悬停 / 聚焦 / 点击可看该指标的「口径说明 + 原始值」。
// 这里把气泡内容存进 TIPDATA，? 上只放指标键，避免把长文本塞进 data 属性。
let TIPDATA = {};

// 合并表的数据源：维度总分行（含总分）+ 逐项行，渲染与复制共用，
// 保证屏幕上看到的和复制出去的永远一致。维度筛选（dimSel）在这里生效：
// 有选中维度时，维度行只保留总分 + 选中维度，逐项行只保留这些维度覆盖的指标。
function buildTableRows(d) {
  const s = d.summary;
  const dimitems = dimItemsOf(d);
  const covered = new Set(d.dims.flatMap(k => dimitems[k] || []));
  const orphans = d.items.filter(k => !covered.has(k));
  const active = d.dims.filter(k => dimSel.has(k));
  const dimKeys = ['total', ...(active.length ? active : d.dims)];
  const dimRows = dimKeys.map(k => {
    const isTotal = k === 'total';
    return {
      kind: 'dim', key: k,
      name: isTotal ? '总分' : (d.dimlabel[k] || k),
      you: isTotal ? s.total : s[k],
      bench: isTotal ? d.bench.total : d.bench[k],
    };
  });
  let keys = d.items;
  if (active.length) {
    const allow = new Set(active.flatMap(k => dimitems[k] || []));
    keys = d.items.filter(k => allow.has(k) || orphans.includes(k));
  }
  const itemRows = keys.map(k => ({
    kind: 'item', key: k,
    name: (d.label && d.label[k]) || k,
    you: s.items[k], bench: d.bench.items[k],
  }));
  return { dimRows, itemRows, itemCount: keys.length, orphanCount: orphans.length };
}

function renderMetrics(d) {
  const { dimRows, itemRows, itemCount, orphanCount } = buildTableRows(d);
  const active = d.dims.filter(k => dimSel.has(k));
  $('#mcount').textContent = active.length
    ? `（${itemCount} / ${d.items.length} 项 · 只显示选中维度${orphanCount ? '，含通用项' : ''}）`
    : `（${itemCount} 项 · 满分 10）`;
  let rows = '<div class="mrow head"><div class="n">项目</div>' +
    '<div class="you">你的分</div><div class="bench">标杆</div><div class="tag">判定</div></div>';
  // 维度总分行：加深底色、加粗，先给整体结论再往下看逐项。
  for (const r of dimRows) {
    const j = itemTag(r.you, r.bench);
    const cls = (r.you === null || r.you === undefined) ? '' : scCls(r.you);
    rows += `<div class="mrow dimrow">
      <div class="n"><span class="nlabel">${r.name}</span></div>
      <div class="you ${cls}">${num(r.you, 2)}</div>
      <div class="bench">${num(r.bench, 2)}</div>
      <div class="tag">${j.tag}</div>
    </div>`;
  }
  rows += '<div class="msep">逐项对比 · 每项满分 10，越高越好</div>';
  TIPDATA = {};
  for (const r of itemRows) {
    const k = r.key;
    const you = r.you, bench = r.bench;
    const raw = d.summary.metrics[k], rawB = d.bench.metrics[k];
    const j = itemTag(you, bench);
    const cls = (you === null || you === undefined) ? '' : scCls(you);
    const desc = (d.desc && d.desc[k]) || '';
    const dir = (d.rawdir && d.rawdir[k]) || '';
    if (desc) {
      TIPDATA[k] = {
        name: d.label[k] || k,
        desc,
        raw: fmt(raw),
        benchRaw: fmt(rawB),
        dir,
      };
    }
    // 缺口径说明时不渲染 ?，避免出现一个点开是空的图标。
    // 用原生 <button> 而不是带 role="button" 的 span：按键 Enter / Space 只有
    // 原生按钮才会合成 click 事件，span 得自己写键盘处理。
    const qi = desc
      ? `<button type="button" class="qi" data-k="${k}"` +
        ` aria-label="${d.label[k] || k} 的口径说明">?</button>`
      : '';
    rows += `<div class="mrow ${j.cls}">
      <div class="n"><span class="nlabel">${r.name}</span>${qi}</div>
      <div class="you ${cls}">${num(you)}</div>
      <div class="bench">${num(bench)}</div>
      <div class="tag">${j.tag}</div>
    </div>`;
  }
  $('#metrics').innerHTML = rows;
}

/* 复制表格 ---------------------------------------------------------------
   把合并表复制成制表符分隔的纯文本，可直接贴进表格软件或聊天窗口，
   方便把一次检测结果带出去排查。数据源与渲染共用 buildTableRows，
   当前维度筛选选了什么，复制出来的就是什么。 */
function buildCopyText(d) {
  const { dimRows, itemRows } = buildTableRows(d);
  const s = d.summary;
  const lines = [
    `墨尺检测 · ${s.chapters} 章 · ${s.chars.toLocaleString()} 字`,
    ['项目', '你的分', '标杆', '判定'].join('\t'),
  ];
  for (const r of dimRows) {
    lines.push([r.name, num(r.you, 2), num(r.bench, 2),
      itemTag(r.you, r.bench).tag].join('\t'));
  }
  lines.push('—— 逐项对比 ——');
  for (const r of itemRows) {
    lines.push([r.name, num(r.you), num(r.bench),
      itemTag(r.you, r.bench).tag].join('\t'));
  }
  return lines.join('\n');
}

// 剪贴板写入：优先 async clipboard API（本服务只跑在 127.0.0.1，属于安全上下文，
// 一般都走这条）；失败或 API 不存在时退回隐藏 textarea + execCommand。
async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* 走兜底 */ }
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}

/* ? 的口径说明气泡 ------------------------------------------------------
   用 position:fixed 自绘，而不是原生 title：原生 title 有约 1s 延迟、不能换行、
   跨浏览器不一致，且在触摸屏上完全不出现。悬停 / 键盘聚焦 / 触屏点按三种触发，
   覆盖鼠标、键盘与触屏。 */
let tipTimer = null;
let tipAnchor = null;   // 当前气泡挂在哪个 ? 上，滚动时要靠它重算位置

function tipEl() { return $('#tip'); }

// 按锚点矩形摆位：默认在上方，上方不够就翻到下方，左右贴边则收进视口内。
function positionTip(qi) {
  const el = tipEl();
  el.style.left = '-9999px';
  el.style.top = '0px';
  const a = qi.getBoundingClientRect();
  const b = el.getBoundingClientRect();
  const M = 8;
  let left = Math.min(a.left, window.innerWidth - M - b.width);
  if (left < M) left = M;
  let top = a.top - b.height - 8;
  if (top < M) top = a.bottom + 8;
  el.style.left = `${Math.round(left)}px`;
  el.style.top = `${Math.round(top)}px`;
}

function showTip(qi) {
  const info = TIPDATA[qi.dataset.k];
  if (!info) return;
  clearTimeout(tipTimer);
  const el = tipEl();
  el.textContent = '';
  const add = (cls, text) => {
    const n = document.createElement('div');
    n.className = cls;
    n.textContent = text;
    el.appendChild(n);
  };
  add('tip-title', info.name);
  add('tip-desc', info.desc);
  add('tip-raw', `原始值　你 ${info.raw}　标杆 ${info.benchRaw}` +
    (info.dir ? `　·　${info.dir}` : ''));
  el.dataset.k = qi.dataset.k;
  tipAnchor = qi;
  el.hidden = false;
  positionTip(qi);   // 先显示再量尺寸，避免在旧位置闪一下
}

function hideTip() {
  clearTimeout(tipTimer);
  const el = tipEl();
  el.hidden = true;
  delete el.dataset.k;
  tipAnchor = null;
}

// 给鼠标留一点余量：从 ? 移向气泡时不要立刻消失。
function scheduleHide() { clearTimeout(tipTimer); tipTimer = setTimeout(hideTip, 140); }

// 滚动 / 改变窗口大小时**重新定位**而不是关闭：键盘 Tab 切换会把元素滚入视口，
// 若在这里直接关闭，气泡会「刚弹出就被自己滚没」。锚点已滚出视口才收起。
function repositionTip() {
  const el = tipEl();
  if (el.hidden || !tipAnchor) return;
  if (!tipAnchor.isConnected) return hideTip();
  const a = tipAnchor.getBoundingClientRect();
  if (a.bottom < 0 || a.top > window.innerHeight) return hideTip();
  positionTip(tipAnchor);
}


function render(d) {
  $('#empty').hidden = true;
  $('#result').hidden = false;

  const s = d.summary;
  $('#meta').textContent =
    `${s.chapters} 章　·　${s.chars.toLocaleString()} 字`;

  // 总分单独成卡：先给结论，再往下看五维与逐项。
  const tv = s.total, tb = d.bench.total;
  const tcls = scCls(tv), tj = itemTag(tv, tb);
  const tpct = Math.max(0, Math.min(100, tv * 10));
  const tbmark = Math.max(0, Math.min(100, tb * 10));
  $('#totalcard').innerHTML = `
    <div class="tc-head">
      <span class="tc-label">总分</span>
      <span class="tc-tip">五维等权平均</span>
    </div>
    <div class="tc-body">
      <div class="tc-num ${tcls}">${tv.toFixed(2)}<span class="tc-max">/ 10</span></div>
      <div class="tc-right">
        <div class="tc-bar" title="你 ${tv.toFixed(2)}　标杆 ${tb.toFixed(2)}">
          <i style="width:${tpct}%;background:var(--${tcls})"></i>
          <span class="tc-mark" style="left:${tbmark}%"></span>
        </div>
        <div class="tc-foot">
          <span>标杆 ${tb.toFixed(2)}　·　竖线为基准位置</span>
          <span class="tc-tag ${tj.cls}">${tj.tag}</span>
        </div>
      </div>
    </div>`;

  renderScores(d);
  renderMetrics(d);

  $('#chtitle').textContent = `逐章（${d.chapters.length}）`;
  let ch = '<div class="crow head"><div class="t">章</div>' +
    '<div class="v">字数</div><div class="v">真人感</div><div class="v">人味</div>' +
    '<div class="v">代入</div><div class="v">节奏</div><div class="v">句法</div>' +
    '<div class="v">总分</div></div>';
  for (const c of d.chapters) {
    ch += `<div class="crow">
      <div class="t" title="${c.title}">${c.title}</div>
      <div class="v">${c.chars}</div>
      <div class="v ${scCls(c.score.real)}">${c.score.real.toFixed(1)}</div>
      <div class="v ${scCls(c.score.human)}">${c.score.human.toFixed(1)}</div>
      <div class="v ${scCls(c.score.imm)}">${c.score.imm.toFixed(1)}</div>
      <div class="v ${scCls(c.score.rhy)}">${c.score.rhy.toFixed(1)}</div>
      <div class="v ${scCls(c.score.syn)}">${c.score.syn.toFixed(1)}</div>
      <div class="v ${scCls(c.score.total)}">${c.score.total.toFixed(1)}</div>
    </div>`;
    if (c.violations && c.violations.length) {
      ch += `<div class="viol">⚠ ${c.violations.map(v => v.name).join('、')}</div>`;
    }
  }
  $('#chapters').innerHTML = ch;
}

async function run() {
  const typedText = $('#text').value.trim();
  const text = loadedText !== null
    ? [loadedText, typedText].filter(Boolean).join('\n\n')
    : typedText;
  if (!text.trim()) {
    const reason = '没有检测内容。请粘贴正文，或先选择/拖入/粘贴文件或文件夹。';
    $('#hint').textContent = reason;
    popup('检测失败', reason, 'error');
    return;
  }
  const runBtn = $('#run');
  runBtn.disabled = true;
  runBtn.classList.add('loading');
  runBtn.dataset.label = runBtn.textContent;
  runBtn.textContent = '检测中…';
  $('#hint').textContent = '正在拆章节并计算指标…';
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!r.ok) throw new Error('检测失败：' + r.status);
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    LAST = d;
    render(d);
    const s = d.summary;
    const sourceNote = loadedFolder
      ? `\n来源：${loadedMeta && loadedMeta.kind === 'file' ? '📄' : '📁'} ${loadedFolder}`
      : '';
    const extra = s.chapters === 0
      ? '\n没有识别到有效章节，请检查文件内容或章节格式。'
      : '';
    $('#hint').textContent = '检测完成';
    popup('检测完成',
      `已完成 ${s.chapters} 章、${s.chars.toLocaleString()} 字的检测。${sourceNote}${extra}`, 'success');
  } catch (e) {
    const reason = e && e.message ? e.message : '未知错误';
    $('#hint').textContent = `检测失败：${reason}`;
    popup('检测失败', `检测没有完成。\n\n原因：${reason}\n\n请检查输入内容或重新载入文件后再试。`, 'error');
  } finally {
    runBtn.disabled = false;
    runBtn.classList.remove('loading');
    runBtn.textContent = runBtn.dataset.label || '开始检测';
  }
}

const OK_EXT = /\.(txt|md|markdown)$/i;
const CHAPTER_HEAD = /(?:^|\n)\s*(?:#\s*)?(?:第[一二三四五六七八九十百千\d]{1,6}[章节]|(?:Chapter|CHAPTER)\s*\d+|楔子|序章|番外)(?:\s|$)/g;
// 纯数字前缀章头（「01开篇」「02 别离」）。护栏与后端 split_chapters 一致：
// 前面是空行（或文件开头）、数字 1–4 位、后面紧跟汉字、且不是「2012年」这类时间。
const CHAPTER_HEAD_NUM = /(?:\n[ \t\u3000]*\n|^)[ \t\u3000]*\d{1,4}[ \t\u3000]?(?!年|月|日|时|分|秒|点|号|届)[\u4e00-\u9fa5]/g;
function countChapters(text) {
  return (text.match(CHAPTER_HEAD) || []).length +
    (text.match(CHAPTER_HEAD_NUM) || []).length;
}

function loadFiles(fs, sourceName = '', sourceKind = 'folder') {
  let list = [...fs].filter(f => OK_EXT.test(f.name));
  const skipped = [...fs].length - list.length;
  if (skipped) unsupportedFiles([...fs].filter(f => !OK_EXT.test(f.name)));
  if (!list.length) {
    $('#hint').textContent = '没找到 .txt / .md / .markdown 文件';
    return;
  }
  list.sort((a, b) => (a.webkitRelativePath || a.name)
    .localeCompare(b.webkitRelativePath || b.name, 'zh'));
  let done = 0, buf = [];
  list.forEach((f, i) => {
    const rd = new FileReader();
    rd.onload = () => {
      buf[i] = rd.result;
      if (++done === list.length) {
        const joined = buf.join('\n\n');
        if (sourceName) {
          loadedText = joined;
          loadedFolder = sourceName;
          const chapters = (joined.match(/(^|\n)\s*#\s*第[^\n]{1,20}[章节]/g) || []).length;
          showSource({
            name: sourceName,
            kind: sourceKind,
            files: list.length,
            skipped,
            formats: [...new Set(list.map(x => (x.name.match(/\.[^.]+$/) || [''])[0].toLowerCase()))].join('、') || '无',
            chars: joined.replace(/\s/g, '').length,
            chapters: chapters || countChapters(joined) || '未分章'
          });
          $('#text').value = '';
        } else {
          loadedText = null;
          loadedFolder = '';
          loadedMeta = null;
          $('#sourcebar').hidden = true;
          $('#text').value = joined;
        }
        const chapterHint = countChapters(joined);
        $('#hint').textContent = sourceName
          ? `已载入 ${list.length} 个文件；识别 ${chapterHint || '未分章'}；输入框内容会一起检测`
          : `已载入 ${list.length} 个文件；识别 ${chapterHint || '未分章'}` +
          (skipped ? `（跳过 ${skipped} 个非文本文件）` : '');
      }
    };
    rd.readAsText(f, 'utf-8');
  });
}

/* 拖拽：支持文件与文件夹 */
function walkEntry(entry, out, roots, isRoot = false) {
  return new Promise(res => {
    if (entry.isFile) {
      entry.file(f => { out.push(f); res(); }, () => res());
    } else if (entry.isDirectory) {
      if (isRoot) roots.push(entry.name);
      const rd = entry.createReader();
      const all = [];
      const step = () => rd.readEntries(async es => {
        if (!es.length) {
          for (const e of all) await walkEntry(e, out, roots);
          return res();
        }
        all.push(...es);
        step();
      }, () => res());
      step();
    } else res();
  });
}

async function fromDrop(dt) {
  const out = [], roots = [];
  const items = dt.items ? [...dt.items] : [];
  const entries = items.map(i => i.webkitGetAsEntry && i.webkitGetAsEntry())
    .filter(Boolean);
  if (entries.length) {
    for (const e of entries) await walkEntry(e, out, roots, true);
  } else {
    out.push(...[...dt.files]);
  }
  return { files: out, folder: roots.length === 1 ? roots[0] : '' };
}

async function fromPaste(dt) {
  const items = dt.items ? [...dt.items] : [];
  const entries = items.map(i => i.webkitGetAsEntry && i.webkitGetAsEntry())
    .filter(Boolean);
  const out = [], roots = [];
  if (entries.length) {
    for (const e of entries) await walkEntry(e, out, roots, true);
  } else if (dt.files && dt.files.length) {
    out.push(...[...dt.files]);
  }
  return { files: out, folder: roots.length === 1 ? roots[0] : '' };
}

function unsupportedFiles(fs) {
  const bad = [...fs].filter(f => !OK_EXT.test(f.name)).map(f => f.name);
  if (bad.length) {
    const shown = bad.slice(0, 8).join('、');
    popup('文件格式不支持',
      `墨尺只支持 .txt、.md、.markdown 文件。\n\n已跳过 ${bad.length} 个不支持的文件：${shown}${bad.length > 8 ? ' 等' : ''}`, 'warn');
  }
  return bad.length;
}

function bindPaste(el) {
  el.addEventListener('paste', async e => {
    const dt = e.clipboardData;
    if (!dt) return;
    const hasFiles = (dt.files && dt.files.length) ||
      [...(dt.items || [])].some(i => i.kind === 'file');
    if (!hasFiles) return; // 普通文字粘贴，交给浏览器
    e.preventDefault();
    $('#hint').textContent = '读取剪贴板文件中…';
    const pasted = await fromPaste(dt);
    if (pasted.files.length) {
      const name = pasted.folder || (pasted.files.length === 1
        ? pasted.files[0].name : `${pasted.files.length} 个文件`);
      loadFiles(pasted.files, name, pasted.folder ? 'folder' : 'file');
      return;
    }
    popup('无法读取此文件夹',
      '当前浏览器没有把桌面剪贴板中的文件夹暴露给网页。\n\n请改用「选文件夹」按钮，或直接把文件夹拖入输入框。', 'warn');
    $('#hint').textContent = '';
  });
}

function bindDrop(el) {
  let n = 0;
  el.addEventListener('dragenter', e => {
    e.preventDefault(); n++; el.classList.add('on');
  });
  el.addEventListener('dragover', e => e.preventDefault());
  el.addEventListener('dragleave', e => {
    e.preventDefault(); if (--n <= 0) { n = 0; el.classList.remove('on'); }
  });
  el.addEventListener('drop', async e => {
    e.preventDefault(); n = 0; el.classList.remove('on');
    $('#hint').textContent = '读取中…';
    const dropped = await fromDrop(e.dataTransfer);
    if (dropped.files.length) {
      const name = dropped.folder || (dropped.files.length === 1
        ? dropped.files[0].name : `${dropped.files.length} 个文件`);
      loadFiles(dropped.files, name, dropped.folder ? 'folder' : 'file');
    } else $('#hint').textContent = '没读到文件';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const t = localStorage.getItem('mochi-theme');
  if (t) document.documentElement.setAttribute('data-theme', t);
  $('#theme').onclick = theme;
  $('#source-remove').onclick = removeSource;
  $('#run').onclick = run;
  // 复制表格：把维度总分 + 逐项对比复制成一张 TSV 表（含章数 / 字数头行），
  // 数据源与渲染共用 buildTableRows，当前筛选到什么就复制什么。
  $('#copybtn').onclick = async () => {
    if (!LAST) return;
    const ok = await copyText(buildCopyText(LAST));
    if (ok) {
      const btn = $('#copybtn'), old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(() => { btn.textContent = old; }, 1400);
    } else {
      popup('复制失败', '浏览器没有放行剪贴板写入，请手动选中表格内容复制。', 'error');
    }
  };
  // 点维度卡切换选中；选中后逐项对比只显示这些维度覆盖的指标。
  $('#scores').addEventListener('click', e => {
    const el = e.target.closest('.sc[data-dim]');
    if (!el || !LAST) return;
    const k = el.dataset.dim;
    if (dimSel.has(k)) dimSel.delete(k); else dimSel.add(k);
    renderScores(LAST);
    renderMetrics(LAST);
  });
  // ? 的口径说明：鼠标走悬停、键盘走聚焦、触屏走点按，按指针类型分流。
  //
  // 用 pointerover / pointerout（会冒泡、且带 pointerType），**不用** mouseover /
  // mouseout：触屏点按后浏览器会补发一整套兼容鼠标事件，其中末尾那个 mouseout
  // 会把刚点开的气泡立刻关掉，表现为「点了没反应」。
  const qiOf = e => (e.target.closest ? e.target.closest('.qi') : null);
  $('#metrics').addEventListener('pointerover', e => {
    if (e.pointerType === 'touch') return;
    const qi = qiOf(e);
    if (qi) showTip(qi);
  });
  $('#metrics').addEventListener('pointerout', e => {
    if (e.pointerType === 'touch') return;
    const qi = qiOf(e);
    if (!qi) return;
    if (e.relatedTarget && qi.contains(e.relatedTarget)) return;
    scheduleHide();
  });
  $('#metrics').addEventListener('focusin', e => {
    const qi = qiOf(e);
    if (qi) showTip(qi);
  });
  $('#metrics').addEventListener('focusout', e => {
    if (qiOf(e)) scheduleHide();
  });
  // 键盘敲 Enter / Space：原生 <button> 会合成 click，其 event.detail 恒为 0。
  // 用它跟鼠标点击区分开——鼠标点击不参与（鼠标走 hover）。
  // 也补上「Esc 收起后元素仍是聚焦态、focusin 不会再触发」这个缺口。
  $('#metrics').addEventListener('click', e => {
    if (e.detail !== 0) return;
    const qi = qiOf(e);
    if (!qi) return;
    e.preventDefault();
    if (tipEl().dataset.k === qi.dataset.k && !tipEl().hidden) hideTip();
    else showTip(qi);
  });
  // 触屏：同一 ? 再点一次收起。鼠标与键盘不参与（分别是 hover / focus）。
  $('#metrics').addEventListener('pointerdown', e => {
    if (e.pointerType !== 'touch') return;
    const qi = qiOf(e);
    if (!qi) return;
    e.preventDefault();
    if (tipEl().dataset.k === qi.dataset.k && !tipEl().hidden) hideTip();
    else showTip(qi);
  });
  // 触屏点别处收起。
  document.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'touch') return;
    const el = tipEl();
    if (el.hidden || !e.target.closest) return;
    if (e.target.closest('.qi') || e.target.closest('#tip')) return;
    hideTip();
  });
  // 气泡本身可悬停，移进去时不要消失。
  tipEl().addEventListener('pointerenter', () => clearTimeout(tipTimer));
  tipEl().addEventListener('pointerleave', scheduleHide);
  // 滚动 / 改变窗口大小：重新定位，而不是关闭（Tab 切换会滚动视口）。
  window.addEventListener('scroll', repositionTip, true);
  window.addEventListener('resize', repositionTip);
  $('#demo').onclick = () => { loadedText = null; loadedFolder = ''; loadedMeta = null; $('#sourcebar').hidden = true; $('#text').value = DEMO; };
  $('#clear').onclick = () => {
    loadedText = null; loadedFolder = ''; loadedMeta = null; $('#sourcebar').hidden = true;
    $('#text').value = '';
    $('#result').hidden = true; $('#empty').hidden = false;
    $('#hint').textContent = '';
  };
  $('#file').onchange = e => {
    if (e.target.files.length) {
      const name = e.target.files.length === 1
        ? e.target.files[0].name : `${e.target.files.length} 个文件`;
      loadFiles(e.target.files, name, 'file');
    }
  };
  $('#dir').onchange = e => {
    if (e.target.files.length) {
      const p = e.target.files[0].webkitRelativePath || '';
      loadFiles(e.target.files, p.split('/')[0] || '文件夹');
    }
  };
  bindDrop($('#text'));
  bindPaste($('#text'));
  $('#text').addEventListener('input', () => {
    if (loadedText === null && $('#text').value.trim()) {
      const n = countChapters($('#text').value);
      $('#hint').textContent = `输入内容 · 识别 ${n || '未分章'}`;
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closePopup(); hideTip(); }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run();
  });
});
