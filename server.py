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
VERSION = '1.0.0'
try:
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
except ValueError:
    sys.exit('端口必须是数字：%r\n用法：python3 server.py [端口]（默认 8765）' % sys.argv[1])
# 请求体上限：百万字长文足够（约 30MB），防异常大包把内存读爆。
MAX_BODY_BYTES = 64 * 1024 * 1024

# 按维度分组，组内顺序即展示顺序。这里只决定「展示哪些、按什么次序」，
# 不参与打分——权重与阈值一律以 qc_core 各维权重表为准。
SHOW = [
    # 真人感（18）。`head`（句首集中）已于 2026-09-14 整体删除：它的区分度
    # 100% 来自「段首全角缩进」这一排版差，剥掉缩进后分离度从 0.92 塌到 0.09。
    # 详见 qc_core 里 HEADWORD 的删除备忘。
    # `enum`（罗列）同日退出打分，理由**不是区分度**（sep 0.605 尚可）而是
    # 真人侧左尾：真人 24 本里 10 本项分 <5、5 本 <3。清退后该维分离度
    # 0.9842 → 0.9877、真人逐本最低分 8.27 → 8.50。详见 qc_core 的 GOOD_BAD。
    'vague', 'nego', 'dash', 'rev', 'simile', 'sent_den', 'para_med',
    'short_run', 'tail', 'bold', 'dede', 'isde', 'onomat', 'space',
    'short', 'tell', 'cv', 'dem_lit',
    # 节奏（6）。`punc_den`（停顿标点密度/千字）2026-09-15 新增：与 `comma_in`
    # **有意重叠**——两半方向相反，分开用都没收益（−0.0022 / +0.0021），
    # 合并成一个量再定阈才有效（Δ维sep +0.0116、左尾 +0.54）。
    # 详见 qc_core 的 RHY_GOOD_BAD 上方记录。
    'sent_p90', 'sent_p10', 'comma_in', 'lit', 'para_cv', 'punc_den',
    # 人味（7）
    'emo', 'net_oral', 'dial_sent', 'exclaim', 'redupl', 'question', 'emo_type',
    # 代入感（4）。**展示项一律计分**——没有「展示了却不打分」的行：
    # `imm_lim`（受限标记）已于 2026-09-14 整体删除（无区分度：真人 0.25 / AI 0.25，
    # 章级分离 0.11，且判定带宽比数据跨度窄一个数量级）。
    # `imm_cog`（认知反应）/ `imm_perc`（感知）/ `imm_soma`（身体感受）同日
    # **退出打分**，理由是「sep 低 + 压真人」：三项 sep 只有 0.23–0.31，
    # 却各压 7–10 本真人到 5 分以下，权重合计占该维 23%——既没用又伤人。
    # 清退后该维 sep 0.9239 → 0.9339、真人逐本最低分 4.95 → 5.23、<5 本数 1 → 0。
    # `act`（动作密度）同日**从「退出打分」名单里捞回来、入本维**：方向为反不是
    # 淘汰理由（good() 的达标值可小于超标值，取反即可用）。
    # 详见 qc_core 的 IMM_GOOD_BAD 上方整轮回标定记录。
    'breath', 'surprise', 'touch_temp', 'act',
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
    # 真人感（18）
    'vague': '含糊指代与虚写的词：在心里 / 过了很久 / 半晌 / 的时候 / 一会儿 / 片刻。每千字。',
    'nego': '「不是 A——B」式否定加破折号纠正。每千字。',
    'dash': '句末用破折号收束（——短句。）。每千字。',
    'rev': '「不是 A，是 B」反转句。每千字。',
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
    'tell': '「他知道 / 她明白 / 他意识到」这类把心理直接讲出来的句式。每千字。',
    'cv': '句长变异系数（标准差 ÷ 均值）。越大说明长短句落差越大。',
    'dem_lit': '古典指示词「此 / 彼」，如 此时 / 此刻 / 此处 / 此番 / 此人。每千字。',
    # 节奏（6）
    'sent_p90': '第 90 百分位句长（字）。',
    'sent_p10': '第 10 百分位句长（字）。',
    'comma_in': '句内逗号「，」。每千字。',
    'lit': '文言虚词：之 / 乃 / 亦 / 矣 / 乎 / 者 / 则。每千字。',
    'para_cv': '段长变异系数（标准差 ÷ 均值）。',
    'punc_den': '停顿标点总量：，。！？、；：…—。每千字。'
                '与「句内逗号」有意重叠——真人逗号更多、但标点总量更少，'
                '两者方向相反，合成后才有区分力。',
    # 人味（7）
    'emo': '情绪词：笑 / 哭 / 怒 / 怕 / 惊 / 叹 / 骂。每千字。',
    'net_oral': '口语语气词：吧 / 啊 / 呢 / 嘛 / 啥 / 哎 / 唉。每千字。',
    'dial_sent': '引号内句子的平均字数（字）。只统计成对引号内的文字，'
                 '引号不成对的段落不计；整章无对话时不打分（返回「无数据」，'
                 '人味维按其余项归一），而不是按 0 分惩罚。',
    'exclaim': '感叹号「！」。每千字。',
    'redupl': '叠词：相邻两字相同（AA 式，如「慢慢 / 轻轻 / 渐渐」）。每千字。'
              '只认汉字成对——不把全角空格、标点算进来。',
    'question': '问号「？」的个数，按每百句归一（对话与叙述一并计）。',
    'emo_type': '用到的不同情绪词种类数（笑/怒/惊/怕等 18 个单字 + 欣慰 / 无奈 / 尴尬 / '
                '疲惫等 31 个二字词），按每百句归一。'
                '与情绪词密度互为独立轴：密度被句长与文风绑架，种类数只看「写没写到多种情绪」。',
    # 代入感（4）
    'breath': '喘 / 呼吸 / 心跳 / 屏住 / 憋 / 胸口发闷。每千字。',
    'surprise': '意外与示证词：居然 / 竟然 / 不料 / 谁知 / 没想到 / 竟是 / 岂料 / '
                '出乎意料 / 始料未及 等，含裸「竟」（排除「毕竟 / 究竟」）。每千字。',
    'touch_temp': '触觉温度词：凉 / 烫 / 冰冷 / 刺痛 / 粗糙 / 光滑。每千字。',
    'act': '身体动作词：起身 / 扭头 / 转身 / 回头 / 抬手 / 点头 / 摇头 / 皱眉 / '
           '抓住 / 拍 / 踢 / 推 / 跑 / 停住 等。每千字。',
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

# 启动自检一：展示项必须同时有「口径说明」和「中文名」。
# 两处兜底都是 `if k in` 过滤 —— 漏了不会报错，只会静默留空，
# 所以必须在这里点名。加新指标时最容易漏的就是这两张表。
_missing_desc = [k for k in SHOW if k not in DESC_TEXT]
if _missing_desc:
    print('[warn] SHOW 里有指标缺口径说明 DESC_TEXT：%s' % '、'.join(_missing_desc),
          file=sys.stderr)
_missing_label = [k for k in SHOW if k not in LABEL]
if _missing_label:
    print('[warn] SHOW 里有指标缺中文名 LABEL：%s' % '、'.join(_missing_label),
          file=sys.stderr)

# 每个维度覆盖哪些展示指标，直接取自该维的权重表 —— 打分口径一变，
# 这里的筛选范围自动跟着变，不需要另维护一份清单。
DIM_ITEM_SRC = {'real': q.WEIGHTS, 'human': q.HUMAN_WEIGHTS,
                'imm': q.IMM_WEIGHTS, 'rhy': q.RHY_WEIGHTS,
                'syn': q.SYN_WEIGHTS}
DIM_ITEMS = {k: [m for m in SHOW if m in w] for k, w in DIM_ITEM_SRC.items()}

# 启动自检二：展示项必须在 `metrics()` 里真的取得到。
# `analyze` 用 `m[k]` 直取（缺键就报错，**不兜底**）—— 而 `metrics()` 对
# **任何输入**都无条件产出全部键（空串 / 单字 / 短句实测都是 47 键），
# 所以「缺键」只可能是代码写错（正则改名、误删一行），拿一段样本正文就能
# 在启动时抓出来，不必等某个请求炸掉。
#
# ⚠⚠ 这里原先写的是 `m.get(k, 0)`。那个兜底必须去掉：**40 项里有 22 项在
# 原始值为 0 时恰好给满分 10**（vague / nego / dash / rev / simile / sent_den /
# short_run / tail / bold / dede / isde / onomat / space / short / tell /
# punc_den / breath / touch_temp / act / pron3 / pron_start / conn_lit），
# 于是「提取被改坏」会被伪装成「满分」——正是本仓给外部检测器点名的
# 「特征缺失输出满分」缺陷原型（见 .workbuddy/notes/probes/mochi_ext23_defects.py）。
# README 也早已声明「漏键会让接口直接 500」，兜底是在跟这个设计意图打架。
_probe = q.metrics("他走了。")
_missing_metric = [k for k in SHOW if k not in _probe]
if _missing_metric:
    print('[warn] SHOW 里有指标在 metrics() 里取不到（接口会 500）：%s'
          % '、'.join(_missing_metric), file=sys.stderr)

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


def analyze(text, name='', light=False):
    """分析一段文本，返回结构化结果。

    所有分数统一 0–10、越高越好（越高越不像 AI 网文）：
      score = 每章 {real 真人感, human 人味, imm 代入感, rhy 节奏,
                   syn 句法, total 总分}
      items = 每章逐项分（SHOW 里每个指标一个 0–10）
      metrics = 每章原始指标值（仅供对照，用于悬停提示）
      desc / rawdir = 每项的口径说明与原始值升降方向（逐项对比的 ? 气泡）

    light=True 时省略**每章**的 metrics（原始值 40 键/章，前端只在全书汇总
    层用到它；几千章的书上这部分占了响应体的一半以上）。汇总层的
    summary.metrics 恒在。默认 light=False，regress.py 等工具拿到的输出
    与历史完全一致。

    另有全书汇总 summary / bench / dimitems / label，供前端渲染对照表。
    """
    chs = q.split_chapters(text)
    chs = [(t, b) for t, b in chs if len(re.sub(r'\s', '', b)) >= 300]
    if not chs:
        chs = [('（整篇）', text)]
    out = []
    raws = []
    for title, body in chs:
        m = q.metrics(body)
        raws.append(m)
        sc = {'real': q.score_real(m)[1], 'human': q.score_human(m)[1],
              'imm': q.score_imm(m)[1], 'rhy': q.score_rhy(m)[1],
              'syn': q.score_syn(m)[1]}
        sc['total'] = q.score_total(sc)
        comp = q.compliance(body, title)
        row = {
            'title': title or '（未命名）',
            'chars': m['chars'],
            'score': sc,
            # 直取，不兜底：缺键就该炸（启动自检二会先一步点名）。
            # 历史上这里是 `m.get(k, 0)`，会把缺键伪装成原始值 0，而 40 项里
            # 有 22 项取 0 即满分 —— 见启动自检二上方那段记录。
            'items': {k: q.item_score(k, m[k]) for k in SHOW},
            'violations': [{'name': k, 'detail': v} for k, v in comp],
        }
        if not light:
            row['metrics'] = {k: m[k] for k in SHOW}
        out.append(row)

    # 全书汇总（中位）。展示项现在全部有阈值、逐项分不会为 None，但仍先滤掉
    # None 再取中位：万一将来出现无阈值项，也不会因 sorted([None]) 直接崩。
    def med(v):
        v = sorted(x for x in v if x is not None)
        return v[len(v) // 2] if v else None

    total_chars = sum(c['chars'] for c in out)
    summary = {'chapters': len(out), 'chars': total_chars}
    for k in DIMS + ['total']:
        summary[k] = med([c['score'][k] for c in out])
    # 汇总层原始值从循环里的 m 取——light 模式裁掉每章 metrics 后它必须在
    summary['metrics'] = {k: med([r[k] for r in raws]) for k in SHOW}
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
    # keep-alive：_send 恒带准确 Content-Length，可安全复用连接。
    # timeout 回收空闲连接占用的线程。
    protocol_version = 'HTTP/1.1'
    timeout = 60

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
                  'image/svg+xml' if fn.endswith('.svg') else
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
        try:
            n = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            # body 未读，连接不能复用，显式关闭防下一个请求错位
            self.close_connection = True
            return self._send(400, b'bad content-length', 'text/plain')
        if n <= 0:
            self.close_connection = True
            return self._send(400, b'empty body', 'text/plain')
        if n > MAX_BODY_BYTES:
            self.close_connection = True
            return self._send(413, b'too large', 'text/plain')
        raw = self.rfile.read(n).decode('utf-8', 'ignore')
        try:
            req = json.loads(raw)
        except Exception:
            return self._send(400, b'bad json', 'text/plain')
        text = req.get('text', '')
        name = req.get('name', '')
        light = bool(req.get('light'))
        if not text.strip():
            return self._send(400, b'empty text', 'text/plain')
        try:
            res = analyze(text, name, light=light)
        except Exception as e:
            return self._send(500, json.dumps(
                {'error': str(e)}).encode('utf-8'),
                'application/json; charset=utf-8')
        self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8')


if __name__ == '__main__':
    print()
    print('  墨尺 · 网文质检 v%s' % VERSION)
    print('  ─────────────────────────────')
    print('  http://127.0.0.1:%d' % PORT)
    print('  Ctrl+C 停止')
    print()
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
