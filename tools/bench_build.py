#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 基准重建（开发工具，不参与服务运行）

重建 `qc_core.BENCHMARKS`：24 本 × 全书等距 ≤100 章，只存原始指标中位。

用法：
    python3 tools/bench_build.py --corpus <真人标杆语料目录>
    python3 tools/bench_build.py --corpus <目录> --out /tmp/newbench.txt
    python3 tools/bench_build.py --corpus <目录> --verify

    --corpus  真人标杆语料目录（.txt / .md / .markdown）
    --out     把 BENCHMARKS 字面量写到文件（默认只打印到 stdout）
    --verify  不产出，改为与当前 qc_core.BENCHMARKS 逐键比对并报告漂移
    --show-fp 只打印语料目录里各文件的内容指纹

不写死任何语料路径——语料在哪儿由使用者传参决定。

为什么用「内容指纹」而不是文件名 / 排序位置来定代号
--------------------------------------------------
`BENCHMARKS` 的键是匿名代号 B01–B24，仓库里不出现具体书目（见 README「基准从哪来」）。
代号 ↔ 源文件的对应关系一旦搞错，**整张表会静默写坏，而分数看起来完全正常**。

- **按文件名**：改名即失配，且等于把书目写进了仓库。
- **按排序位置**（旧脚本的 `B{i:02d}`）：目录里新增一本书，其后全部错位。
  2026-09-14 实测：旧脚本的 `EXCLUDE` 只列了 2 本，实际剔除的是 5 本，
  直接重跑会产出 `B01..B27`，**B02 之后全体位移**——同一个代号会落到另一本书上，
  整张表静默写坏，而分数看起来完全正常。
- **按内容指纹**：改名、增删文件都不影响，也不暴露作品名。

所以本脚本：
    1. 扫描语料目录，算每个文件的 sha256 前 16 位；
    2. 只认 `FINGERPRINTS` 里登记过的 24 个指纹，其余一律跳过并列出来；
    3. 24 个代号没找齐就直接报错退出，**不产出半成品**。

改语料（换书 / 增删）时：先跑 `--verify` 看现状，再按需更新 `FINGERPRINTS`。
指纹用 `--show-fp` 打印。

其他工具（标定、排版扫描）需要「只保留基准登记的这 24 本」时，直接调
`keep_known()`——同一份指纹表，别各写一份按书名筛的清单。
"""
import argparse
import glob
import hashlib
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# server.py 在 import 时把 argv[1] 当端口号读走，所以先顶上一个合法端口再导入；
# 但 argparse 也要读 sys.argv，原始参数得先留一份。
_ARGV = sys.argv[:]
sys.argv = [sys.argv[0], "8765"]
import qc_core as q          # noqa: E402
import server                # noqa: E402
sys.argv = _ARGV

MINCH = 1200          # 单章可用下限（与拆章过滤同口径）
PERBOOK = 100         # 每本最多抽多少章（全书等距）

# 代号 → 源文件 sha256 前 16 位。**这是代号身份的唯一来源**，不要改成文件名或顺序。
FINGERPRINTS = {
    "B01": "ef59d8c8617b2310",
    "B02": "410b7af2264cf893",
    "B03": "f1a9bf3d88e37b18",
    "B04": "7fd743d4e48ae5c5",
    "B05": "d2df75c6f0dc2843",
    "B06": "f843057bea77c9d8",
    "B07": "c8e9af246e80cbf2",
    "B08": "5eb9483c6493a711",
    "B09": "e057a26e53495f71",
    "B10": "303535f2a8e19636",
    "B11": "9e461b668b670103",
    "B12": "86915016665cfb9c",
    "B13": "de6a16bb084360e3",
    "B14": "ee1a93683792f3d9",
    "B15": "884e77e6ada958a7",
    "B16": "4ba43c5d1ff7acb6",
    "B17": "bd31dda7a4efc066",
    "B18": "f35f5ed336cdfe91",
    "B19": "5b37e4922aeea88b",
    "B20": "19308a35fd9dcff6",
    "B21": "67d75fa56504f45c",
    "B22": "347f72503f56600d",
    "B23": "03c1cfd7c133d34b",
    "B24": "e5c5394c0ee4129e",
}

FP2CODE = {v: k for k, v in FINGERPRINTS.items()}
KEYS = list(server.SHOW)          # 42 项，顺序即 BENCHMARKS 字面量里的键序


def keep_known(paths):
    """只留下 `FINGERPRINTS` 里登记过的文件，返回 (保留, 剔除)。

    真人标杆目录里通常混着几本不可用的（拆不出章 / 疑似合章）。标定阈值、
    扫排版噪声这些**依赖真人中位**的工具都必须先筛，否则 5 本坏书会把中位
    算歪。**不要在别处另写一份按书名筛的清单**——那既会随书目变动失配，
    也等于把作品名写进仓库（项目铁律：一律匿名）。
    """
    keep = [f for f in paths if fingerprint(f) in FP2CODE]
    return keep, [f for f in paths if f not in set(keep)]


def fingerprint(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def pick(path):
    """一本完整的书 → 全书等距 ≤PERBOOK 章。"""
    t = open(path, encoding="utf-8", errors="ignore").read()
    ch = [b for _, b in q.split_chapters(t)
          if len(re.sub(r"\s", "", b)) >= MINCH]
    if len(ch) > PERBOOK:
        step = len(ch) / PERBOOK
        ch = [ch[int(i * step)] for i in range(PERBOOK)]
    return ch


def build(corpus):
    """返回 {代号: {_n, 各指标中位}}，按代号排序；同时报告跳过/缺失。"""
    files = []
    for ext in ("*.txt", "*.md", "*.markdown"):
        files += glob.glob(os.path.join(corpus, "**", ext), recursive=True)
    files = sorted(f for f in files if not f.endswith(".DS_Store"))

    books, unknown, seen = {}, [], set()
    for f in files:
        fp = fingerprint(f)
        code = FP2CODE.get(fp)
        if not code:
            unknown.append(os.path.basename(f)[:24])
            continue
        seen.add(code)
        chs = pick(f)
        if not chs:
            print(f"  [无可用章] {code} —— {os.path.basename(f)[:24]}", file=sys.stderr)
            continue
        ms = [q.metrics(b) for b in chs]
        d = {"_n": len(chs)}
        for k in KEYS:
            d[k] = round(st.median([m.get(k, 0.0) or 0.0 for m in ms]), 4)
        books[code] = d

    missing = sorted(set(FINGERPRINTS) - seen)
    if missing:
        print(f"\n[错误] 有 {len(missing)} 个代号在语料目录里找不到：{'、'.join(missing)}",
              file=sys.stderr)
        print("       代号按内容指纹认领。若语料确实换过，请用 --show-fp 核对并更新 "
              "FINGERPRINTS，不要直接重跑。", file=sys.stderr)
        sys.exit(1)
    if unknown:
        print(f"\n[跳过] {len(unknown)} 个文件未登记（不参与基准）："
              f"{'、'.join(unknown[:8])}{' 等' if len(unknown) > 8 else ''}")
    return books


def literal(books):
    lines = ["BENCHMARKS = {"]
    for code in sorted(books):
        items = ", ".join(f"'{k}': {v}" for k, v in books[code].items())
        lines.append(f'    "{code}": {{{items}}},')
    lines.append("}")
    return "\n".join(lines)


def verify(books):
    """与当前 qc_core.BENCHMARKS 逐键比对。返回漂移条数。"""
    cur = q.BENCHMARKS
    drift = {}
    for code in sorted(set(books) | set(cur)):
        a, b = cur.get(code, {}), books.get(code, {})
        for k in sorted(set(a) | set(b)):
            va, vb = a.get(k), b.get(k)
            if va != vb:
                drift.setdefault(code, []).append((k, va, vb))
    if not drift:
        print("\n[零漂移] 24 本 × %d 键与当前 BENCHMARKS 完全一致。" % len(KEYS))
        return 0
    n = sum(len(v) for v in drift.values())
    print(f"\n[漂移] {len(drift)} 本 / {n} 个键与当前 BENCHMARKS 不一致：")
    for code in sorted(drift):
        for k, va, vb in drift[code][:6]:
            print(f"    {code}.{k:<10} 现 {va} → 新 {vb}")
        if len(drift[code]) > 6:
            print(f"    {code} …另有 {len(drift[code]) - 6} 个键")
    return n


def main():
    ap = argparse.ArgumentParser(description="墨尺基准重建")
    ap.add_argument("--corpus", required=True, help="真人标杆语料目录")
    ap.add_argument("--out", help="把 BENCHMARKS 字面量写到该文件")
    ap.add_argument("--verify", action="store_true",
                    help="与当前 qc_core.BENCHMARKS 比对漂移，不产出")
    ap.add_argument("--show-fp", action="store_true",
                    help="只打印语料目录里各文件的内容指纹")
    a = ap.parse_args()

    if not os.path.isdir(a.corpus):
        sys.exit(f"不是目录：{a.corpus}")

    if a.show_fp:
        for f in sorted(glob.glob(os.path.join(a.corpus, "**", "*.txt"),
                                  recursive=True)):
            print(f"  {fingerprint(f)}  {os.path.basename(f)[:32]}")
        return

    books = build(a.corpus)
    print(f"\n{len(books)} 本 × {len(KEYS)} 键"
          f"（每本 ≤{PERBOOK} 章，单章 ≥{MINCH} 字，中位取 statistics.median）")
    for code in sorted(books):
        sc = {k: q.score_real(books[code])[1] if k == "real" else
              q.score_human(books[code])[1] if k == "human" else
              q.score_imm(books[code])[1] if k == "imm" else
              q.score_rhy(books[code])[1] if k == "rhy" else
              q.score_syn(books[code])[1] for k in ("real", "human", "imm", "rhy", "syn")}
        sc["total"] = q.score_total(sc)
        print(f"  {code}  {books[code]['_n']:>4} 章  " +
              "  ".join(f"{k}={v:5.2f}" for k, v in sc.items()))

    if a.verify:
        sys.exit(1 if verify(books) else 0)

    text = literal(books)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n已写出 {a.out}（人工核对后写入 qc_core.py）")
    else:
        print()
        print(text)


if __name__ == "__main__":
    main()
