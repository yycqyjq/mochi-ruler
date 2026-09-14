"""排版噪声扫描：正文里的「全角空格/缩进」等格式差异，是否在给某些指标虚高分离度。

项目铁律（见 qc_core 注释与 MEMORY）：
    格式噪声必须排除 —— 段间空行、引号风格、半角标点、拉丁字母，全是排版差异，
    不是笔法。判分离前必须回原文验证。

做法：对每个指标，分别在「原样正文」与「剥掉全角空格后的正文」上算真人/AI 分离度。
Δ 越大 = 该指标的分离度越依赖排版，而不是笔法。
"""
import bisect
import glob
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = [sys.argv[0], "8765"]
import qc_core as q          # noqa: E402
import server                # noqa: E402

HOME = os.path.expanduser("~/Desktop/向死而生")
EXCLUDE = ("九君齐天", "傲世九重天", "剑来", "我的26岁女房客", "长夜君主")
AI_DIRS = ("AI文章  这个世界不想活", "AI文章 深渊之上", "AI文章 灰渊online")
MINCH, PERBOOK = 1200, 60
FWSP = "\u3000"


def chapters(t, cap):
    ch = [b for _, b in q.split_chapters(t)
          if len(re.sub(r"\s", "", b)) >= MINCH]
    if cap and len(ch) > cap:
        step = len(ch) / cap
        ch = [ch[int(i * step)] for i in range(cap)]
    return ch


def load(paths, cap):
    out = []
    for f in paths:
        t = open(f, encoding="utf-8", errors="ignore").read()
        out += chapters(t, cap)
    return out


def auc(a, b):
    bs = sorted(b)
    tot = 0.0
    for x in a:
        lo = bisect.bisect_left(bs, x)
        hi = bisect.bisect_right(bs, x)
        tot += lo + (hi - lo) / 2.0
    return tot / (len(a) * len(b))


def sep(a, b):
    return abs(auc(a, b) - 0.5) * 2


def main():
    hf = [f for f in sorted(glob.glob(os.path.join(HOME, "标杆文章", "*.txt")))
          if not any(x in os.path.basename(f) for x in EXCLUDE)]
    B = os.path.join(HOME, "AI文章")
    af = []
    for d in AI_DIRS:
        af += sorted(glob.glob(os.path.join(B, d, "**", "*.md"), recursive=True))
        af += sorted(glob.glob(os.path.join(B, d, "**", "*.txt"), recursive=True))

    Hb, Ab = load(hf, PERBOOK), load(af, None)
    print(f"真人 {len(hf)} 本 / {len(Hb)} 章    AI {len(af)} 文件 / {len(Ab)} 块")
    print(f"全角空格密度（每千字，章级中位）：真人 "
          f"{st.median([b.count(FWSP) / max(len(re.sub(chr(92) + 's', '', b)), 1) * 1000 for b in Hb]):.2f}"
          f" / AI {st.median([b.count(FWSP) / max(len(re.sub(chr(92) + 's', '', b)), 1) * 1000 for b in Ab]):.2f}")

    # 单趟：每个 body 只算两次 metrics
    raw_h, raw_a, cut_h, cut_a = [], [], [], []
    for b in Hb:
        raw_h.append(q.metrics(b))
        cut_h.append(q.metrics(b.replace(FWSP, "")))
    for b in Ab:
        raw_a.append(q.metrics(b))
        cut_a.append(q.metrics(b.replace(FWSP, "")))

    rows = []
    for k in server.SHOW:
        s1 = sep([m.get(k, 0) or 0 for m in raw_h], [m.get(k, 0) or 0 for m in raw_a])
        s2 = sep([m.get(k, 0) or 0 for m in cut_h], [m.get(k, 0) or 0 for m in cut_a])
        rows.append((abs(s2 - s1), k, s1, s2))
    rows.sort(reverse=True)

    print("\n剥掉全角空格后，各指标分离度的变化")
    print(f"{'指标':<12}{'原样':>8}{'去缩进':>9}{'Δ':>8}   判定")
    for d, k, s1, s2 in rows:
        if d >= 0.10:
            v = "⚠ 严重依赖排版"
        elif d >= 0.05:
            v = "· 轻度依赖排版"
        else:
            v = ""
        print(f"{k:<12}{s1:>8.2f}{s2:>9.2f}{s2 - s1:>+8.2f}   {v}")


if __name__ == "__main__":
    main()
