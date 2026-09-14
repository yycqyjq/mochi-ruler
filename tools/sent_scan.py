#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 句子切分口径扫描（开发工具，不参与服务运行）

回答一个问题：**哪些指标其实在量引号碎片，而不是在量笔法**。

`sentences()` 按 `[。！？…]+` 切分，对话引号会被切成独立碎片：

    “我知道了。”他点点头。   →   ["“我知道了", "”他点点头"]

第二段的**真实句首被 `”` 挡住**，于是所有拿 `ss` 当分母或样本的指标
（pron_start / sent_med / sent_p90 / sent_p10 / cv / sent_den / question /
emo_type / net_short）都被稀释。这不是排版问题——换任何字体、任何缩进都一样，
所以 `layout_scan.py` 扫不出来。

本工具把每个句子类指标分别在「原样切句」与「先剥掉引号字符再切句」两个口径
下算分离度，Δ 大的说明该指标被引号碎片污染。

用法：
    python3 tools/sent_scan.py --human <真人语料> --ai <AI语料> [--ai ...]
    python3 tools/sent_scan.py --human ~/标杆文章 --ai ~/ai1 ~/ai2 --per 100
    python3 tools/sent_scan.py --human ... --ai ... --fp --top 12

    --human   真人语料（目录或文件），必填
    --ai      AI 语料（目录或文件），可多个；`--ai A B` 与 `--ai A --ai B` 等价
    --per     每本最多抽多少章（全书等距），默认 100——须与 bench_build.PERBOOK 一致
    --top     打印前 N 行，默认全部
    --fp      真人语料只保留 bench_build 里登记过内容指纹的 24 本

判读：Δ ≥ +0.03 说明修正切分口径能明显提升该指标，值得单独重标定；
Δ ≈ 0 说明该指标对引号碎片不敏感，不必动。

只依赖 Python 标准库。统计函数复用 tools/audit.py。
"""

import argparse
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit                                # noqa: E402
import bench_build                          # noqa: E402
import qc_core as q                         # noqa: E402

QSTRIP = re.compile("[\u201c\u201d\u300c\u300d\u2018\u2019\"']")
SPLIT = re.compile(r"[。！？…]+")
WSP = re.compile(r"\s")

# 所有直接或间接依赖 sentences() 的指标。net_short 不参与打分，留作参照。
SENT_KEYS = ["pron_start", "sent_med", "sent_p90", "sent_p10", "cv",
             "sent_den", "question", "emo_type", "net_short"]


def sents(body, strip):
    b = re.sub(r"[*>#]", "", body)
    if strip:
        b = QSTRIP.sub("", b)
    return [WSP.sub("", s) for s in SPLIT.split(b)
            if len(WSP.sub("", s)) >= 2]


def feats(body, strip):
    """按指定切句口径重算全部句子类指标。"""
    ss = sents(body, strip)
    k = max(len(WSP.sub("", body)), 1) / 1000.0
    lens = [len(s) for s in ss] or [1]
    L = sorted(len(s) for s in ss) or [0]
    n = max(len(ss), 1)
    return {
        "pron_start": (sum(1 for s in ss if s and s[0] in "他她它") / n)
                      if ss else 0.0,
        "sent_med": float(st.median(lens)),
        "sent_p90": float(L[min(int(len(L) * 0.90), len(L) - 1)]),
        "sent_p10": float(L[int(len(L) * 0.10)]),
        "cv": (st.pstdev(lens) / st.mean(lens)) if len(lens) > 2 else 0.0,
        "sent_den": len(ss) / k,
        "question": body.count("\uff1f") / n * 100.0,
        "emo_type": len(set(q.EMO.findall(body))) / n * 100.0,
        "net_short": sum(1 for s in ss if len(s) <= 10) / n,
    }


def collect(paths, strip, per):
    """返回 (每本中位 dict, 全部块值 dict)。"""
    bm = {k: [] for k in SENT_KEYS}
    pool = {k: [] for k in SENT_KEYS}
    for f in paths:
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        vs = {k: [] for k in SENT_KEYS}
        for b in audit.chapters(txt, per):
            ft = feats(b, strip)
            for k in SENT_KEYS:
                vs[k].append(ft[k])
        for k in SENT_KEYS:
            if vs[k]:
                bm[k].append(st.median(vs[k]))
                pool[k] += vs[k]
    return bm, pool


def main():
    ap = argparse.ArgumentParser(description="墨尺句子切分口径扫描")
    ap.add_argument("--human", required=True, help="真人语料（目录或文件）")
    ap.add_argument("--ai", nargs="+", action="extend", required=True,
                    help="AI 语料，可多个")
    ap.add_argument("--per", type=int, default=100, help="每本最多抽多少章")
    ap.add_argument("--top", type=int, default=0, help="只打印前 N 行")
    ap.add_argument("--fp", action="store_true",
                    help="真人语料只保留内容指纹登记过的 24 本")
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
              f"分离度可用于比较两口径，但别拿它当绝对水位。")

    (hb_a, hp_a), (ab_a, ap_a) = collect(hf, False, a.per), collect(af, False, a.per)
    (hb_b, hp_b), (ab_b, ap_b) = collect(hf, True, a.per), collect(af, True, a.per)

    print(f"真人 {len(hf)} 文件 / {len(hp_a['sent_med'])} 章　"
          f"AI {len(af)} 文件 / {len(ap_a['sent_med'])} 块　（每本 ≤{a.per} 章）")
    print("\n剥掉引号字符再切句，各指标分离度的变化")
    print(f"{'指标':<12}{'真人中位':>10}{'AI中位':>9}"
          f"{'原样':>8}{'剥引号':>9}{'Δ':>8}   判定")
    print("-" * 68)
    rows = []
    for k in SENT_KEYS:
        sa = audit.sep(hp_a[k], ap_a[k])
        sb = audit.sep(hp_b[k], ap_b[k])
        rows.append((k, st.median(hb_a[k]), st.median(ap_a[k]), sa, sb, sb - sa))
    rows.sort(key=lambda r: -r[5])
    show = rows[:a.top] if a.top else rows
    for k, hm, am, sa, sb, d in show:
        verdict = ("修正口径能明显提升" if d >= 0.03 else
                   "基本不敏感" if abs(d) < 0.01 else "略有变化")
        print(f"{k:<12}{hm:>10.4f}{am:>9.4f}{sa:>8.3f}{sb:>9.3f}{d:>+8.3f}   {verdict}")
    print(f"\n最大 Δ {max(r[5] for r in rows):+.2f}"
          f"　—— Δ ≥ +0.03 的指标值得单独重标定")


if __name__ == "__main__":
    main()
