#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 阈值标定（开发工具，不参与服务运行）

回答一个问题：**这个指标的达标线该定在哪**。

用法：
    python3 tools/calibrate.py --human <真人语料> --ai <AI语料> [--ai <AI语料2> ...]
    python3 tools/calibrate.py --human ~/标杆文章 --ai ~/AI文章/分幕稿A ~/AI文章/分幕稿B
    python3 tools/calibrate.py --human ... --ai ... --items redupl,emo --k 0.85

    --human   真人语料（目录或文件），必填
    --ai      AI 语料（目录或文件），可给多个，全部并成一个 AI 组
    --items   只标定这几个指标（逗号分隔），默认全部打分项
    --k       达标线插值系数，默认 0.85
    --per     每本最多抽多少章（全书等距），默认 100——**必须与
              tools/bench_build.py 的 PERBOOK 一致**，否则真人中位会系统性
              偏小（实测 per=60 时 dial_sent 是 16.27，per=100 才是 16.95，
              而 qc_core 阈值表里记的就是 16.9458）。
    --ai-cap  每个 AI 文件最多抽多少章，默认 0（不封顶）
    --fp      真人语料只保留 tools/bench_build.py 里登记过内容指纹的 24 本。
              标杆文章目录里有 5 本不可用的（拆不出章 / 疑似合章），不筛掉
              会把「真人中位」算歪——**标定阈值时必须开**。

统一公式（与 qc_core 各维阈值表的注一致）：
    达标 = AI中位 + k × (真人中位 − AI中位)
    超标 = AI中位
k=0.85 的取法见 qc_core.HUMAN_GOOD_BAD 上方的标定注释：k=1.0 会把水位压塌，
k 越小越接近旧线、越容易饱和。

两个「中位」口径不同，**不要混用**：
    真人中位 —— 先算每本中位，再取跨本中位（防某一本超长书主导）
    AI  中位 —— 所有块直接取中位（AI 语料本身就是散块，没有「本」的概念）

输出末尾会与 qc_core 当前阈值逐项对照，并给出建议阈值。
**本工具只报告、不改源码**——阈值改动一律人工核对后写入 qc_core。

只依赖 Python 标准库。统计函数复用 tools/audit.py，不重复实现。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit                                # noqa: E402
import bench_build                          # noqa: E402
import qc_core as q                         # noqa: E402

SHOW = audit.SHOW


def keep_fingerprinted(paths):
    """只留下内容指纹登记过的文件（真人标杆 24 本），并报出被剔掉几个。"""
    keep = [f for f in paths if bench_build.fingerprint(f) in bench_build.FP2CODE]
    drop = len(paths) - len(keep)
    if drop:
        print(f"  [--fp] 剔掉 {drop} 本未登记 / 不可用的书，保留 {len(keep)} 本")
    return keep


def per_book(paths, cap):
    """每本抽 ≤cap 章并算好 metrics，返回 [(文件名, [metrics, ...])]。

    metrics() 很贵（几十条正则），所以**每本只算一次**再供所有指标复用——
    按指标逐个重算会让整个标定慢上一个数量级。
    """
    out = []
    for f in paths:
        try:
            t = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        ms = audit.sample([f], cap)
        if ms:
            out.append((os.path.basename(f)[:28], ms))
    return out


def main():
    ap = argparse.ArgumentParser(description="墨尺阈值标定")
    ap.add_argument("--human", required=True, help="真人语料（目录或文件）")
    ap.add_argument("--ai", nargs="+", required=True, help="AI 语料，可多个")
    ap.add_argument("--items", help="只标定这些指标，逗号分隔")
    ap.add_argument("--k", type=float, default=0.85, help="达标线插值系数")
    ap.add_argument("--per", type=int, default=100, help="每本最多抽多少章")
    ap.add_argument("--ai-cap", type=int, default=0, help="每个 AI 文件最多抽多少章")
    ap.add_argument("--fp", action="store_true",
                    help="真人语料只保留内容指纹登记过的 24 本")
    a = ap.parse_args()

    hf = audit.load([a.human])
    af = audit.load(a.ai)
    if a.fp:
        hf = keep_fingerprinted(hf)
    if not hf or not af:
        sys.exit("真人组与 AI 组都至少要有一个文件")

    keys = ([k.strip() for k in a.items.split(",")] if a.items
            else [k for k in SHOW if k in q.ITEM_TARGET])

    print(f"真人 {len(hf)} 个文件　AI {len(af)} 个文件　"
          f"k={a.k}　每本 ≤{a.per} 章")

    # 样本：真人按本算中位（每本只算一次 metrics），AI 全部块汇总
    HB = per_book(hf, a.per)
    A = audit.sample(af, a.ai_cap or None)
    # 真人池化样本（逐章）：分离度/残差用它——与既有 sep 口径一致；
    # 阈值用「跨本中位」：防某一本超长书主导达标线。两个口径分工不同。
    H = [m for _, ms in HB for m in ms]
    print(f"样本：真人 {len(HB)} 本 / {len(H)} 章　AI {len(A)} 章\n")

    print("=" * 104)
    print(f"{'指标':<11}{'真人跨本中位':>13}{'AI中位':>9}{'分离度':>8}"
          f"{'残差':>7}{'AI零值率':>10}   当前阈值 → 建议阈值")
    print("=" * 104)
    changed = []
    for k in keys:
        # 真人：每本一个中位（None 不计），再取跨本中位
        hb = [audit.st.median([m[k] for m in ms if m.get(k) is not None])
              for _, ms in HB if any(m.get(k) is not None for m in ms)]
        hv = [m[k] for m in H if m.get(k) is not None]      # 池化，算 sep 用
        av = [x[k] for x in A if x.get(k) is not None]
        if not hb or not av:
            print(f"{k:<11}   该项在{'真人' if not hb else 'AI'}组全为「不适用」")
            continue
        hm = audit.st.median(hb)
        am = audit.st.median(av)
        s = audit.sep(hv, av)
        # 残差要的是「句长配对」——必须与 hv/av 一一对应，不能用未过滤的 HS/AS
        hp = [(m[k], m["sent_med"]) for m in H if m.get(k) is not None]
        ap = [(x[k], x["sent_med"]) for x in A if x.get(k) is not None]
        rs = audit.resid_sep([p[0] for p in hp], [p[1] for p in hp],
                             [p[0] for p in ap], [p[1] for p in ap])
        za = sum(1 for v in av if v == 0) / len(av) * 100
        tgt = am + a.k * (hm - am)
        cur = q.ITEM_TARGET.get(k)
        flag = ""
        if cur and (abs(cur[0] - tgt) > 0.005 or abs(cur[1] - am) > 0.005):
            flag = "  ← 需更新"
            changed.append(k)
        print(f"{k:<11}{hm:>13.3f}{am:>9.3f}{s:>8.2f}"
              f"{'  —  ' if rs is None else f'{rs:>5.2f}  ':>7}{za:>9.0f}%"
              f"   {cur} → ({tgt:.4g}, {am:.4g}){flag}")

    print("\n" + "-" * 104)
    if changed:
        print(f"需要更新的指标（{len(changed)}）：{'、'.join(changed)}")
        print("写回 qc_core 时：只改这些键，其余阈值必须逐字节不变。")
    else:
        print("全部指标与当前阈值一致，无需更新。")


if __name__ == "__main__":
    main()
