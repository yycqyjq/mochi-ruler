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
// 逐项排序：dim = 按维度分组（默认），gap = 按与标杆的差距从大到小平铺。
let sortMode = 'dim';
// 逐章列表视图：排序 / 违规过滤 / 展开的章 / 大书截断。
let chSort = 'orig';
let chOnlyViol = false;
let showAllChapters = false;
let expandedCh = new Set();
const CHAPTER_LIMIT = 60;   // 超过后默认截断，只渲染前 60 章 +「显示全部」

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
  // 不在载入时报章节数：前端估算与后端拆章（7 种模式选型）口径不一致，
  // 会出现「载入说 12 章、检测完 10 章」——章节数只认检测结果。
  $('#source-info').textContent =
    `已识别：${meta.files} 个文件\n` +
    `支持格式：${meta.formats}\n` +
    (meta.encNote ? `解码：${meta.encNote}\n` : '') +
    `总字数：${meta.chars.toLocaleString()}\n` +
    `章节：以检测结果为准` +
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

// HTML 转义：章标题等文本来自被检测的文件（可能是任意来源下载的 txt），
// 渲染进 innerHTML 前必须转义，防止「第X章 <img src=x onerror=…>」这类
// 藏在章头行里的内容借渲染执行。
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ── 上次检测对比（ghost）────────────────────────────────────
// 最近一次检测的汇总（总分 / 五维 / 40 项）存 localStorage，供下一次
// 检测做前后对比：尺条上的灰点 = 上次位置，行内 ▲▼ = 涨跌，雷达上叠
// 一层上次的灰色五边形。只存汇总层不存逐章，体积几 KB；隐私模式下
// 静默放弃。
let PREV = null;
try { PREV = JSON.parse(localStorage.getItem('mochi-prev-run') || 'null'); } catch (e) { PREV = null; }
function savePrev(d) {
  try {
    localStorage.setItem('mochi-prev-run', JSON.stringify({
      ts: Date.now(), summary: d.summary, bench: d.bench,
    }));
  } catch (e) { /* ignore */ }
}
function prevAgo(ts) {
  const m = Math.max(1, Math.round((Date.now() - ts) / 60000));
  if (m < 60) return m + ' 分钟前';
  const h = Math.round(m / 60);
  if (h < 24) return h + ' 小时前';
  return Math.round(h / 24) + ' 天前';
}
// 行内涨跌标记：▲ 绿 / ▼ 朱。所有分数 0–10、越高越好，涨就是改善。
// ±0.05 内视为持平，不渲染（避免噪音）。
function deltaHTML(you, prev) {
  if (prev == null || you == null) return '';
  const df = you - prev;
  if (Math.abs(df) < 0.05) return '';
  const up = df > 0;
  return `<span class="d ${up ? 'up' : 'down'}">${up ? '▲' : '▼'}${Math.abs(df).toFixed(1)}</span>`;
}
function prevVal(kind, k) {
  if (!PREV || !PREV.summary) return null;
  if (kind === 'item') return (PREV.summary.items || {})[k] ?? null;
  return (PREV.summary[k] ?? null);
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
    const pv = prevVal('dim', k);
    const pgm = pv == null ? '' :
      `<span class="gmark" style="left:${Math.max(0, Math.min(100, pv * 10))}%" title="上次 ${pv.toFixed(2)}"></span>`;
    // role/tabindex/aria-pressed：让维度筛选能被 Tab 到、能用 Enter/Space 触发，
    // 读屏也能播报选中态（键盘激活由全局 keydown 委托统一处理）。
    return `<div class="sc${sel ? ' sel' : ''}" data-dim="${k}"
        role="button" tabindex="0" aria-pressed="${sel}"
        title="点击只看该维度的逐项对比，再点一次取消">
      <div class="k">${d.dimlabel[k]}</div>
      <div class="v ${cls}">${v.toFixed(2)}</div>
      <div class="bar" title="你 ${v.toFixed(2)}　标杆 ${bench.toFixed(2)}">
        <i style="width:${pct}%;background:var(--${cls})"></i>
        <span class="mark" style="left:${bmark}%"></span>${pgm}
      </div>
      <div class="t">标杆 ${bench.toFixed(2)}${deltaHTML(v, pv)}</div>
    </div>`;
  }).join('');
}

// 每个维度覆盖哪些展示指标 —— 与 qc_core 各维权重表一一对应。
// 前端必须内置一份：接口若没带 dimitems（旧版后端 / 字段缺失），
// 筛选会退化成「选了等于没选」的静默空操作。
const DIM_ITEMS_FALLBACK = {
  real: ['vague', 'nego', 'dash', 'rev', 'simile', 'sent_den',
    'para_med', 'short_run', 'tail', 'bold', 'dede', 'isde', 'onomat',
    'space', 'short', 'tell', 'cv', 'dem_lit'],
  human: ['emo', 'net_oral', 'dial_sent', 'exclaim', 'redupl', 'question', 'emo_type'],
  imm: ['breath', 'surprise', 'touch_temp', 'act'],
  rhy: ['sent_p90', 'sent_p10', 'comma_in', 'lit', 'para_cv', 'punc_den'],
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
// 逐章列表里的违规芯片用同一气泡（VIOL_TIPS），键空间互不重叠。
let TIPDATA = {};
let VIOL_TIPS = {};

// 合并表的数据源：维度总分行（含总分）+ 按维度分组的逐项行，渲染与复制共用，
// 保证屏幕上看到的和复制出去的永远一致。维度筛选（dimSel）在这里生效：
// 有选中维度时，维度行只保留总分 + 选中维度，逐项行只保留这些维度覆盖的指标。
// 组序与五维卡一致（d.dims），未归入任何维度的项兜底进「通用」组——
// 正常口径下 SHOW 与权重表完全重合，这组是空的。
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
  const groups0 = (active.length ? active : d.dims).map(k => ({
    dim: k,
    name: d.dimlabel[k] || k,
    items: (dimitems[k] || []).filter(item => d.items.includes(item)),
  }));
  if (orphans.length) groups0.push({ dim: '', name: '通用', items: orphans });
  let groups = groups0;
  let itemDim = null;
  if (sortMode === 'gap') {
    // 按差距平铺：「标杆 − 你的分」从大到小。组名换成排序说明，每行补一个
    // 维度小标签——渲染与复制共用本函数，屏幕所见与复制所得一致。
    const dimOf = {};
    groups0.forEach(g => g.items.forEach(item => { dimOf[item] = g.dim; }));
    groups = [{
      dim: '', name: '按差距排序',
      items: groups0.flatMap(g => g.items).sort((a, b) =>
        ((d.bench.items[b] ?? 0) - (d.summary.items[b] ?? 0)) -
        ((d.bench.items[a] ?? 0) - (d.summary.items[a] ?? 0))),
    }];
    itemDim = dimOf;
  }
  const itemCount = groups.reduce((n, g) => n + g.items.length, 0);
  return { dimRows, groups, itemCount, orphanCount: orphans.length, itemDim };
}

function renderMetrics(d) {
  const { dimRows, groups, itemCount, orphanCount, itemDim } = buildTableRows(d);
  const active = d.dims.filter(k => dimSel.has(k));
  document.querySelectorAll('#sortseg button').forEach(b =>
    b.classList.toggle('on', b.dataset.sort === sortMode));
  $('#mcount').textContent = active.length
    ? `（${itemCount} / ${d.items.length} 项 · 只显示选中维度${orphanCount ? '，含通用项' : ''}）`
    : `（${itemCount} 项 · 满分 10）`;
  let rows = '<div class="mrow head"><div class="n">项目</div><div class="mbarcell"></div>' +
    '<div class="you">你的分</div><div class="bench">标杆</div><div class="tag">判定</div></div>';
  // 维度总分行：加深底色、加粗，先给整体结论再往下看逐项。
  for (const r of dimRows) {
    const j = itemTag(r.you, r.bench);
    const cls = (r.you === null || r.you === undefined) ? '' : scCls(r.you);
    rows += `<div class="mrow dimrow">
      <div class="n"><span class="nlabel">${r.name}</span></div>
      <div class="mbarcell"></div>
      <div class="you ${cls}">${num(r.you, 2)}${deltaHTML(r.you, prevVal('dim', r.key))}</div>
      <div class="bench">${num(r.bench, 2)}</div>
      <div class="tag">${j.tag}</div>
    </div>`;
  }
  rows += '<div class="msep">逐项对比 · 每项满分 10，越高越好</div>';
  TIPDATA = {};
  for (const g of groups) {
    rows += `<div class="mgroup" data-dim="${g.dim}"><span>${esc(g.name)}</span>` +
      `<span>${g.items.length} 项</span></div>`;
    for (const k of g.items) {
      const you = d.summary.items[k], bench = d.bench.items[k];
      const raw = d.summary.metrics[k], rawB = d.bench.metrics[k];
      const j = itemTag(you, bench);
      const cls = (you === null || you === undefined) ? '' : scCls(you);
      const name = (d.label && d.label[k]) || k;
      const desc = (d.desc && d.desc[k]) || '';
      const dir = (d.rawdir && d.rawdir[k]) || '';
      if (desc) {
        TIPDATA[k] = {
          name,
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
          ` aria-label="${esc(name)} 的口径说明">?</button>`
        : '';
      // 尺列：填充=你的分，朱砂竖线=标杆 —— 与五维卡同一视觉语言，
      // 40 行扫一眼就能看出哪项短，不必逐行心算两个数。
      const fill = cls
        ? `<i style="width:${Math.max(0, Math.min(10, you)) * 10}%;background:var(--${cls})"></i>`
        : '';
      const mark = (bench === null || bench === undefined) ? '' :
        `<span class="mark" style="left:${Math.max(0, Math.min(10, bench)) * 10}%"></span>`;
      const dtag = (itemDim && itemDim[k])
        ? `<span class="dtag">${esc(d.dimlabel[itemDim[k]] || itemDim[k])}</span>` : '';
      const pv = prevVal('item', k);
      const gmark = pv == null ? '' :
        `<span class="gmark" style="left:${Math.max(0, Math.min(10, pv)) * 10}%" title="上次 ${pv.toFixed(2)}"></span>`;
      const dStr = deltaHTML(you, pv);
      rows += `<div class="mrow ${j.cls}">
        <div class="n"><span class="nlabel">${esc(name)}</span>${dtag}${qi}</div>
        <div class="mbar">${fill}${mark}${gmark}</div>
        <div class="you ${cls}">${num(you)}${dStr}</div>
        <div class="bench">${num(bench)}</div>
        <div class="tag">${j.tag}</div>
      </div>`;
    }
  }
  $('#metrics').innerHTML = rows;
}

/* 复制表格 ---------------------------------------------------------------
   把合并表复制成制表符分隔的纯文本，可直接贴进表格软件或聊天窗口，
   方便把一次检测结果带出去排查。数据源与渲染共用 buildTableRows，
   当前维度筛选选了什么，复制出来的就是什么。 */function buildCopyText(d) {
  const { dimRows, groups, itemDim } = buildTableRows(d);
  const s = d.summary;
  const lines = [
    `墨尺检测 · ${s.chapters} 章 · ${s.chars.toLocaleString()} 字`,
    ['项目', '你的分', '标杆', '判定'].join('\t'),
  ];
  for (const r of dimRows) {
    lines.push([r.name, num(r.you, 2), num(r.bench, 2),
      itemTag(r.you, r.bench).tag].join('\t'));
  }
  for (const g of groups) {
    lines.push(`—— ${g.name} ——`);
    for (const k of g.items) {
      const dimName = itemDim && itemDim[k]
        ? '·' + (d.dimlabel[itemDim[k]] || itemDim[k]) : '';
      // ⚠ 括号不能省：`+` 优先级高于 `||`，写成 `A || k + dimName` 会被解析成
      // `A || (k + dimName)`——有中文名时 dimName 被丢掉，复制出去的表缺维度后缀。
      lines.push([((d.label && d.label[k]) || k) + dimName,
        num(s.items[k]), num(d.bench.items[k]),
        itemTag(s.items[k], d.bench.items[k]).tag].join('\t'));
    }
  }
  return lines.join('\n');
}

// 复制逐章：应用当前排序与违规过滤后的逐章分数表（含违规名）。
function buildChaptersCopy(d) {
  const list = chapterList(d);
  const head = `墨尺检测 · ${d.summary.chapters} 章 · ${d.summary.chars.toLocaleString()} 字 —— 逐章` +
    (chSort === 'low' ? '（按总分最低）' : '') + (chOnlyViol ? '（只看有违规）' : '');
  const lines = [
    head,
    ['章', '字数', '真人感', '人味', '代入', '节奏', '句法', '总分', '违规'].join('\t'),
  ];
  for (const { c } of list) {
    lines.push([c.title, c.chars,
      c.score.real.toFixed(1), c.score.human.toFixed(1), c.score.imm.toFixed(1),
      c.score.rhy.toFixed(1), c.score.syn.toFixed(1), c.score.total.toFixed(1),
      (c.violations || []).map(v => v.name).join('、')].join('\t'));
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
  const info = TIPDATA[qi.dataset.k] || VIOL_TIPS[qi.dataset.k];
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
  if (info.raw !== undefined) {
    add('tip-raw', `原始值　你 ${info.raw}　标杆 ${info.benchRaw}` +
      (info.dir ? `　·　${info.dir}` : ''));
  }
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


// 「最该先改」摘要条：总分卡直接给出行动结论，兑现 README 的
// 「指出最该先改的项」。挑选口径与判定一致：差距 > 2 偏低，> 0.5 接近。
function renderFixbar(d) {
  const s = d.summary, b = d.bench;
  const dimGaps = d.dims
    .map(k => ({ k, name: d.dimlabel[k] || k, you: s[k], bench: b[k] }))
    .filter(x => x.you != null && x.bench != null && x.bench - x.you > 2)
    .sort((a, b) => (b.bench - b.you) - (a.bench - a.you));
  const gaps = d.items
    .map(k => ({ k, name: (d.label && d.label[k]) || k,
                 you: s.items[k], bench: b.items[k] }))
    .filter(x => x.you != null && x.bench != null)
    .map(x => ({ ...x, gap: x.bench - x.you }));
  const lows = gaps.filter(x => x.gap > 2)
    .sort((a, b) => b.gap - a.gap).slice(0, 3);
  const mids = lows.length ? [] :
    gaps.filter(x => x.gap > 0.5).sort((a, b) => b.gap - a.gap).slice(0, 3);
  const violNames = [];
  let violChs = 0;
  for (const c of d.chapters) {
    if (c.violations && c.violations.length) {
      violChs++;
      for (const v of c.violations)
        if (!violNames.includes(v.name)) violNames.push(v.name);
    }
  }
  const el = $('#fixbar');
  el.hidden = false;
  if (!dimGaps.length && !lows.length && !mids.length && !violChs) {
    el.innerHTML = '<span class="fx-ok">✓ 各项均达标或接近标杆，未命中硬规则。</span>';
    return;
  }
  const chips = [];
  for (const x of dimGaps.slice(0, 2)) {
    chips.push(`<button type="button" class="fx-chip no" data-dim="${x.k}">` +
      `${esc(x.name)} ${x.you.toFixed(2)}（标杆 ${x.bench.toFixed(2)}）</button>`);
  }
  for (const x of (lows.length ? lows : mids)) {
    chips.push(`<button type="button" class="fx-chip ${lows.length ? 'no' : 'mid'}" data-k="${x.k}">` +
      `${esc(x.name)} ${x.you.toFixed(1)}（标杆 ${x.bench.toFixed(1)}）</button>`);
  }
  if (violChs) {
    chips.push(`<button type="button" class="fx-chip warn" data-viol="1">` +
      `⚠ 硬规则 ${violNames.length} 项 · 命中 ${violChs} 章</button>`);
  }
  el.innerHTML = `<span class="fx-label">⚡ 最该先改</span>${chips.join('')}`;
}

// 点摘要条/章明细里的指标芯片 → 选中所在维度并滚到那一行，短暂高亮。
function jumpToItem(d, k) {
  const dimitems = dimItemsOf(d);
  const dim = d.dims.find(dd => (dimitems[dd] || []).includes(k));
  if (dim && !dimSel.has(dim)) {
    dimSel.add(dim);
    renderScores(d);
    renderMetrics(d);
  }
  const qi = document.querySelector(`.qi[data-k="${k}"]`);
  const row = qi && qi.closest('.mrow');
  if (row) {
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.classList.remove('flash');
    void row.offsetWidth;
    row.classList.add('flash');
  } else {
    $('#metrics').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
}

// 章展开明细：该章与标杆差距最大的前三项 + 违规完整详情。数据本来就在
// analyze 的逐章返回里（items / violations），此前只是没渲染。
function chapterDetailHTML(d, c) {
  const gaps = d.items
    .map(k => ({ k, name: (d.label && d.label[k]) || k,
                 you: c.items[k], bench: d.bench.items[k] }))
    .filter(x => x.you != null && x.bench != null)
    .map(x => ({ ...x, gap: x.bench - x.you }))
    .sort((a, b) => b.gap - a.gap);
  const worst = gaps.filter(x => x.gap > 2).slice(0, 3);
  const itemsPart = worst.length
    ? worst.map(x =>
        `<button type="button" class="fx-chip no" data-k="${x.k}">` +
        `${esc(x.name)} ${x.you.toFixed(1)}（标杆 ${x.bench.toFixed(1)}）</button>`).join('')
    : '<span class="dim">各项均接近标杆。</span>';
  const violPart = (c.violations || [])
    .map(v => `<div class="chd-viol">⚠ ${esc(v.name)}：${esc(v.detail)}</div>`).join('');
  return `<div class="chdetail"><div class="chd-items">${itemsPart}</div>${violPart}</div>`;
}

// 逐章列表的数据源：应用当前排序与违规过滤。渲染与「复制逐章」共用，
// 保证屏幕上看到的和复制出去的永远一致。
function chapterList(d) {
  // ⚠ 必须是 let：下面按「只看违规」会重新赋值（filter 返回新数组）。
  // 写成 const 会在 chOnlyViol=true 时抛 TypeError: Assignment to constant variable
  // ——「只看有违规」按钮、fixbar 违规芯片、「复制逐章」都会崩。
  let list = d.chapters.map((c, i) => ({ c, i }));
  if (chOnlyViol) list = list.filter(x => x.c.violations && x.c.violations.length);
  if (chSort === 'low') list.sort((a, b) => a.c.score.total - b.c.score.total);
  return list;
}

// 逐章列表：可按原文顺序或总分排序，可只看有违规的章；超过 CHAPTER_LIMIT
// 截断（几千章一次性渲染会卡 DOM），章行点击展开该章问题明细。
function renderChapters(d) {
  $('#chtitle').textContent = `逐章（${d.chapters.length}）`;
  document.querySelectorAll('#chsortseg button').forEach(b =>
    b.classList.toggle('on', b.dataset.chsort === chSort));
  $('#onlyviol').classList.toggle('on', chOnlyViol);
  VIOL_TIPS = {};

  const list = chapterList(d);
  const truncated = !showAllChapters && list.length > CHAPTER_LIMIT;
  const shown = truncated ? list.slice(0, CHAPTER_LIMIT) : list;

  let ch = '<div class="crow head"><div class="t">章</div>' +
    '<div class="v">字数</div><div class="v">真人感</div><div class="v">人味</div>' +
    '<div class="v">代入</div><div class="v">节奏</div><div class="v">句法</div>' +
    '<div class="v">总分</div></div>';
  for (const { c, i } of shown) {
    const t = esc(c.title);
    // role/tabindex/aria-expanded：章行可 Tab 到、回车展开明细，读屏能播报展开态
    ch += `<div class="crow" data-i="${i}" role="button" tabindex="0"
      aria-expanded="${expandedCh.has(i)}">
      <div class="t"><span class="twist">${expandedCh.has(i) ? '▾' : '▸'}</span>${t}</div>
      <div class="v">${c.chars}</div>
      <div class="v ${scCls(c.score.real)}">${c.score.real.toFixed(1)}</div>
      <div class="v ${scCls(c.score.human)}">${c.score.human.toFixed(1)}</div>
      <div class="v ${scCls(c.score.imm)}">${c.score.imm.toFixed(1)}</div>
      <div class="v ${scCls(c.score.rhy)}">${c.score.rhy.toFixed(1)}</div>
      <div class="v ${scCls(c.score.syn)}">${c.score.syn.toFixed(1)}</div>
      <div class="v ${scCls(c.score.total)}">${c.score.total.toFixed(1)}</div>
    </div>`;
    if (c.violations && c.violations.length) {
      // 违规名做成芯片：点/悬停用同一气泡看完整 detail，不再靠原生 title。
      ch += '<div class="viol">⚠ ' + c.violations.map((v, vi) => {
        const vk = `v${i}-${vi}`;
        VIOL_TIPS[vk] = { name: v.name, desc: v.detail };
        return `<button type="button" class="vchip" data-k="${vk}"` +
          ` aria-label="${esc(v.name)} 的违规详情">${esc(v.name)}</button>`;
      }).join('、') + '</div>';
    }
    if (expandedCh.has(i)) ch += chapterDetailHTML(d, c);
  }
  if (truncated) {
    ch += `<div class="crow showall" role="button" tabindex="0">显示全部 ${list.length} 章（当前只列前 ${CHAPTER_LIMIT}；可改按「总分最低」排序让问题章排前）</div>`;
  }
  if (!shown.length) {
    ch = '<div class="chempty">没有符合条件的章。</div>';
  }
  $('#chapters').innerHTML = ch;
}

// 五维雷达：实线=你，朱砂虚线=标杆。SVG 手绘零依赖；颜色用 CSS 变量
// （必须走 style 属性——SVG 表现属性不支持 var()），明暗主题自动跟随。
function renderRadar(d) {
  const C = 95, R = 72, N = d.dims.length;
  const pt = (i, v) => {
    const a = -Math.PI / 2 + i * 2 * Math.PI / N;
    const r = R * Math.max(0, Math.min(10, v)) / 10;
    return [C + r * Math.cos(a), C + r * Math.sin(a)];
  };
  const poly = vals => vals.map((v, i) =>
    pt(i, v).map(x => x.toFixed(1)).join(',')).join(' ');
  // ⚠ 用 role="group" 而非 "img"：img 是叶子节点，会把里面的可聚焦顶点
  //（.rvhit，每个都是一次维度筛选）整个从无障碍树里抹掉。
  let svg = '<svg viewBox="-16 -10 222 202" role="group" ' +
    `aria-label="五维雷达：实线为你，朱砂虚线为标杆${PREV ? '，灰虚线为上次检测' : ''}。五个顶点可聚焦，回车只看该维度">`;
  for (const f of [0.25, 0.5, 0.75, 1]) {
    svg += `<polygon points="${poly(d.dims.map(() => 10 * f))}" ` +
      'style="fill:none;stroke:var(--line);stroke-width:1"/>';
  }
  // 环线刻度值：不标的话读者不知道每一环代表几分
  for (const f of [0.25, 0.5, 0.75, 1]) {
    const [, ry] = pt(0, 10 * f);
    svg += `<text x="${(C + 5).toFixed(1)}" y="${(ry + 3).toFixed(1)}" ` +
      `style="font:9px var(--mono);fill:var(--dim)">${(10 * f).toFixed(1)}</text>`;
  }
  for (let i = 0; i < N; i++) {
    const [x, y] = pt(i, 10);
    svg += `<line x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" ` +
      'style="stroke:var(--line);stroke-width:1"/>';
  }
  svg += `<polygon points="${poly(d.dims.map(k => d.bench[k]))}" ` +
    'style="fill:none;stroke:var(--verm);stroke-width:1.5;stroke-dasharray:4 3"/>';
  // 上次检测的五边形（灰虚线）：改稿重测时，两层的胀缩就是修改的效果
  if (PREV && PREV.summary) {
    svg += `<polygon points="${poly(d.dims.map(k => PREV.summary[k] ?? 0))}" ` +
      'style="fill:none;stroke:var(--dim);stroke-width:1;stroke-dasharray:2 3"/>';
  }
  svg += `<polygon points="${poly(d.dims.map(k => d.summary[k]))}" ` +
    'style="fill:var(--accent-soft);stroke:var(--accent);stroke-width:2;stroke-linejoin:round"/>';
  // 顶点圆点 + 透明命中区：点击 = 与五维卡一致的维度筛选
  for (let i = 0; i < N; i++) {
    const k = d.dims[i];
    const [vx, vy] = pt(i, d.summary[k]);
    const sel = dimSel.has(k);
    svg += `<circle cx="${vx.toFixed(1)}" cy="${vy.toFixed(1)}" r="3.2" ` +
      `style="fill:${sel ? 'var(--accent)' : 'var(--card)'};stroke:var(--accent);stroke-width:1.2"/>`;
    // tabindex/role/aria-label：SVG 元素也能聚焦。但**键盘主入口是五维卡**
    //（功能完全相同、语义更标准），这里只是让不用鼠标的人也能操作雷达。
    svg += `<circle cx="${vx.toFixed(1)}" cy="${vy.toFixed(1)}" r="11" fill="transparent" ` +
      `class="rvhit" data-dim="${k}" role="button" tabindex="0" ` +
      `aria-label="${d.dimlabel[k]}：你 ${d.summary[k].toFixed(2)}，标杆 ${d.bench[k].toFixed(2)}，回车只看该维度" ` +
      `style="cursor:pointer">` +
      `<title>${d.dimlabel[k]}：你 ${d.summary[k].toFixed(2)} · 标杆 ${d.bench[k].toFixed(2)} · 点击只看该维度</title></circle>`;
  }
  for (let i = 0; i < N; i++) {
    const [x, y] = pt(i, 10);
    const lx = C + (x - C) * 1.17, ly = C + (y - C) * 1.17;
    const k = d.dims[i];
    svg += `<text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="middle" ` +
      `style="font:700 10px var(--serif);fill:var(--dim)">${d.dimlabel[k]} ` +
      `${d.summary[k].toFixed(1)}</text>`;
  }
  svg += '</svg>';
  $('#radar').innerHTML = svg;
}

// 逐章趋势带：总分折线 + 朱砂标杆虚线。回答「从第几章开始掉」——
// 数字表看不出趋势。y 轴数据驱动（分数集中在 3–9 时，固定 0–10 会把
// 变化压扁）；章数超过 1200 按窗口聚合，SVG 点数可控。
// preserveAspectRatio=none 让折线铺满容器宽度，线宽用 vector-effect
// 锁定不随拉伸变形；hover / click 定位到对应章行。
function renderTrend(d) {
  const el = $('#trend');
  const list = d.chapters;                    // 原文顺序 = 叙事时间轴
  if (list.length < 3) { el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  const totals = list.map(c => c.score.total);
  const STEP = Math.max(1, Math.ceil(list.length / 1200));
  const pts = [];
  for (let i = 0; i < list.length; i += STEP) {
    const seg = totals.slice(i, i + STEP);
    pts.push({ i, v: seg.reduce((a, b) => a + b, 0) / seg.length });
  }
  const lo = Math.max(0, Math.floor(Math.min(...totals) - 0.6));
  const hi = Math.min(10, Math.ceil(Math.max(...totals) + 0.6));
  const bench = d.bench.total;
  const W = 1000, H = 150, PL = 6, PR = 6, PT = 12, PB = 6;
  const X = k => PL + (W - PL - PR) * (pts.length === 1 ? 0.5 : k / (pts.length - 1));
  const Y = v => PT + (H - PT - PB) * (1 - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo || 1));
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" ` +
    `aria-label="逐章总分趋势：实线为各章总分，虚线为标杆 ${bench.toFixed(2)}">`;
  for (let g = lo + 1; g < hi; g++) {
    svg += `<line x1="${PL}" y1="${Y(g).toFixed(1)}" x2="${W - PR}" y2="${Y(g).toFixed(1)}" ` +
      `style="stroke:var(--line);stroke-width:1" vector-effect="non-scaling-stroke"/>`;
  }
  if (bench >= lo && bench <= hi) {
    svg += `<line x1="${PL}" y1="${Y(bench).toFixed(1)}" x2="${W - PR}" y2="${Y(bench).toFixed(1)}" ` +
      `style="stroke:var(--verm);stroke-width:1.5;stroke-dasharray:6 4" vector-effect="non-scaling-stroke"/>`;
  }
  svg += `<polyline points="${pts.map((p, k) =>
    `${X(k).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' ')}" fill="none" ` +
    `style="stroke:var(--accent);stroke-width:2" vector-effect="non-scaling-stroke"/>`;
  svg += '</svg>';
  // 最低章标记（写作者最关心「最差的那章」）
  let minK = 0;
  pts.forEach((p, k) => { if (p.v < pts[minK].v) minK = k; });
  const minPctX = (X(minK) / W * 100).toFixed(2), minPctY = (Y(pts[minK].v) / H * 100).toFixed(2);
  el.innerHTML =
    `<div class="trend-legend"><span>总分（逐章，纵轴 ${lo}–${hi} 分）</span>` +
    `<span class="tl-bench">┄ 标杆 ${bench.toFixed(2)}</span>` +
    `<span>朱砂圆点 = 最低章 · 点击折线定位到章行</span></div>` +
    `<div class="trend-plot">${svg}` +
    `<div class="trend-min" style="left:${minPctX}%;top:${minPctY}%"></div>` +
    `<div class="trend-cross" hidden></div><div class="trend-tip" hidden></div></div>`;
  const plot = el.querySelector('.trend-plot');
  const cross = el.querySelector('.trend-cross');
  const tip = el.querySelector('.trend-tip');
  // ⚠ 缓存 rect：getBoundingClientRect 会强制重排，原来每次 mousemove 都调一次
  // （趋势带最多 1200 点，鼠标一动 = 一次重排 + 一次 O(n) 扫描）。
  // 200ms 内复用，滚动/缩放后最多滞后 200ms —— 视觉上无感，但省掉绝大部分重排。
  let rectCache = null, rectAt = 0;
  const plotRect = () => {
    const now = performance.now();
    if (!rectCache || now - rectAt > 200) {
      rectCache = plot.getBoundingClientRect();
      rectAt = now;
    }
    return rectCache;
  };
  // ⚠ X(k) 是 k 的线性函数（见上方定义），故 X 随 k 单调递增 → 二分查找。
  // 原来是对全部点做 forEach 线性扫描，1200 点时每次移动要算 1200 次。
  const nearest = clientX => {
    const rect = plotRect();
    const vx = (clientX - rect.left) / rect.width * W;
    let a = 0, b = pts.length - 1;
    while (b - a > 1) {
      const mid = (a + b) >> 1;
      if (X(mid) < vx) a = mid; else b = mid;
    }
    return Math.abs(X(a) - vx) <= Math.abs(X(b) - vx) ? a : b;
  };
  // ⚠ rAF 节流：mousemove 触发频率远高于渲染帧率，不节流会做大量无用计算。
  let pendingX = null, rafId = 0;
  const drawAt = () => {
    rafId = 0;
    if (pendingX === null) return;
    const bi = nearest(pendingX), p = pts[bi];
    const pctX = (X(bi) / W * 100).toFixed(2);
    cross.style.left = pctX + '%'; cross.hidden = false;
    tip.style.left = pctX + '%';
    const py = Y(p.v) / H * 100;
    tip.style.top = py < 30 ? `calc(${py.toFixed(2)}% + 14px)` : `calc(${py.toFixed(2)}% - 30px)`;
    tip.textContent = `第 ${p.i + 1} 章 · ${p.v.toFixed(2)}`;
    tip.hidden = false;
  };
  const move = ev => {
    pendingX = ev.clientX;
    if (!rafId) rafId = requestAnimationFrame(drawAt);
  };
  const leave = () => {
    pendingX = null;
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    cross.hidden = true; tip.hidden = true;
  };
  const locate = ev => {
    const ci = pts[nearest(ev.clientX)].i;
    chSort = 'orig'; chOnlyViol = false;
    if (list.length > CHAPTER_LIMIT) showAllChapters = true;   // 定位需要该章在渲染窗口内
    renderChapters(d);
    let row = document.querySelector(`#chapters .crow[data-i="${ci}"]`);
    if (!row) return;
    if (!expandedCh.has(ci)) { expandedCh.add(ci); renderChapters(d); }
    row = document.querySelector(`#chapters .crow[data-i="${ci}"]`);
    if (row) {
      row.scrollIntoView({ block: 'center', behavior: 'smooth' });
      row.classList.remove('flash'); void row.offsetWidth; row.classList.add('flash');
    }
  };
  plot.addEventListener('mousemove', move);
  plot.addEventListener('mouseleave', leave);
  plot.addEventListener('touchmove', ev => { move(ev.touches[0]); }, { passive: true });
  plot.addEventListener('touchend', leave);
  plot.addEventListener('click', locate);
}

function render(d) {
  $('#empty').hidden = true;
  $('#result').hidden = false;

  const s = d.summary;
  $('#meta').textContent =
    `${s.chapters} 章　·　${s.chars.toLocaleString()} 字`;

  // 短文本提示：每千字密度在短文本上被外推放大，分数失真（README 已声明
  // 不适用短篇，工具自己也要说出口）。
  $('#shortwarn').hidden = s.chars >= 1000;

  // 总分单独成卡：先给结论，再往下看五维与逐项。
  const tv = s.total, tb = d.bench.total;
  const tcls = scCls(tv), tj = itemTag(tv, tb);
  const tpct = Math.max(0, Math.min(100, tv * 10));
  const tbmark = Math.max(0, Math.min(100, tb * 10));
  const pv = PREV && PREV.summary ? PREV.summary.total : null;
  const pMark = pv == null ? '' :
    `<span class="tc-ghost" style="left:${Math.max(0, Math.min(100, pv * 10))}%" title="上次 ${pv.toFixed(2)}"></span>`;
  const prevFoot = pv == null ? '' :
    `　·　上次 ${pv.toFixed(2)}（${prevAgo(PREV.ts)}）${deltaHTML(tv, pv)}`;
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
          ${pMark}
        </div>
        <div class="tc-foot">
          <span>标杆 ${tb.toFixed(2)}　·　竖线为基准位置${prevFoot}</span>
          <span class="tc-tag ${tj.cls}">${tj.tag}</span>
        </div>
      </div>
    </div>`;

  renderFixbar(d);
  renderTrend(d);
  renderRadar(d);
  renderScores(d);
  renderMetrics(d);
  renderChapters(d);
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
  // 服务端同步计算，超长文本可能要等一会；2 分钟无响应按超时处理，
  // 否则按钮永远停在「检测中…」。
  const ctrl = new AbortController();
  const killTimer = setTimeout(() => ctrl.abort(), 120000);
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // light：省略每章的原始指标（前端只在汇总层用到），大书响应体减半
      body: JSON.stringify({ text, light: true }),
      signal: ctrl.signal
    });
    // ⚠ 非 2xx 也要先把 body 读出来：server 把真实原因放在 {"error": "..."} 里
    //（如「内容太短」「章节数超限」）。直接抛 status 会让用户只看到「500」，
    // 真正的原因被吞掉。
    if (!r.ok) {
      let detail = '';
      try {
        const e = await r.json();
        if (e && e.error) detail = `：${e.error}`;
      } catch (_) { /* body 不是 JSON 就算了，别让解析失败盖住原始错误 */ }
      throw new Error(`检测失败（HTTP ${r.status}）${detail}`);
    }
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    LAST = d;
    // 新结果重置逐章视图（维度筛选与排序偏好保留）。
    expandedCh.clear();
    showAllChapters = false;
    chOnlyViol = false;
    chSort = 'orig';
    render(d);
    // 本轮渲染用的是上一次的 PREV；渲染完把本轮存起来，供下一次对比
    PREV = { ts: Date.now(), summary: d.summary, bench: d.bench };
    savePrev(d);
    // 窄屏单列布局：结果在输入框下方，完成后自动滚过去，别让用户找
    if (window.innerWidth <= 960) {
      $('#result').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
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
    const reason = e && e.name === 'AbortError'
      ? '检测超时（120 秒）。正文可能过长，请拆分后分批检测。'
      : (e && e.message ? e.message : '未知错误');
    $('#hint').textContent = `检测失败：${reason}`;
    popup('检测失败', `检测没有完成。\n\n原因：${reason}\n\n请检查输入内容或重新载入文件后再试。`, 'error');
  } finally {
    clearTimeout(killTimer);
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

// 文件解码：网文 txt 大量是 GBK/GB18030（也有带 BOM 的 UTF-16），按 UTF-8 硬解
// 会整篇变成乱码——乱码拆不出章，却仍会产出一套看似正常的分数，用户毫无线索。
// 所以先严格按 UTF-8 解（fatal，非法序列即抛错），失败再退 gb18030（覆盖
// GBK/GB2312/GB18030 全族）；带 BOM 的 UTF-16 按 BOM 解。TextDecoder 是浏览器
// 内置（Encoding Standard），仍保持零依赖。
function decodeFile(buf) {
  const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  if (u8.length >= 2 && u8[0] === 0xFF && u8[1] === 0xFE)
    return { text: new TextDecoder('utf-16le').decode(u8), enc: 'UTF-16LE' };
  if (u8.length >= 2 && u8[0] === 0xFE && u8[1] === 0xFF)
    return { text: new TextDecoder('utf-16be').decode(u8), enc: 'UTF-16BE' };
  try {
    return { text: new TextDecoder('utf-8', { fatal: true }).decode(u8), enc: 'UTF-8' };
  } catch (e) {
    return { text: new TextDecoder('gb18030').decode(u8), enc: 'GB18030' };
  }
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
  let done = 0, buf = [], encs = [], failed = [];
  // 全部读完后的统一收尾。抽成函数是为了让 onload / onerror **共用同一个计数
  // 出口**——否则任一文件读失败时 done 永远到不了 list.length，聚合回调不触发，
  // UI 会一直卡在「读取中…」且没有任何提示。
  const finish = () => {
    const joined = buf.join('\n\n');
    // 非 UTF-8 文件必须点名，否则「转码成功」对用户不可见
    const encSet = [...new Set(encs.filter(e => e && e !== 'UTF-8'))];
    const encNote = encSet.length
      ? `${encs.filter(e => e && e !== 'UTF-8').length} 个文件按 ${encSet.join('、')} 解码`
      : '';
    if (sourceName) {
      loadedText = joined;
      loadedFolder = sourceName;
      showSource({
        name: sourceName,
        kind: sourceKind,
        files: list.length,
        skipped,
        encNote,
        formats: [...new Set(list.map(x => (x.name.match(/\.[^.]+$/) || [''])[0].toLowerCase()))].join('、') || '无',
        chars: joined.replace(/\s/g, '').length
      });
      // 不清空输入框：run() 会把来源与手动内容合并检测，
      // 与「移除来源时保留手动内容」保持同一设计。
    } else {
      loadedText = null;
      loadedFolder = '';
      loadedMeta = null;
      $('#sourcebar').hidden = true;
      $('#text').value = joined;
    }
    $('#hint').textContent = sourceName
      ? `已载入 ${list.length} 个文件${encNote ? '，' + encNote : ''}；章节以检测结果为准，输入框内容会一起检测`
      : `已载入 ${list.length} 个文件${encNote ? '，' + encNote : ''}` +
      (skipped ? `（跳过 ${skipped} 个非文本文件）` : '');
    if (failed.length) {
      popup('部分文件读取失败',
        `有 ${failed.length} 个文件没能读出来，已跳过：\n\n` +
        failed.slice(0, 8).join('\n') +
        (failed.length > 8 ? `\n…另有 ${failed.length - 8} 个` : ''),
        'error');
    }
  };
  list.forEach((f, i) => {
    const rd = new FileReader();
    const settle = () => { if (++done === list.length) finish(); };
    rd.onload = () => {
      const d = decodeFile(rd.result);
      buf[i] = d.text;
      encs[i] = d.enc;
      settle();
    };
    rd.onerror = () => {
      failed.push(f.name);
      buf[i] = '';
      encs[i] = '';
      settle();
    };
    rd.readAsArrayBuffer(f);
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
  // 复制逐章：应用当前排序 / 违规过滤后的逐章分数表，与逐章列表同一数据源。
  $('#chcopy').onclick = async () => {
    if (!LAST) return;
    const ok = await copyText(buildChaptersCopy(LAST));
    if (ok) {
      const btn = $('#chcopy'), old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(() => { btn.textContent = old; }, 1400);
    } else {
      popup('复制失败', '浏览器没有放行剪贴板写入，请手动选中内容复制。', 'error');
    }
  };
  // 点维度卡切换选中；选中后逐项对比只显示这些维度覆盖的指标。
  $('#scores').addEventListener('click', e => {
    const el = e.target.closest('.sc[data-dim]');
    if (!el || !LAST) return;
    const k = el.dataset.dim;
    if (dimSel.has(k)) dimSel.delete(k); else dimSel.add(k);
    // ⚠ 重新渲染会替换掉整个 #scores，焦点随之丢失——键盘用户按一次 Enter
    // 就得重新 Tab 一遍。原来有焦点的话，按维度名找回新元素把焦点还回去。
    const hadFocus = document.activeElement === el;
    renderScores(LAST);
    renderMetrics(LAST);
    if (hadFocus) {
      const again = document.querySelector(`.sc[data-dim="${k}"]`);
      if (again) again.focus();
    }
  });
  // 雷达顶点：与五维卡同款的维度筛选（点击切换选中维度）
  $('#radar').addEventListener('click', e => {
    const el = e.target.closest('.rvhit[data-dim]');
    if (!el || !LAST) return;
    const k = el.dataset.dim;
    if (dimSel.has(k)) dimSel.delete(k); else dimSel.add(k);
    const hadFocus = document.activeElement === el;
    renderScores(LAST); renderMetrics(LAST); renderRadar(LAST);
    if (hadFocus) {
      const again = document.querySelector(`.rvhit[data-dim="${k}"]`);
      if (again) again.focus();
    }
  });
  // 「按维度 / 按差距」排序切换：渲染与复制共用 buildTableRows，同步生效。
  $('#sortseg').addEventListener('click', e => {
    const btn = e.target.closest('button[data-sort]');
    if (!btn) return;
    sortMode = btn.dataset.sort;
    if (LAST) renderMetrics(LAST);
  });
  // 「最该先改」摘要条：维度芯片 → 选中该维并滚到分组头；指标芯片 → 跳到该行；
  // 违规芯片 → 打开逐章的违规过滤并展开第一章。
  $('#fixbar').addEventListener('click', e => {
    const chip = e.target.closest('.fx-chip');
    if (!chip || !LAST) return;
    if (chip.dataset.dim) {
      dimSel.add(chip.dataset.dim);
      renderScores(LAST);
      renderMetrics(LAST);
      const g = document.querySelector(`.mgroup[data-dim="${chip.dataset.dim}"]`);
      if (g) {
        g.scrollIntoView({ block: 'start', behavior: 'smooth' });
        g.classList.remove('flash'); void g.offsetWidth; g.classList.add('flash');
      }
    } else if (chip.dataset.k) {
      jumpToItem(LAST, chip.dataset.k);
    } else if (chip.dataset.viol) {
      chOnlyViol = true;
      showAllChapters = true;
      renderChapters(LAST);
      const first = document.querySelector('#chapters .crow[data-i]');
      if (first) first.click();
      $('#chapters').scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  });
  // 逐章工具条：排序与违规过滤。
  $('#chsortseg').addEventListener('click', e => {
    const btn = e.target.closest('button[data-chsort]');
    if (!btn) return;
    chSort = btn.dataset.chsort;
    if (LAST) renderChapters(LAST);
  });
  $('#onlyviol').addEventListener('click', () => {
    chOnlyViol = !chOnlyViol;
    if (LAST) renderChapters(LAST);
  });
  // 逐章列表：点行展开问题明细，点芯片跳到对应指标行，点尾行显示全部。
  $('#chapters').addEventListener('click', e => {
    if (!LAST) return;
    if (e.target.closest('.showall')) {
      showAllChapters = true;
      renderChapters(LAST);
      return;
    }
    const chip = e.target.closest('.fx-chip[data-k]');
    if (chip) {
      jumpToItem(LAST, chip.dataset.k);
      return;
    }
    const crow = e.target.closest('.crow[data-i]');
    if (!crow) return;
    const i = +crow.dataset.i;
    // 明细插在章行（或其违规行）之后；再点一次收起。
    const next = crow.nextElementSibling;
    const afterViol = next && next.classList.contains('viol')
      ? next.nextElementSibling : next;
    if (afterViol && afterViol.classList.contains('chdetail')) {
      afterViol.remove();
      expandedCh.delete(i);
      crow.querySelector('.twist').textContent = '▸';
      // ⚠ 这条路径是**直接改 DOM**（不重新渲染），所以 aria-expanded 必须手动同步，
      // 否则读屏会一直播报「已展开」而实际已收起。
      crow.setAttribute('aria-expanded', 'false');
    } else {
      crow.insertAdjacentHTML('afterend', chapterDetailHTML(LAST, LAST.chapters[i]));
      expandedCh.add(i);
      crow.querySelector('.twist').textContent = '▾';
      crow.setAttribute('aria-expanded', 'true');
    }
  });
  // 气泡触发：鼠标走悬停、键盘走聚焦、触屏走点按，按指针类型分流。
  // 挂在 document 上做事件委托，同时覆盖逐项表的 .qi 和逐章列表的违规
  // .vchip——两处共用同一个气泡。
  //
  // 用 pointerover / pointerout（会冒泡、且带 pointerType），**不用** mouseover /
  // mouseout：触屏点按后浏览器会补发一整套兼容鼠标事件，其中末尾那个 mouseout
  // 会把刚点开的气泡立刻关掉，表现为「点了没反应」。
  const tipOf = e => (e.target.closest ? e.target.closest('.qi, .vchip') : null);
  document.addEventListener('pointerover', e => {
    if (e.pointerType === 'touch') return;
    const qi = tipOf(e);
    if (qi) showTip(qi);
  });
  document.addEventListener('pointerout', e => {
    if (e.pointerType === 'touch') return;
    const qi = tipOf(e);
    if (!qi) return;
    if (e.relatedTarget && qi.contains(e.relatedTarget)) return;
    scheduleHide();
  });
  document.addEventListener('focusin', e => {
    const qi = tipOf(e);
    if (qi) showTip(qi);
  });
  document.addEventListener('focusout', e => {
    if (tipOf(e)) scheduleHide();
  });
  // 键盘敲 Enter / Space：原生 <button> 会合成 click，其 event.detail 恒为 0。
  // 用它跟鼠标点击区分开——鼠标点击不参与（鼠标走 hover）。
  // 也补上「Esc 收起后元素仍是聚焦态、focusin 不会再触发」这个缺口。
  document.addEventListener('click', e => {
    if (e.detail !== 0) return;
    const qi = tipOf(e);
    if (!qi) return;
    e.preventDefault();
    if (tipEl().dataset.k === qi.dataset.k && !tipEl().hidden) hideTip();
    else showTip(qi);
  });
  // 触屏：同一目标再点一次收起。鼠标与键盘不参与（分别是 hover / focus）。
  document.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'touch') return;
    const qi = tipOf(e);
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
    if (e.target.closest('.qi, .vchip') || e.target.closest('#tip')) return;
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
  // ⚠ 两处都：先把 FileList 展开成数组（同步复制），再清空 input.value——
  // 否则选同一个文件/文件夹第二次不触发 onchange（value 没变，浏览器认为无变化）。
  // 顺序不能反：直接清 value 会同时清空 FileList，异步的 FileReader 就拿不到文件了。
  $('#file').onchange = e => {
    const fs = [...e.target.files];
    e.target.value = '';
    if (fs.length) {
      const name = fs.length === 1 ? fs[0].name : `${fs.length} 个文件`;
      loadFiles(fs, name, 'file');
    }
  };
  $('#dir').onchange = e => {
    const fs = [...e.target.files];
    e.target.value = '';
    if (fs.length) {
      const p = fs[0].webkitRelativePath || '';
      loadFiles(fs, p.split('/')[0] || '文件夹');
    }
  };
  bindDrop($('#text'));
  bindPaste($('#text'));
  $('#text').addEventListener('input', () => {
    if (loadedText === null && $('#text').value.trim()) {
      // 手打输入的即时反馈只能算预估：拆章选型以后端为准，这里注明。
      const n = countChapters($('#text').value);
      $('#hint').textContent = `输入内容 · 预估 ${n || '未分章'} 章 · 以检测为准`;
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closePopup(); hideTip(); }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run();
    // 键盘可达性：Enter / Space 等价于点击。只处理显式标了 role="button"
    // 的委托目标（五维卡 / 雷达顶点 / 逐章行 / 「显示全部」），其余一律放行。
    // ⚠ 必须排除 meta/ctrl/alt —— 否则 Cmd+Enter 会在这里被吃掉，
    // 变成「既触发 run() 又触发元素 click()」的双重动作。
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    const t = e.target;
    if (!t || typeof t.matches !== 'function') return;
    if (!t.matches('[role="button"][tabindex]')) return;
    e.preventDefault();                 // Space 默认会滚动页面，必须挡掉
    t.click();
  });
});
