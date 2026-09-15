#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 叙事结构诊断（开发工具，不参与打分、不参与服务运行）

⚠ **性质：诊断视图，不是指标。**
实测（2026-09-14）：本文件算出的 6 个叙事候选，`sep` 全部 ≤ 0.48，其中最高的一条
（动作句占比 0.45）还是已有项 `act` 的回声。详见
`.workbuddy/notes/外部扩展模块复用性评估_三模块18规则.md`。
所以它**不进五维、不进 `server.SHOW`、不碰 `BENCHMARKS`**——只给作者看自己的文本结构。

本文件同时是外部 `ai_detector_ext.py`（3 模块 18 规则）的**修正版**：
保留它唯一站得住的设计思路（逐句分类 → 类型序列 → 转移统计），修掉 6 处缺陷。

用法：
    python3 tools/narrative.py <文件>
    python3 tools/narrative.py <文件> --window 2000 --step 1000

修了什么（每条都可复现）
------------------------
1. **自转换率恒为 0** —— 原版 N2 是条死规则。
   原版先「合并相邻同类片段」再统计转移矩阵，于是
   `merged[i].kind != merged[i+1].kind` 按构造成立，**对角线永远为空**。
   本版在**句级序列**（未合并）上统计转移，自转换率才有意义；
   「同类型连续长度」另用「平均片段长度」表达，两者分工不重叠。
2. **转移熵算错了对象** —— 原版 N1。
   原版 `shannon_entropy(所有转移次数)` 是「**次数**分布的熵」，随文本长度单调变化。
   本版用条件熵 `H(next|cur) = Σ_a p(a)·H(next|a)`，单位 bit，与长度无关。
3. **滑动窗口端点越界** —— 原版模块一。
   原版上界 `max(1, n - min_chars + 1)`，尾部窗口被 `min(s+window, n)` 截短，
   变长窗口喂给长度敏感指标（句长CV / TTR）= 长度噪声。本版上界 `n - window + 1`，
   **窗口等长**，且默认只报**未被 `good()` 夹取**的原始指标（见下方「为什么不用分数」）。
4. **修饰链「的」计数名不副实** —— 原版 S4。
   原版算的是「25 字滑动窗内『的』个数的最大值」，不是修饰链深度，
   且把 目的 / 的确 / 的士 一起算了。本版改用 `qc_core.DEDE` 的同口径，改名「的的连用」。
5. **特征缺失时输出满分** —— 原版 S3。
   原版在无 jieba 时返回全 0 特征，而 `scale_down(0, 0.05, 0.20) = 100`
   → 假阳性「高度疑似 AI」。本版统一 **None 语义**：不适用就跳过，不折算成分。
6. **引号解析未按奇偶配对** —— 原版 classify。
   原版 `"".join(DIALOGUE_RE.findall(sentence))` 遇捕获组会抛 TypeError；
   且 ASCII 引号开闭同字符，必须按出现次序交替配对。本版复用
   `qc_core.net_stats` 的「奇偶配对、不成对整段作废（宁缺勿错）」口径。

为什么不用分数
--------------
原版把 18 条规则的**手猜** `lo/hi` 折成 0–100 再加权平均，得到一个无标定依据的
「综合 AI 味分」。本文件**不输出任何 0–100 分**，只给原始统计量。
模块一的「窗口一致性」同理：`good()` 把分数夹在 0–10，**用夹取后的分数算波动会被
天花板污染**（实测 `r(每本均分, 跨章CV) = −0.780`，`sep 0.82` 是假象）。
所以本版的窗口波动一律在**原始指标**上算。

有意不做
--------
**不引入 jieba / LTP**（项目铁律：零依赖）。原版模块二的词性熵、名动相邻率、
依存距离因此**整体不做**——它们在墨尺语料上也测不出增量：句法维 `sep` 已 0.9988。

只依赖 Python 标准库。词典全部复用 `qc_core`，不新增任何词表。
"""

import argparse
import math
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qc_core as q                                  # noqa: E402

KIND = ("对话", "心理", "动作", "描写", "叙述")
WSP = re.compile(r"\s")
QRE = re.compile("[" + q.QALL + "]")
MIN_DEN = 3.0          # 每千字命中数低于此值 → 归「叙述」
MIN_CH = 400           # 整篇可用下限
MIN_SENT = 12          # 句数下限

# 分类词典：**全部来自 qc_core**，不新增词表。
# 原版自带的 PSYCH_MARKERS / WEATHER_MARKERS / DIALOGUE_TAG_MARKERS 与墨尺已有项
# 大量重叠（觉得/想起 ≈ TELL，说道 ≈ 对话标签），引进来只会制造回声。
PSYCH = re.compile("(?:" + "|".join([
    q.COG.pattern, q.LYRIC.pattern, q.TELL.pattern,
    r"心里|心中|内心|脑海|心想|暗想|念头|回忆|想起|思忖|琢磨|寻思|盘算",
]) + ")")
ACT = re.compile("(?:" + "|".join([q.ACT.pattern, q.NOD.pattern]) + ")")
DESC = re.compile("(?:" + "|".join([
    q.TOUCH_TEMP.pattern, q.SOMA.pattern, q.PERC.pattern, q.SPACE.pattern,
]) + ")")

# 窗口波动用的原始指标（**都不过 good()**，因此不受 0–10 夹取影响）
RAW = ("sent_med", "para_med", "comma_in", "sent_den", "cv", "emo", "dede")


def cn(s):
    """汉字/非空白字符数。"""
    return len(WSP.sub("", s))


def quoted_chars(p):
    """段内成对引号包住的字数。

    引号不成对 → 返回 None（整段作废，宁缺勿错）。与 `qc_core.net_stats` 同口径：
    所有引号字符（弯 / 直 / 直角）按**出现次序奇偶配对**，偶位开、奇位闭。
    """
    pos = [m.start() for m in QRE.finditer(p)]
    if not pos or len(pos) % 2:
        return None
    return sum(cn(p[pos[i] + 1:pos[i + 1]]) for i in range(0, len(pos), 2))


def classify(sent):
    """单句 → 类型。对话优先（含引号），其余按词典密度取最大者，都不够则「叙述」。"""
    if QRE.search(sent):
        return "对话"
    n = max(cn(sent), 1)
    best, val = "叙述", MIN_DEN
    for k, pat in (("心理", PSYCH), ("动作", ACT), ("描写", DESC)):
        v = len(pat.findall(sent)) / n * 1000.0
        if v > val:
            best, val = k, v
    return best


def kinds_of(body):
    """逐句类型序列（**不合并**——转移统计必须在合并前做，见修复 1）。"""
    return [classify(s) for s in q.sentences(body)]


def runs_of(seq):
    """同类型连续段的长度列表（描述「同类型聚集程度」，与自转换率分工不同）。"""
    out = []
    for k in seq:
        if out and out[-1][0] == k:
            out[-1][1] += 1
        else:
            out.append([k, 1])
    return out


def transition(seq):
    """转移矩阵 + 自转换率 + 条件熵（修复 1、2）。"""
    trans = defaultdict(Counter)
    for i in range(len(seq) - 1):
        trans[seq[i]][seq[i + 1]] += 1
    ntr = sum(sum(c.values()) for c in trans.values())
    if not ntr:
        return trans, 0.0, 0.0
    self_r = sum(trans[a][a] for a in KIND) / ntr
    # 条件熵 H(next|cur)，bit：对每个当前态算其下一态的熵，再按出现频率加权
    ce = 0.0
    for a in KIND:
        ta = sum(trans[a].values())
        if not ta:
            continue
        h = -sum((c / ta) * math.log2(c / ta) for c in trans[a].values() if c)
        ce += (ta / ntr) * h
    return trans, self_r, ce


def narrative(body):
    """叙事结构诊断。返回 dict；样本不足返回 None。"""
    ps = q.paras(body)
    tot = sum(cn(p) for p in ps)
    if tot < MIN_CH:
        return None
    qc = sum(v for v in (quoted_chars(p) for p in ps) if v is not None)
    seq = kinds_of(body)
    if len(seq) < MIN_SENT:
        return None
    cnt = Counter(seq)
    runs = runs_of(seq)
    trans, self_r, ce = transition(seq)
    return {
        "句数": len(seq),
        "对话字数占比": qc / tot,
        "对话句占比": cnt.get("对话", 0) / len(seq),
        "心理句占比": cnt.get("心理", 0) / len(seq),
        "动作句占比": cnt.get("动作", 0) / len(seq),
        "描写句占比": cnt.get("描写", 0) / len(seq),
        "叙述句占比": cnt.get("叙述", 0) / len(seq),
        "片段数": len(runs),
        "平均片段长度": st.mean([r[1] for r in runs]),
        "自转换率": self_r,
        "转移条件熵": ce,
        "_trans": trans,
    }


def window_profile(body, window, step):
    """等长窗口下，**原始指标**的跨窗波动（修复 3 + 绕开天花板）。

    返回 [(起始, 字数, {指标: 值}), ...]。

    两个要点：
    - **窗口一律等长**，尾窗不足直接丢弃。原版保留变长尾窗，等于往长度敏感指标
      （句长CV / TTR）里灌长度噪声。
    - **必须在保留换行的原文上切**。若先 `re.sub(r"\\s", "", body)` 再切，
      换行会被一起删掉、段落结构被抹平，`para_med` 会退化成窗口长度本身。
    """
    n = len(body)
    if n < window:
        return []
    out = []
    for s in range(0, n - window + 1, step):
        chunk = body[s:s + window]
        m = q.metrics(chunk)
        out.append((s, window, {k: m.get(k) for k in RAW}))
    return out


def cv(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 3:
        return None
    mu = st.mean(xs)
    return st.pstdev(xs) / mu if mu else None


def main():
    ap = argparse.ArgumentParser(description="墨尺叙事结构诊断（不进打分）")
    ap.add_argument("path", help="文本文件（.txt/.md/.markdown）")
    ap.add_argument("--window", type=int, default=2000, help="窗口字数，默认 2000")
    ap.add_argument("--step", type=int, default=1000, help="滑动步长，默认 1000")
    a = ap.parse_args()

    if os.path.isdir(a.path):
        sys.exit("不是文件（是目录）：%s" % a.path)
    if not os.path.exists(a.path):
        sys.exit("找不到文件：%s" % a.path)

    body = open(a.path, encoding="utf-8", errors="ignore").read()
    r = narrative(body)
    print("=" * 74)
    print("叙事结构诊断　%s" % os.path.basename(a.path))
    print("=" * 74)
    if not r:
        print("  样本不足（需 ≥%d 字且 ≥%d 句）" % (MIN_CH, MIN_SENT))
        return

    print("  句数 %d　片段数 %d　平均片段长度 %.2f 句"
          % (r["句数"], r["片段数"], r["平均片段长度"]))
    print()
    print("  类型分布（按句数）：")
    for k in KIND:
        v = r[k + "句占比"]
        bar = "█" * int(round(v * 30)) + "·" * (30 - int(round(v * 30)))
        print("    %s %s %6.1f%%" % (k, bar, v * 100))
    print("    对话字数占比（按引号配对）  %6.1f%%" % (r["对话字数占比"] * 100))

    print()
    print("  转移（句级，**含对角线** —— 原版在这里恒为空）：")
    print("        " + "".join("%8s" % k for k in KIND) + "%8s" % "行合计")
    tr = r["_trans"]
    for x in KIND:
        row = tr[x]
        tot = sum(row.values())
        print("  %-4s" % x + "".join(
            "%8.3f" % (row[y] / tot if tot else 0.0) for y in KIND) + "%8d" % tot)
    print("  自转换率 %.3f　转移条件熵 %.3f bit" % (r["自转换率"], r["转移条件熵"]))

    wp = window_profile(body, a.window, a.step)
    print()
    print("  跨窗波动（窗口 %d 字 / 步长 %d，等长窗口 %d 个；"
          "**原始指标，不过 good()**）" % (a.window, a.step, len(wp)))
    if len(wp) < 3:
        print("    窗口不足 3 个，跳过")
    else:
        print("    %-10s%12s%12s%12s" % ("指标", "跨窗中位", "跨窗CV", "极差"))
        for k in RAW:
            vs = [w[2][k] for w in wp if w[2][k] is not None]
            if len(vs) < 3:
                continue
            print("    %-10s%12.4f%12.4f%12.4f"
                  % (k, st.median(vs), cv(vs) or 0.0, max(vs) - min(vs)))
    print()
    print("  ⚠ 这是诊断视图，不进打分。实测这 6 个候选 sep 全部 ≤0.48，")
    print("    最高的一条（动作句占比）还是已有项 act 的回声。")


if __name__ == "__main__":
    main()
