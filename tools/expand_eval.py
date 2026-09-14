#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 扩充指标收益评估（开发工具，不参与服务运行）

回答一个问题：**再加一个指标，到底让这一维更容易区分，还是更难**。

为什么要先问这个：把新指标加进某一维，**每个旧指标的权重份额必然被稀释**
——这是算术，与好坏无关。区分度取决于新轴的**信噪比**，不取决于指标个数。
判据（与 qc_core 的标定注释同源）：

    新指标的 sep（且残差 sep）必须 ≥ 该维现有的加权平均 sep，
    加进去才是净收益；低于这条线就是净损失。

而墨尺五维现在的 sep 已在 0.88–1.00 —— 余量极小，多数候选都会是负收益。
**所以本工具的主要作用是「劝退」，不是「找新指标」。**

用法：
    python3 tools/expand_eval.py --human <真人语料> --ai <AI语料> [--ai ...]
    python3 tools/expand_eval.py --human ~/标杆文章 --ai ~/ai1 ~/ai2 --fp

    --human   真人语料（目录或文件），必填
    --ai      AI 语料（目录或文件），可多个；`--ai A B` 与 `--ai A --ai B` 等价
    --per     每本最多抽多少章，默认 100（须与 bench_build.PERBOOK 一致）
    --fp      真人语料只保留 bench_build 里登记过内容指纹的 24 本
    --cand    只评估这几个候选（逗号分隔），默认全部

输出：
    1 各维当前分离度（基线）
    2 每个候选：真人跨本中位 / AI 中位 / sep / 残差 sep / 与目标维现有项的最大相关
      / 按该维平均权重加进去后的 Δ维sep
    3 一行纯噪声对照 —— **对照若也是正的，说明余量为零，任何 Δ 都在噪声里**

只依赖 Python 标准库。统计函数复用 tools/audit.py，维度分复算与 score_* 逐位自检。
"""

import argparse
import glob
import hashlib
import math
import os
import re
import statistics as st
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit                                # noqa: E402
import bench_build                          # noqa: E402
import qc_core as q                         # noqa: E402
import server as srv                        # noqa: E402

WSP = re.compile(r"\s")
QSTRIP = re.compile("[\u201c\u201d\u300c\u300d\u2018\u2019\"']")
SPLIT = re.compile(r"[。！？…]+")
PUNCT = set("，。！？、；：（）《》「」『』—…·【】\u201c\u201d\u2018\u2019\"'")
TAGS = ["说", "道", "问", "答", "喊", "叫", "吼", "嚷", "嘟囔", "嘀咕",
        "低语", "冷笑", "笑道", "叹"]

DIMS = {
    "real": (q.GOOD_BAD, q.WEIGHTS, {"cv": q.CV_RANGE}),
    "human": (q.HUMAN_GOOD_BAD, q.HUMAN_WEIGHTS, {}),
    "imm": (q.IMM_GOOD_BAD, q.IMM_WEIGHTS, {}),
    "rhy": (q.RHY_GOOD_BAD, q.RHY_WEIGHTS, {}),
    "syn": (q.SYN_GOOD_BAD, q.SYN_WEIGHTS, {}),
}
DIMNAME = {"real": "真人感", "human": "人味", "imm": "代入感",
           "rhy": "节奏", "syn": "句法"}


def _k(body):
    return max(len(WSP.sub("", body)), 1) / 1000.0


def _ent(counts):
    tot = sum(counts)
    if not tot:
        return 0.0
    return -sum((c / tot) * math.log2(c / tot) for c in counts if c > 0)


# ---------------------------------------------------------------- 候选指标库
# 全部来自对「工业级 48 规则检测器」的逐条实测复核（2026-09-14）。
# 括号里是实测 sep，只有 ≥0.6 的才值得往下看。

def c_num_quant(body):
    """数字+量词密度/千字。真人 6.09 / AI 12.55，sep 0.80，残差 0.81，
    与真人感现有项最大相关仅 0.20 —— 唯一一条真正独立的「内容具体性」轴。"""
    n = len(re.findall(r"\d+", body))
    n += len(re.findall(r"[一二三四五六七八九十百千万几数]\s*"
                        r"[个只件张条款杯瓶斤米吨天年月日时分秒次回遍]", body))
    return n / _k(body)


def c_para_even(body):
    """段长均匀度：落在中位 ±40% 内的段落比例。sep 0.67，但最大相关 0.64，
    大半是现有段长项的回声。"""
    ps = [len(WSP.sub("", p)) for p in q.paras(body)]
    if len(ps) < 8:
        return None
    med = st.median(ps)
    if med <= 0:
        return None
    return sum(1 for n in ps if 0.6 * med <= n <= 1.4 * med) / len(ps)


def c_pstart_rep(body):
    """段首 3 字重复率。sep 0.52。"""
    starts = []
    for p in q.paras(body):
        m = re.search(r"[\u4e00-\u9fff]", p)
        if m:
            starts.append(p[m.start():m.start() + 3])
    if len(starts) < 6:
        return None
    c = Counter(starts)
    return sum(v for v in c.values() if v > 1) / len(starts)


def c_shead_ent(body):
    """句首字多样性熵（先剥引号，否则量的是引号碎片）。sep 0.29。"""
    b = QSTRIP.sub("", re.sub(r"[*>#]", "", body))
    ss = [WSP.sub("", s) for s in SPLIT.split(b)]
    ss = [s for s in ss if len(s) >= 2]
    if len(ss) < 15:
        return None
    return _ent(Counter(s[0] for s in ss).values())


def c_dial_tag(body):
    """对话标签集中度：说/道 占全部标签的比例。sep 0.20。"""
    tot = sum(body.count(t) for t in TAGS)
    if tot < 5:
        return None
    return (body.count("说") + body.count("道")) / tot


def c_burst(body):
    """突现性：相邻句长差绝对均值/均长。sep 0.02 —— 零区分度，
    尽管它在那份 48 规则表里权重 1.3。"""
    lens = [len(s) for s in q.sentences(body)]
    if len(lens) < 15:
        return None
    d = [abs(lens[i] - lens[i - 1]) for i in range(1, len(lens))]
    m = st.mean(lens)
    return st.mean(d) / m if m else 0.0


def c_prop_n(body):
    """专有名词密度/千字（后缀正则近似）。sep 0.09。"""
    p = len(re.findall(r"[\u4e00-\u9fff]{1,4}"
                       r"(街|路|巷|城|镇|村|山|河|湖|海|岛|宫|殿|塔|桥|楼|院)", body))
    o = len(re.findall(r"[\u4e00-\u9fff]{1,6}"
                       r"(公司|集团|大学|学院|中学|医院|政府|银行|协会)", body))
    return (p + o) / _k(body)


def c_time_w(body):
    """时间词密度/千字。sep 0.02。"""
    h = re.findall(r"(今天|昨天|明天|前天|后天|今晚|昨夜|清晨|黄昏|午后|"
                   r"凌晨|傍晚|正午|此刻|当时|那时|如今|从前|此后)", body)
    return len(h) / _k(body)


def c_punct_ent(body):
    """标点多样性熵。sep 0.08，且受排版影响 —— 双重不合格。"""
    ps = [c for c in body if c in PUNCT]
    if len(ps) < 30:
        return None
    return _ent(Counter(ps).values())


def c_noise(body):
    """对照：确定性伪随机（内容哈希），与文本语义无关。"""
    h = int(hashlib.sha256(body.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0


CAND = [
    ("num_quant", c_num_quant, "real", "数字+量词密度/千字"),
    ("para_even", c_para_even, "real", "段长均匀度"),
    ("pstart_rep", c_pstart_rep, "real", "段首3字重复率"),
    ("shead_ent", c_shead_ent, "syn", "句首字多样性熵（剥引号）"),
    ("dial_tag", c_dial_tag, "human", "对话标签集中度（说/道占比）"),
    ("burst", c_burst, "syn", "突现性（相邻句长差/均长）"),
    ("prop_n", c_prop_n, "real", "专有名词密度/千字"),
    ("time_w", c_time_w, "real", "时间词密度/千字"),
    ("punct_ent", c_punct_ent, "real", "标点多样性熵"),
    ("__noise__", c_noise, "real", "对照组：纯噪声（与文本无关）"),
]


# ---------------------------------------------------------------- 维度分复算

def dim_score(m, dim, extra=None, extra_w=0.0):
    """复算维度分，与 qc_core.score_* 同口径；extra=(key, value, tgt, over)。"""
    tbl, w, xtbl = DIMS[dim]
    s = {}
    for k, (g, b) in list(tbl.items()) + list(xtbl.items()):
        v = m.get(k)
        if v is None:
            continue
        gv = q.good(v, g, b)
        if gv is not None:
            s[k] = gv
    ww = dict(w)
    if extra is not None:
        key, val, tgt, over = extra
        if val is not None:
            gv = q.good(val, tgt, over)
            if gv is not None:
                s[key] = gv
                ww[key] = extra_w
    return q._wavg(s, ww)


def collect(paths, per):
    out = []
    for f in paths:
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        ms = []
        for b in audit.chapters(txt, per):
            m = q.metrics(b)
            for key, fn, _, _ in CAND:
                try:
                    m[key] = fn(b)
                except Exception:
                    m[key] = None
            ms.append(m)
        if ms:
            out.append((os.path.basename(f)[:26], ms))
    return out


def main():
    ap = argparse.ArgumentParser(description="墨尺扩充指标收益评估")
    ap.add_argument("--human", required=True)
    ap.add_argument("--ai", nargs="+", action="extend", required=True)
    ap.add_argument("--per", type=int, default=100)
    ap.add_argument("--fp", action="store_true")
    ap.add_argument("--cand", help="只评估这几个候选，逗号分隔")
    a = ap.parse_args()

    hf = audit.load([a.human])
    af = audit.load(a.ai)
    if a.fp:
        hf, dropped = bench_build.keep_known(hf)
        print(f"  [--fp] 剔掉 {len(dropped)} 本未登记 / 不可用的书，"
              f"保留 {len(hf)} 本")
    if not hf or not af:
        sys.exit("真人组与 AI 组都至少要有一个文件")
    if a.per != bench_build.PERBOOK:
        print(f"  ⚠ --per={a.per} ≠ bench_build.PERBOOK={bench_build.PERBOOK}："
              f"Δ 可用于横向比较，但别当绝对水位。")

    cands = CAND
    if a.cand:
        want = {x.strip() for x in a.cand.split(",")}
        cands = [c for c in CAND if c[0] in want or c[0] == "__noise__"]

    HB, AB = collect(hf, a.per), collect(af, a.per)
    H = [m for _, ms in HB for m in ms]
    A = [m for _, ms in AB for m in ms]
    print(f"真人 {len(hf)} 文件 / {len(H)} 章　AI {len(af)} 文件 / {len(A)} 块"
          f"　（每本 ≤{a.per} 章）")

    # 自检：手工维度分必须与 score_* 逐位一致，否则下面所有 Δ 都不可信
    chk = HB[0][1][0]
    for d, fn in (("real", q.score_real), ("human", q.score_human),
                  ("imm", q.score_imm), ("rhy", q.score_rhy), ("syn", q.score_syn)):
        _, ref = fn(chk)
        assert abs(ref - dim_score(chk, d)) < 1e-9, d
    print("[自检] 维度分复算与 score_* 逐位一致 ✓\n")

    print("各维当前分离度（基线）")
    base = {}
    for d in DIMS:
        hs = [dim_score(m, d) for m in H]
        as_ = [dim_score(m, d) for m in A]
        base[d] = audit.sep(hs, as_)
        print(f"  {DIMNAME[d]:<4} {base[d]:.4f}   （{len(srv.DIM_ITEM_SRC[d])} 项）")
    print()

    def book_med(key):
        out = []
        for _, ms in HB:
            vs = [m[key] for m in ms if m.get(key) is not None]
            if vs:
                out.append(st.median(vs))
        return out

    def pooled(blocks, key):
        return [m[key] for _, ms in blocks for m in ms if m.get(key) is not None]

    print("=" * 100)
    print(f"{'候选指标':<12}{'目标维':<7}{'真人中位':>10}{'AI中位':>9}{'sep':>7}"
          f"{'残差':>7}{'最大相关':>9}{'Δ维sep':>9}   说明")
    print("=" * 100)
    rows = []
    for key, fn, dim, desc in cands:
        hm = st.median(book_med(key))
        am = st.median(pooled(AB, key))
        tgt = am + 0.85 * (hm - am)
        hv, av = pooled(HB, key), pooled(AB, key)
        s = audit.sep(hv, av)
        rs = audit.resid_sep(hv, pooled(HB, "sent_med"),
                             av, pooled(AB, "sent_med"))
        mx = 0.0
        for k2 in DIMS[dim][1]:
            v2 = pooled(HB, k2)
            if len(v2) == len(hv):
                mx = max(mx, abs(audit.corr(hv, v2)))
        wavg = st.mean(list(DIMS[dim][1].values()))
        hs2 = [dim_score(m, dim, (key, m.get(key), tgt, am), wavg) for m in H]
        as2 = [dim_score(m, dim, (key, m.get(key), tgt, am), wavg) for m in A]
        rows.append((key, dim, hm, am, s, rs, mx,
                     audit.sep(hs2, as2) - base[dim], desc))

    for key, dim, hm, am, s, rs, mx, dd, desc in rows:
        nm = "噪声对照" if key == "__noise__" else key
        rss = f"{rs:.3f}" if rs is not None else "  —  "
        print(f"{nm:<12}{DIMNAME[dim]:<7}{hm:>10.4f}{am:>9.4f}{s:>7.3f}"
              f"{rss:>7}{mx:>9.3f}{dd:>+9.4f}   {desc}")

    noise = [r for r in rows if r[0] == "__noise__"]
    print()
    print("判读：")
    print("  Δ维sep = 按该维平均权重加进去后，该维分离度的变化。")
    print("  最大相关 > 0.7 说明是现有项的回声；残差 sep 掉下来说明是句长的回声。")
    if noise:
        print(f"  ⚠ 噪声对照的 Δ 是 {noise[0][7]:+.4f}——"
              f"正负号不比它大的候选，一律视为「没有信号」。")
    best = max((r for r in rows if r[0] != "__noise__"), key=lambda r: r[7], default=None)
    indep = [r for r in rows if r[0] != "__noise__" and r[6] < 0.5 and r[4] >= 0.6]
    if best:
        print(f"  Δ 最大的候选：{best[0]}（Δ={best[7]:+.4f}，sep={best[4]:.3f}，"
              f"与现有项最大相关={best[6]:.3f}）")
    if indep:
        b2 = max(indep, key=lambda r: r[4])
        print(f"  「既独立又有信号」的候选（最大相关<0.5 且 sep≥0.6）："
              f"{b2[0]}（sep={b2[4]:.3f}，残差="
              f"{'—' if b2[5] is None else round(b2[5], 3)}，Δ={b2[7]:+.4f}）")
    else:
        print("  「既独立又有信号」的候选：本批一个都没有。")
    print("  维度 sep 已接近 1 时，任何候选都救不了区分度——"
          "这时扩维度的价值在「换轴覆盖新失败模式」，不在提升分离度。")


if __name__ == "__main__":
    main()
