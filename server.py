#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 后端服务（零依赖，只用 Python 标准库）

启动：
    python3 server.py            # 默认 http://127.0.0.1:8765
    python3 server.py 9000       # 指定端口

接口：
    GET  /                  前端页面
    GET  /static/*          静态资源
    POST /api/analyze       分析文本，返回 JSON
"""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qc_core as q
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, 'static')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

# 按维度分组，组内顺序即展示顺序。这里只决定「展示哪些、按什么次序」，
# 不参与打分——权重与阈值一律以 qc_core 各维权重表为准。
SHOW = [
    # 真人感（20）
    'vague', 'nego', 'dash', 'rev', 'enum', 'simile', 'sent_den', 'para_med',
    'short_run', 'tail', 'bold', 'dede', 'isde', 'onomat', 'space',
    'short', 'head', 'tell', 'cv', 'dem_lit',
    # 节奏（5）
    'sent_p90', 'sent_p10', 'comma_in', 'lit', 'para_cv',
    # 人味（5）
    'emo', 'net_oral', 'net_dial', 'exclaim', 'redupl',
    # 代入感（6）。**展示项一律计分**——没有「展示了却不打分」的行：
    # `imm_lim`（受限标记）已于 2026-09-14 整体删除（无区分度：真人 0.25 / AI 0.25，
    # 章级分离 0.11，且判定带宽比数据跨度窄一个数量级）。详见 qc_core 的代入感注释。
    'imm_cog', 'imm_perc', 'imm_soma', 'breath', 'surprise', 'touch_temp',
    # 句法（5）
    'pron3', 'pron_start', 'sent_med', 'g_turn', 'conn_lit',
]

# 逐项指标的中文名（只保留展示的 SHOW 项）。五维的中文名见 DIM_LABEL。
_RAW = dict(q.BENCH_LABEL)
_RAW.update({
    'dede': '的的连用', 'isde': '是…的句', 'onomat': '拟声词',
    'space': '空间定位', 'breath': '呼吸心跳', 'exclaim': '感叹号',
    'redupl': '叠词', 'comma_in': '句内逗号',
})
LABEL = {k: _RAW[k] for k in SHOW if k in _RAW}

# 逐项指标的「口径说明」——鼠标悬停逐项对比里的 ? 时显示。
#
# 写法约定：**只写「数的是什么、怎么数、什么单位」**，都能从 qc_core 的正则与
# metrics() 逐条核对；不写理论解释，也不写「越高/越低越好」——后者由
# ITEM_TARGET 自动推出（见下面 _raw_dirs）。这样阈值一改，方向提示自动跟着
# 改，永远不会出现「说明文字与阈值打架」。
DESC_TEXT = {
    # 真人感（20）
    'vague': '含糊指代与虚写的词：在心里 / 过了很久 / 半晌 / 的时候 / 一会儿 / 片刻。每千字。',
    'nego': '「不是 A——B」式否定加破折号纠正。每千字。',
    'dash': '句末用破折号收束（——短句。）。每千字。',
    'rev': '「不是 A，是 B」反转句。每千字。',
    'enum': '顿号三连、或「有的…有的…」排比罗列。每千字。',
    'simile': '「像是 / 就像 / 仿佛 / 如同」等明喻。每千字。',
    'sent_den': '每千字句数。数值越高，句子切得越碎。',
    'para_med': '段落字数中位数（字）。',
    'short_run': '最长的连续短段串，单段 ≤12 字算短段，单位是「段」。',
    'tail': '段尾金句命中数 / 段落总数（比例）。',
    'bold': '正文里的 Markdown 加粗「**…**」个数（个）。',
    'dede': '一句里连用三个「的」。每千字。',
    'isde': '「是……的。」判断句。每千字。',
    'onomat': '拟声词：啪嗒 / 哗啦 / 咕噜 / 咚 / 唰。每千字。',
    'space': '方位词：左边 / 右边 / 上头 / 底下 / 跟前。每千字。',
    'short': '单段 ≤12 字的短段数 / 段落总数（比例）。',
    'head': '出现最多的那个句首词，其频次 / 句子总数（比例）。',
    'tell': '「他知道 / 她明白 / 他意识到」这类把心理直接讲出来的句式。每千字。',
    'cv': '句长变异系数（标准差 ÷ 均值）。越大说明长短句落差越大。',
    'dem_lit': '古典指示词「此 / 彼」，如 此时 / 此刻 / 此处 / 此番 / 此人。每千字。',
    # 节奏（5）
    'sent_p90': '第 90 百分位句长（字）。',
    'sent_p10': '第 10 百分位句长（字）。',
    'comma_in': '句内逗号「，」。每千字。',
    'lit': '文言虚词：之 / 乃 / 亦 / 矣 / 乎 / 者 / 则。每千字。',
    'para_cv': '段长变异系数（标准差 ÷ 均值）。',
    # 人味（5）
    'emo': '情绪词：笑 / 哭 / 怒 / 怕 / 惊 / 叹 / 骂。每千字。',
    'net_oral': '口语语气词：吧 / 啊 / 呢 / 嘛 / 啥 / 哎 / 唉。每千字。',
    'net_dial': '含引号的段落数 / 段落总数，即对话占比（比例）。',
    'exclaim': '感叹号「！」。每千字。',
    'redupl': '叠词（相邻两字重复）。每千字。',
    # 代入感（6）
    'imm_cog': '认知反应词：发现 / 意识到 / 愣住 / 回过神 / 忽然 / 猛地。每千字。',
    'imm_perc': '感知动词：看见 / 听到 / 闻到 / 摸到 / 觉得 / 看清。每千字。',
    'imm_soma': '躯体感受词：疼 / 麻 / 痒 / 抖 / 颤 / 汗 / 僵 / 闷。每千字。',
    'breath': '喘 / 呼吸 / 心跳 / 屏住 / 憋 / 胸口发闷。每千字。',
    'surprise': '意外与示证词：居然 / 竟然 / 不料 / 谁知 / 没想到 / 竟是。每千字。',
    'touch_temp': '触觉温度词：凉 / 烫 / 冰冷 / 刺痛 / 粗糙 / 光滑。每千字。',
    # 句法（5）
    'pron3': '第三人称代词「他 / 她 / 它」（不计「其他」）。每千字。',
    'pron_start': '以代词开头的句子数 / 句子总数（比例）。',
    'sent_med': '句长中位数（字）。',
    'g_turn': '转折连词：但是 / 可是 / 不过 / 却 / 反倒。每千字。',
    'conn_lit': '书面连接词：裸「但」/ 然而 / 因此 / 从而 / 故 / 遂 / 乃。每千字。',
}


def _raw_dir(k):
    """该指标原始值的升降方向，由阈值自动推出——不手写，就不会与阈值脱节。

    good(v, target, over)：达标值 target → 10 分，超标值 over → 0 分。所以
    target < over 时值是越小分越高（越低越好），target > over 时反过来。
    """
    t = q.ITEM_TARGET.get(k)
    if not t or t[0] == t[1]:
        return ''
    return '越低越好' if t[0] < t[1] else '越高越好'


# 只暴露 SHOW 项；缺口径说明的项会在启动时点名告警（见下方自检）。
DESC = {k: DESC_TEXT[k] for k in SHOW if k in DESC_TEXT}
RAW_DIR = {k: _raw_dir(k) for k in SHOW}

_missing = [k for k in SHOW if k not in DESC_TEXT]
if _missing:
    # 不静默：加新指标时忘了补口径说明，必须在这里被看见。
    print('[warn] SHOW 里有指标缺口径说明 DESC_TEXT：%s' % '、'.join(_missing),
          file=sys.stderr)

# 每个维度覆盖哪些展示指标，直接取自该维的权重表 —— 打分口径一变，
# 这里的筛选范围自动跟着变，不需要另维护一份清单。
DIM_ITEM_SRC = {'real': q.WEIGHTS, 'human': q.HUMAN_WEIGHTS,
                'imm': q.IMM_WEIGHTS, 'rhy': q.RHY_WEIGHTS,
                'syn': q.SYN_WEIGHTS}
DIM_ITEMS = {k: [m for m in SHOW if m in w] for k, w in DIM_ITEM_SRC.items()}

# 展示用分数：五维 + 总分。全部 0–10、越高越好。
DIMS = ['real', 'human', 'imm', 'rhy', 'syn']
DIM_LABEL = {'total': '总分', 'real': '真人感', 'human': '人味',
             'imm': '代入感', 'rhy': '节奏', 'syn': '句法'}


def _clean(o):
    """把 inf/nan 变成 JSON 安全值"""
    if isinstance(o, float):
        if o != o:
            return 0.0
        if o == float('inf'):
            return 999.0
        if o == float('-inf'):
            return -999.0
        return round(o, 4)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    return o


def analyze(text, name=''):
    """分析一段文本，返回结构化结果。

    所有分数统一 0–10、越高越好（越高越不像 AI 网文）：
      score = 每章 {real 真人感, human 人味, imm 代入感, rhy 节奏,
                   syn 句法, total 总分}
      items = 每章逐项分（SHOW 里每个指标一个 0–10）
      metrics = 每章原始指标值（仅供对照，用于悬停提示）
      desc / rawdir = 每项的口径说明与原始值升降方向（逐项对比的 ? 气泡）

    另有全书汇总 summary / bench / dimitems / label，供前端渲染对照表。
    """
    chs = q.split_chapters(text)
    chs = [(t, b) for t, b in chs if len(re.sub(r'\s', '', b)) >= 300]
    if not chs:
        chs = [('（整篇）', text)]
    out = []
    for title, body in chs:
        m = q.metrics(body)
        sc = {'real': q.score_real(m)[1], 'human': q.score_human(m)[1],
              'imm': q.score_imm(m)[1], 'rhy': q.score_rhy(m)[1],
              'syn': q.score_syn(m)[1]}
        sc['total'] = q.score_total(sc)
        comp = q.compliance(body, title)
        out.append({
            'title': title or '（未命名）',
            'chars': m['chars'],
            'score': sc,
            'metrics': {k: m.get(k, 0) for k in SHOW},
            'items': {k: q.item_score(k, m.get(k)) for k in SHOW},
            'violations': [{'name': k, 'detail': v} for k, v in comp],
        })

    # 全书汇总（中位）。展示项现在全部有阈值、逐项分不会为 None，但仍先滤掉
    # None 再取中位：万一将来出现无阈值项，也不会因 sorted([None]) 直接崩。
    def med(v):
        v = sorted(x for x in v if x is not None)
        return v[len(v) // 2] if v else None

    total_chars = sum(c['chars'] for c in out)
    summary = {'chapters': len(out), 'chars': total_chars}
    for k in DIMS + ['total']:
        summary[k] = med([c['score'][k] for c in out])
    summary['metrics'] = {k: med([c['metrics'][k] for c in out]) for k in SHOW}
    summary['items'] = {k: med([c['items'][k] for c in out]) for k in SHOW}

    # 标杆基准。BENCHMARKS 里只存原始指标中位，**五维分在运行时用当前公式
    # 算**——旧版存的是六个字面量死数（ai/human/imm/net/rhythm/syn），公式一改
    # 就与新口径脱节（net 撤编、g_turn 入库时都踩过）。现在口径永远自洽，
    # 新增指标也自动有基准，不需要回头补基准表。
    bench = {}
    for d, fn in (('real', q.score_real), ('human', q.score_human),
                  ('imm', q.score_imm), ('rhy', q.score_rhy),
                  ('syn', q.score_syn)):
        bench[d] = med([fn(q.BENCHMARKS[b])[1] for b in q.BENCHMARKS])
    bench['total'] = q.score_total(bench)

    def _bmed(k):
        vs = [q.BENCHMARKS[b][k] for b in q.BENCHMARKS if k in q.BENCHMARKS[b]]
        return med(vs) if vs else None

    bench['metrics'] = {k: _bmed(k) for k in SHOW}
    bi = {}
    for k in SHOW:
        vs = [q.item_score(k, q.BENCHMARKS[b].get(k)) for b in q.BENCHMARKS]
        vs = [v for v in vs if v is not None]
        bi[k] = med(vs) if vs else None
    bench['items'] = bi

    return _clean({
        'name': name or '未命名',
        'summary': summary,
        'bench': bench,
        'dims': DIMS,
        'dimlabel': DIM_LABEL,
        'items': SHOW,
        'label': LABEL,
        # 逐项对比里 ? 的气泡内容：口径说明 + 原始值升降方向（后者由阈值推出）。
        'desc': DESC,
        'rawdir': RAW_DIR,
        'dimitems': DIM_ITEMS,
        'chapters': out,
    })


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/' or p == '/index.html':
            return self._file(os.path.join(STATIC, 'index.html'),
                              'text/html; charset=utf-8')
        if p.startswith('/static/'):
            fn = os.path.basename(p)
            ct = ('text/css' if fn.endswith('.css') else
                  'application/javascript' if fn.endswith('.js') else
                  'text/plain')
            return self._file(os.path.join(STATIC, fn), ct + '; charset=utf-8')
        self._send(404, b'not found', 'text/plain')

    def _file(self, path, ctype):
        if not os.path.exists(path):
            return self._send(404, b'not found', 'text/plain')
        with open(path, 'rb') as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        if self.path.split('?')[0] != '/api/analyze':
            return self._send(404, b'not found', 'text/plain')
        n = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(n).decode('utf-8', 'ignore')
        try:
            req = json.loads(raw)
        except Exception:
            return self._send(400, b'bad json', 'text/plain')
        text = req.get('text', '')
        name = req.get('name', '')
        if not text.strip():
            return self._send(400, b'empty text', 'text/plain')
        try:
            res = analyze(text, name)
        except Exception as e:
            return self._send(500, json.dumps(
                {'error': str(e)}).encode('utf-8'),
                'application/json; charset=utf-8')
        self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8')


if __name__ == '__main__':
    print()
    print('  墨尺 · 网文质检')
    print('  ─────────────────────────────')
    print('  http://127.0.0.1:%d' % PORT)
    print('  Ctrl+C 停止')
    print()
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
