#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 排版噪声扫描（开发工具，不参与服务运行）

回答一个问题：**某个指标的区分度，有多少来自排版差异而不是笔法差异。**

用法：
    python3 tools/layout_scan.py --human <真人语料> --ai <AI语料> [--ai <AI语料2> ...]
    python3 tools/layout_scan.py --human ~/标杆文章 --ai ~/AI文章/分幕稿 --per 100

    --human   真人语料（目录或文件），必填
    --ai      AI 语料（目录或文件），可给多个
    --per     每本最多抽多少章（全书等距），默认 100
    --top     只打印 Δ 最大的前 N 行，默认全部
    --fp      真人语料只保留 tools/bench_build.py 里登记过内容指纹的 25 本。
              标杆目录里另有几本不可用的，不筛会污染两侧的分离度。

项目铁律（见 qc_core 注释）：
    **格式噪声必须排除** —— 段间空行、引号风格、半角标点、拉丁字母、全角缩进，
    全是排版差异，不是笔法。判分离前必须回原文验证。

做法：对每个指标，分别在「原样正文」与「剥掉全角空格后的正文」上算真人/AI
分离度。Δ 越大 = 该指标的分离度越依赖排版。

这条扫描出过一次真问题：`head`（句首集中）原样分离度 0.92，剥掉段首的全角
缩进后塌到 0.09——它的全部区分度都来自「真人语料段首缩进、AI 语料不缩进」，
于是被整体删除。`redupl` 旧正则把全角空格对也算成叠词，同样在这里露了馅。
**任何新指标入库前都该先过这道扫描。**

只依赖 Python 标准库。统计与语料加载复用 tools/audit.py，不重复实现。
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
import server                               # noqa: E402

FWSP = "\u3000"                             # 全角空格（段首缩进用的就是它）


def chapters_of(paths, cap):
    """把语料展开成章正文列表。要的是**正文**而不是 metrics——同一个 body
    要算两次（原样 / 去缩进），所以不能直接用 audit.sample()。"""
    out = []
    for f in paths:
        try:
            t = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        out += audit.chapters(t, cap)
    return out


def fwsp_density(bodies):
    """全角空格密度（每千字），取章级中位。"""
    vs = [b.count(FWSP) / max(len(re.sub(r"\s", "", b)), 1) * 1000
          for b in bodies]
    return st.median(vs) if vs else 0.0


def main():
    ap = argparse.ArgumentParser(description="墨尺排版噪声扫描")
    ap.add_argument("--human", required=True, help="真人语料（目录或文件）")
    ap.add_argument("--ai", nargs="+", required=True, help="AI 语料，可多个")
    ap.add_argument("--per", type=int, default=100, help="每本最多抽多少章")
    ap.add_argument("--top", type=int, default=0, help="只打印 Δ 最大的前 N 行")
    ap.add_argument("--fp", action="store_true",
                    help="真人语料只保留内容指纹登记过的 25 本")
    a = ap.parse_args()

    hf, af = audit.load([a.human]), audit.load(a.ai)
    if a.fp:
        hf, dropped = bench_build.keep_known(hf)
        print(f"  [--fp] 剔掉 {len(dropped)} 本未登记 / 不可用的书，"
              f"保留 {len(hf)} 本")
    if not hf or not af:
        sys.exit("真人组与 AI 组都至少要有一个文件")

    Hb = chapters_of(hf, a.per)
    Ab = chapters_of(af, None)
    if not Hb or not Ab:
        sys.exit("至少有一组没抽到 ≥%d 字的章节" % audit.MINCH)
    print(f"真人 {len(hf)} 文件 / {len(Hb)} 章    "
          f"AI {len(af)} 文件 / {len(Ab)} 块    （每本 ≤{a.per} 章）")
    print(f"全角空格密度（每千字，章级中位）："
          f"真人 {fwsp_density(Hb):.2f} / AI {fwsp_density(Ab):.2f}")

    # 单趟：每个 body 只算两次 metrics（几十条正则，逐指标重算会慢一个数量级）
    def both(bodies):
        return [(q.metrics(b), q.metrics(b.replace(FWSP, ""))) for b in bodies]

    H, A = both(Hb), both(Ab)

    rows = []
    for k in server.SHOW:
        s1 = audit.sep([m.get(k) or 0.0 for m, _ in H],
                       [m.get(k) or 0.0 for m, _ in A])
        s2 = audit.sep([m.get(k) or 0.0 for _, m in H],
                       [m.get(k) or 0.0 for _, m in A])
        rows.append((abs(s2 - s1), k, s1, s2))
    rows.sort(reverse=True)
    if a.top:
        rows = rows[:a.top]

    print("\n剥掉全角空格后，各指标分离度的变化")
    print(f"{'指标':<12}{'原样':>8}{'去缩进':>9}{'Δ':>8}   判定")
    print("-" * 52)
    for d, k, s1, s2 in rows:
        if d >= 0.10:
            v = "⚠ 严重依赖排版"
        elif d >= 0.05:
            v = "· 轻度依赖排版"
        else:
            v = ""
        print(f"{k:<12}{s1:>8.2f}{s2:>9.2f}{s2 - s1:>+8.2f}   {v}")
    worst = max((r[0] for r in rows), default=0.0)
    print("-" * 52)
    print(f"最大 Δ {worst:.2f}"
          + ("（无指标依赖排版）" if worst < 0.05
             else "（Δ≥0.10 的指标应先回原文验证，再决定修正则还是删项）"))


if __name__ == "__main__":
    main()
