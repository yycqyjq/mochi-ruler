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
    # 真人感（19）
    'vague', 'nego', 'dash', 'rev', 'enum', 'simile', 'sent_den', 'para_med',
    'short_run', 'tail', 'bold', 'dede', 'isde', 'onomat', 'space',
    'short', 'head', 'tell', 'cv',
    # 节奏（5）
    'sent_p90', 'sent_p10', 'comma_in', 'lit', 'para_cv',
    # 人味（5）
    'emo', 'net_oral', 'net_dial', 'exclaim', 'redupl',
    # 代入感（5）
    'imm_cog', 'imm_perc', 'imm_soma', 'imm_lim', 'breath',
    # 句法（4）
    'pron3', 'pron_start', 'sent_med', 'g_turn',
]

# 逐项指标的中文名（只保留展示的 SHOW 项）。五维的中文名见 DIM_LABEL。
_RAW = dict(q.BENCH_LABEL)
_RAW.update({
    'dede': '的的连用', 'isde': '是…的句', 'onomat': '拟声词',
    'space': '空间定位', 'breath': '呼吸心跳', 'exclaim': '感叹号',
    'redupl': '叠词', 'comma_in': '句内逗号',
})
LABEL = {k: _RAW[k] for k in SHOW if k in _RAW}

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

    # 全书汇总（中位）
    def med(v):
        v = sorted(v)
        return v[len(v) // 2]

    total_chars = sum(c['chars'] for c in out)
    summary = {'chapters': len(out), 'chars': total_chars}
    for k in DIMS + ['total']:
        summary[k] = med([c['score'][k] for c in out])
    summary['metrics'] = {k: med([c['metrics'][k] for c in out]) for k in SHOW}
    summary['items'] = {k: med([c['items'][k] for c in out]) for k in SHOW}

    # 标杆基准（预置基准中位，口径与上面一致）。真人感 = 10 − 旧「AI 味」。
    bench = {
        'real': 10 - med([q.BENCHMARKS[b]['ai'] for b in q.BENCHMARKS]),
        'human': med([q.BENCHMARKS[b]['human'] for b in q.BENCHMARKS]),
        'imm': med([q.BENCHMARKS[b]['imm'] for b in q.BENCHMARKS]),
        'rhy': med([q.BENCHMARKS[b]['rhythm'] for b in q.BENCHMARKS]),
        'syn': med([q.BENCHMARKS[b]['syn'] for b in q.BENCHMARKS]),
    }
    bench['total'] = q.score_total(bench)
    # 新增指标在冻结基准里没有存值（基准是一次性算定的，不能就地补），
    # 这类键一律给 None 让前端显示「—」，而不是拿 0 冒充标杆原始值。
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
