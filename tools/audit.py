#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 全指标体检（开发工具，不参与服务运行）

对全部打分指标逐项体检，回答一个问题：**这把尺子现在还准吗**。

用法：
    python3 tools/audit.py --human <真人语料> --ai <AI语料> [--ref <参照组>]
    python3 tools/audit.py --human ~/books --ai ~/ai --ref ~/mine --top 20

    --human   真人长篇语料（目录或文件，.txt/.md/.markdown），必填
    --ai      AI 生成语料，必填
    --ref     参照组，选填。**已知标签的对照组**，用于观察误判；
              默认不参与任何判据计算（见下）
    --ref-into-ai  把参照组并入 AI 组一起算判据。**慎用**：只在该组确实
              是 AI 生成文本时才该开，否则会污染基线、削弱所有指标
    --top     语料体检里打印的前 N 行，默认全部
    --per     每本最多抽多少章（全书等距），默认 60

三组样本的分工：
    真人组  —— 判据的「正样本」，所有分离度、阈值建议都以它为基准
    AI 组   —— 判据的「负样本」
    参照组  —— 已知标签，只做对照展示 + 误判提示，**不进任何判据**。
              典型用法：把自己写的正文挂在这里，看它落在哪一侧。

输出五块：
    1 语料体检    章数 / 章均字数 / 疑似合章或拆不出章的坏本（**坏本已剔出判据**）
    2 逐项体检    分布、分离度、残差分离度、两侧满分率、判定
    3 五维与总分
    4 跨作品稳定  分离度是不是靠某一部撑起来的
    5 维度内共线  指标原始值 vs 该维分数

两个判据（改指标前必看，写在 qc_core.SYN_GOOD_BAD 上方的「口径警告」里）：
    **每千字**会被短句化虚高（AI 句子短 → 每千字句子多 → 什么密度都涨）
    **每百句**会被句长绑架（句子越长，每句撞上目标词的概率越高）
    所以一律加做残差检验：在真人样本上做 `X ~ 句长中位` 回归，看 AI 残差的
    分离度。真信号残差仍在，句长的回声会掉下来甚至方向反转。

只依赖 Python 标准库，不写死任何语料路径。
"""

import argparse
import bisect
import glob
import math
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# server.py 在 import 时把 argv[1] 当端口号读走，所以先顶上一个合法端口再导入；
# 但 argparse 也要读 sys.argv，所以原始参数得先留一份，不能覆盖掉。
_ARGV = sys.argv[:]
sys.argv = [sys.argv[0], "8765"]
import qc_core as q                        # noqa: E402
import server                              # noqa: E402
sys.argv = _ARGV

MINCH = 1200
SHOW = server.SHOW
DIM_OF = {k: d for d, tbl in server.DIM_ITEM_SRC.items() for k in tbl}
EXTRA = ["ttr", "net_short", "enum"]       # 不参与打分，只备查
# `act` 2026-09-14 已入代入感维（在 server.SHOW 里），不再列于此——留着会重复输出一行。
# `enum` 同日退出打分（真人侧左尾过重），补进这份「只备查」名单。


# ---------------------------------------------------------------- 采样

def chapters(text, cap=None):
    ch = [b for _, b in q.split_chapters(text)
          if len(re.sub(r"\s", "", b)) >= MINCH]
    if cap and len(ch) > cap:
        step = len(ch) / cap
        ch = [ch[int(i * step)] for i in range(cap)]
    return ch


def load(paths):
    """路径可以是目录或文件，展开成文件列表。

    目录下的**隐藏文件与隐藏目录一律跳过**：语料目录里常常混着 `.workbuddy-ai`
    / `.git` 这类工具目录，不筛就会把无关文本悄悄算进判据（实测 AI 组因此多出
    1 块）。显式传进来的文件路径不做隐藏名过滤——那是用户自己指定的。
    """
    out = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ("*.txt", "*.md", "*.markdown"):
                for f in sorted(glob.glob(os.path.join(p, "**", ext),
                                          recursive=True)):
                    rel = os.path.relpath(f, p)
                    if any(seg.startswith(".") for seg in rel.split(os.sep)):
                        continue
                    out.append(f)
        elif os.path.isfile(p):
            out.append(p)
        else:
            for ext in ("*.txt", "*.md", "*.markdown"):
                out += sorted(glob.glob(os.path.join(p, ext)))
    return sorted(f for f in out if not f.endswith(".DS_Store"))


def sample(paths, cap):
    out = []
    for f in paths:
        try:
            t = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        out.extend([q.metrics(b) for b in chapters(t, cap)])
    return out


def corpus_report(paths, label, top, whole=False):
    """whole=True 表示每个文件是一本完整的书，这时才做「坏本」判定。

    AI 语料常常是分幕/分章的散文件（一个文件只有 1 章），按文件判
    「可用章过少」是误报，所以这类语料只报总量。

    返回 (可用文件列表, 坏本列表)。**判据只用可用文件**——坏本（拆不出章 /
    疑似合章）本身就是解析失败的产物，把它们算进分离度等于用垃圾数据体检尺子，
    会把所有指标一起压低。只标注不剔除是 2026-09-14 之前的旧行为。
    """
    print(f"\n[{label}] {len(paths)} 个文件")
    rows = []
    for f in paths:
        t = open(f, encoding="utf-8", errors="ignore").read()
        allc = q.split_chapters(t)
        big = [b for _, b in allc if len(re.sub(r"\s", "", b)) >= MINCH]
        med = (st.median([len(re.sub(r"\s", "", b)) for b in big])
               if big else 0.0)
        flag = ""
        if whole:
            if not big:
                flag = "← 无可用章"
            elif len(big) < 20:
                flag = "← 可用章过少"
            elif med > 6000:
                flag = "← 章均异常大，疑似合章"
        rows.append((len(big), med, os.path.basename(f)[:30], flag, f))
    show = rows if not top else rows[:top]
    for n, m, name, flag, _ in show:
        print(f"  {n:>6} 章  章均 {m:>7.0f} 字  {name}  {flag}")
    bad = [r for r in rows if r[3]] if whole else []
    kept = [r[4] for r in rows if not r[3]]
    if whole:
        if bad:
            print(f"  —— {len(bad)} 本不可用，**已剔出判据**"
                  f"（可用 {len(kept)} 本）")
        else:
            print(f"  —— {len(kept)} 本全部可用")
    else:
        print(f"  —— 合计 {sum(r[0] for r in rows)} 章"
              f"（散文件语料，不做坏本判定）")
    return kept, bad


# ---------------------------------------------------------------- 统计

def auc(a, b):
    """P(真人 > AI)"""
    bs = sorted(b)
    tot = 0.0
    for x in a:
        lo = bisect.bisect_left(bs, x)
        hi = bisect.bisect_right(bs, x)
        tot += lo + (hi - lo) / 2.0
    return tot / (len(a) * len(b))


def sep(a, b):
    """方向无关的分离度，0–1。1.00 = 两边完全分开。"""
    return abs(auc(a, b) - 0.5) * 2


def corr(xs, ys):
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs)
                    * sum((y - my) ** 2 for y in ys))
    return num / den if den else 0.0


def resid_sep(hv, hs, av, as_):
    """控制句长后的残差分离度。"""
    if len(set(hv)) < 2 or len(set(hs)) < 2:
        return None
    mx, my = st.mean(hs), st.mean(hv)
    sxx = sum((x - mx) ** 2 for x in hs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(hs, hv)) / sxx
    icpt = my - slope * mx
    hr = [y - (icpt + slope * x) for x, y in zip(hs, hv)]
    ar = [y - (icpt + slope * x) for x, y in zip(as_, av)]
    if len(set(hr)) < 2 or len(set(ar)) < 2:
        return None
    return sep(hr, ar)


def pct(arr, p):
    s = sorted(arr)
    return s[min(int(len(s) * p), len(s) - 1)]


def fullrate(scores):
    if not scores:
        return 0.0
    return sum(1 for x in scores if x >= 9.99) / len(scores) * 100


def dims(ms):
    out = []
    for m in ms:
        sc = {"real": q.score_real(m)[1], "human": q.score_human(m)[1],
              "imm": q.score_imm(m)[1], "rhy": q.score_rhy(m)[1],
              "syn": q.score_syn(m)[1]}
        sc["total"] = q.score_total(sc)
        out.append(sc)
    return out


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="墨尺全指标体检")
    ap.add_argument("--human", nargs="+", required=True, help="真人语料")
    ap.add_argument("--ai", nargs="+", required=True, help="AI 语料")
    ap.add_argument("--ref", nargs="*", default=[], help="参照组（已知标签）")
    ap.add_argument("--ref-into-ai", action="store_true",
                    help="把参照组并入 AI 组算判据（仅当该组确为 AI 文本）")
    ap.add_argument("--per", type=int, default=60, help="每本最多抽多少章")
    ap.add_argument("--top", type=int, default=0, help="语料体检打印前 N 行")
    a = ap.parse_args()

    hf, af, rf = load(a.human), load(a.ai), load(a.ref)
    if not hf or not af:
        sys.exit("真人组与 AI 组都至少要有一个文件")

    print("=" * 112)
    print("1 语料体检")
    print("=" * 112)
    hf, _ = corpus_report(hf, "真人组", a.top, whole=True)
    af, _ = corpus_report(af, "AI 组", a.top)
    if rf:
        rf, _ = corpus_report(rf, "参照组", a.top)
    if not hf or not af:
        sys.exit("剔除坏本后，真人组或 AI 组已无可用文件")

    H = sample(hf, a.per)
    A = sample(af, None)
    R = sample(rf, None) if rf else []
    if a.ref_into_ai and R:
        A = A + R
        print("\n  ⚠ 参照组已并入 AI 组参与判据（--ref-into-ai）")
    print(f"\n样本：真人 {len(H)} 章　AI {len(A)} 章"
          + (f"　参照 {len(R)} 章（不参与判据）" if R else ""))

    # AI 组构成：某一部占比过高会主导统计，必须显式提示
    parts = {}
    for f in af:
        w = os.path.basename(os.path.dirname(f)) or os.path.basename(f)
        parts.setdefault(w, []).append(f)
    if len(parts) > 1:
        cnt = {}
        for w, fs in parts.items():
            cnt[w[:26]] = sum(len(chapters(open(f, encoding="utf-8",
                                                errors="ignore").read()))
                              for f in fs)
        tot = max(sum(cnt.values()), 1)
        print("\n  AI 组构成（某一部占比过高就会主导判据）：")
        for w, c in sorted(cnt.items(), key=lambda t: -t[1]):
            p = c / tot * 100
            warn = "  ← 占比过半，判据基本由它决定" if p > 50 else ""
            print(f"    {w:<28} {c:>5} 章  {p:>5.1f}%{warn}")

    HS = [x["sent_med"] for x in H]
    AS = [x["sent_med"] for x in A]

    print("\n" + "=" * 112)
    print("2 逐项体检　分离度 = 2×|AUC−0.5|；残差 = 控制句长后；"
          "满分率 ≥95% 即饱和")
    print("=" * 112)
    hdr = (f"{'指标':<11}{'维':<5}{'真人中位':>9}{'AI中位':>8}"
           + (f"{'参照':>8}" if R else "")
           + f"{'分离度':>8}{'方向':>7}{'残差':>7}{'真人分':>7}{'AI分':>7}"
             f"{'满分率 人/AI':>13}  判定")
    print(hdr)
    print("-" * 112)

    for k in SHOW + EXTRA:
        dim = DIM_OF.get(k, "—")
        hv = [x.get(k) or 0.0 for x in H]
        av = [x.get(k) or 0.0 for x in A]
        s = sep(hv, av)
        direc = "真人高" if auc(hv, av) > 0.5 else "AI高"
        rs = resid_sep(hv, HS, av, AS)
        hs_ = [q.item_score(k, v) for v in hv]
        as_ = [q.item_score(k, v) for v in av]
        hs_ = [x for x in hs_ if x is not None]
        as_ = [x for x in as_ if x is not None]
        fh, fa = fullrate(hs_), fullrate(as_)

        if k in EXTRA:
            v = "备查未计分"
        elif fh >= 95 and fa >= 95:
            v = "✗ 死项·两侧恒满分"
        elif fh >= 95 and fa < 50:
            v = "✓ 有效（真人恒满分，但能抓 AI）"
        elif fh >= 95:
            v = "✗ 饱和·真人恒满分"
        elif s >= 0.75 and (rs is None or rs >= 0.5):
            v = "✓ 强"
        elif s >= 0.55 and (rs is None or rs >= 0.35):
            v = "~ 中"
        elif rs is not None and rs < 0.25 and s >= 0.55:
            v = "✗ 共线·句长回声"
        else:
            v = "· 弱"

        line = (f"{k:<11}{dim:<5}{st.median(hv):>9.2f}{st.median(av):>8.2f}")
        if R:
            line += f"{st.median([x.get(k) or 0.0 for x in R]):>8.2f}"
        line += (f"{s:>8.2f}{direc:>7}"
                 f"{'  —  ' if rs is None else f'{rs:>5.2f}  ':>7}"
                 f"{(f'{st.median(hs_):.2f}' if hs_ else '  — '):>7}"
                 f"{(f'{st.median(as_):.2f}' if as_ else '  — '):>7}"
                 f"{f'{fh:.0f}% / {fa:.0f}%':>13}  {v}")
        print(line)

    print("\n" + "=" * 112)
    print("3 五维与总分")
    print("=" * 112)
    HD, AD = dims(H), dims(A)
    RD = dims(R) if R else None
    hh = (f"{'维度':<9}{'真人':>8}{'AI':>8}"
          + (f"{'参照':>8}" if RD else "")
          + f"{'分离度':>8}{'真人P05':>9}{'AI P95':>9}  重叠")
    print(hh)
    print("-" * 112)
    for k in ("real", "human", "imm", "rhy", "syn", "total"):
        hv = [x[k] for x in HD]
        av = [x[k] for x in AD]
        line = (f"{k:<9}{st.median(hv):>8.2f}{st.median(av):>8.2f}")
        if RD:
            line += f"{st.median([x[k] for x in RD]):>8.2f}"
        line += (f"{sep(hv, av):>8.2f}{pct(hv, .05):>9.2f}{pct(av, .95):>9.2f}"
                 f"  {'有' if pct(av, .95) > pct(hv, .05) else '无'}")
        print(line)

    if RD:
        print("\n  参照组落在哪一侧（参照组不参与判据，只看位置）：")
        for k in ("real", "human", "imm", "rhy", "syn", "total"):
            hv = [x[k] for x in HD]
            av = [x[k] for x in AD]
            rv = st.median([x[k] for x in RD])
            if rv >= pct(hv, .05):
                pos = "真人区间 ✓"
            elif rv <= pct(av, .95):
                pos = "AI 区间 ⚠ 被判为 AI 特征"
            else:
                pos = "两区之间"
            print(f"    {k:<8} {rv:>6.2f}   {pos}")

    print("\n" + "=" * 112)
    print("4 跨 AI 作品稳定性")
    print("=" * 112)
    works = {}
    for f in af:
        w = os.path.basename(os.path.dirname(f)) or os.path.basename(f)
        works.setdefault(w[:18], []).append(f)
    names = sorted(works)
    if len(names) > 1:
        print(f"{'指标':<12}" + "".join(f"{n[:13]:>15}" for n in names)
              + f"{'真人中位':>10}")
        print("-" * 112)
        for k in ("g_turn", "pron3", "pron_start", "sent_med", "net_oral",
                  "emo", "para_med", "imm_cog", "vague", "sent_den"):
            line = f"{k:<12}"
            for n in names:
                vs = sample(works[n], None)
                v = [x.get(k) or 0.0 for x in vs]
                line += f"{st.median(v):>15.2f}" if v else f"{'—':>15}"
            print(line + f"{st.median([x.get(k) or 0.0 for x in H]):>10.2f}")
    else:
        print("  AI 语料只识别出一个来源，跳过（多放几部作品才有意义）")

    print("\n" + "=" * 112)
    print("5 维度内共线：指标原始值 vs 该维分数（真人样本内）")
    print("=" * 112)
    for dim in ("real", "human", "imm", "rhy", "syn"):
        ks = [k for k in SHOW if DIM_OF.get(k) == dim]
        ds = [x[dim] for x in HD]
        out = []
        for k in ks:
            r = corr([x.get(k) or 0.0 for x in H], ds)
            out.append(f"{k}={r:+.2f}{'!' if abs(r) >= 0.6 else ''}")
        print(f"  [{dim}] " + "  ".join(out))
    print("  （! 标记 |r|≥0.6，说明该项主导了整个维度的波动）")


if __name__ == "__main__":
    main()
