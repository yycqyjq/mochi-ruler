#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 零回归验证（开发工具，不参与服务运行）

README「改完要跑零回归」的执行工具：**用同一批素材，把改动前后
`server.analyze()` 的输出逐字段比对**，确认漂移只落在预期字段，其余逐字节一致。

用法（两步 dump + 一步 compare）：

    # 1) 取改动前的干净树（不动当前工作区）
    git worktree add --detach /tmp/mochi_old <改动前的 commit>

    # 2) 分别导出：--tree 指定用哪棵树里的 qc_core / server 算分
    python3 tools/regress.py --tree /tmp/mochi_old --corpus <语料> --per 20 \\
        --dump /tmp/base.json
    python3 tools/regress.py --corpus <语料> --per 20 --dump /tmp/new.json

    # 3) 比对。--allow 列出「本次改动**预期**会漂移」的字段名
    python3 tools/regress.py --compare /tmp/base.json /tmp/new.json \\
        --allow head,redupl,human,total

退出码：compare 时 0 = 无未预期漂移，1 = 有（可直接用在 CI / 提交前检查）。

为什么要有 `--allow`：任何一次改动都**必然**带来漂移（否则等于没改）。零回归不是
「输出完全一样」，而是「**漂移全部落在预期字段内**」——把预期写成白名单，剩下的
任何一处不同都会被点名。

漂移按「字段签名」聚合：`chapters.#.items.redupl` 与 `chapters.#.items.emo`
归成两种签名，逐章逐键列出，不会淹没在几百行输出里。
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_tree(root):
    """导入指定树里的 qc_core / server。

    server.py 在 import 时把 argv[1] 当端口号读走，所以先顶上一个合法端口。
    """
    root = os.path.abspath(root)
    sys.path.insert(0, root)
    _argv = sys.argv[:]
    sys.argv = [sys.argv[0], "8765"]
    try:
        # 必须先清掉缓存：--tree 指到另一棵树时，不清理会静默复用已导入的旧模块，
        # 于是「两棵树」跑出完全一样的输出——一个永远通过的假零回归。
        for m in ("qc_core", "server"):
            sys.modules.pop(m, None)
        import qc_core as q
        import server as srv
    finally:
        sys.argv = _argv
    return q, srv


def corpus_chapters(q, paths, per):
    """把语料展开成 [(标签, 章文本)]。per 限制每本抽多少章（全书等距）。"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            import glob
            for ext in ("*.txt", "*.md", "*.markdown"):
                for f in sorted(glob.glob(os.path.join(p, "**", ext),
                                          recursive=True)):
                    rel = os.path.relpath(f, p)
                    if any(s.startswith(".") for s in rel.split(os.sep)):
                        continue
                    files.append(f)
        else:
            files.append(p)
    out = []
    for f in sorted(files):
        if f.endswith(".DS_Store"):
            continue
        try:
            t = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        chs = [b for _, b in q.split_chapters(t)
               if len(re.sub(r"\s", "", b)) >= 300]
        if per and len(chs) > per:
            step = len(chs) / per
            chs = [chs[int(i * step)] for i in range(per)]
        base = os.path.basename(f)[:28]
        for i, b in enumerate(chs):
            out.append((f"{base}#{i}", b))
    return out


def dump(tree, paths, per, out_path):
    q, server = load_tree(tree)
    items = corpus_chapters(q, paths, per)
    print(f"[{tree}] 语料 {len(items)} 章，开始 analyze …")
    res = {}
    for i, (tag, body) in enumerate(items):
        res[tag] = server.analyze(body, name=tag)
        if (i + 1) % 100 == 0:
            print(f"  … {i + 1}/{len(items)}")
    # sort_keys 保证「同一份内容 → 同一串字节」，比对才有意义
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, sort_keys=True,
                  separators=(",", ":"))
    print(f"已写出 {out_path}（{len(res)} 章）")


IDX = re.compile(r"#\d+")


def signature(path):
    """把逐章路径折叠成字段签名：chapters.#.items.redupl → items.redupl"""
    p = path.split(".") if path else []
    p = [s for s in p if not IDX.search(s)]
    return ".".join(p) or "(根)"


def _is_scalar_list(x):
    """纯标量列表（如 items / dimitems.real 这种「键名清单」）。"""
    return (isinstance(x, list) and
            all(e is None or isinstance(e, (str, int, float, bool)) for e in x))


def walk(a, b, path, drifts):
    """收集漂移。

    **键增删 / 列表元素增删单独记为一条**，路径上带上那个键名
    （如 `items.head`、`label.head`）——否则删掉一个键会让后面所有元素位置
    错位，比对结果被几百行「位置偏移」淹没，真正的改动反而看不见。
    带上键名之后，`--allow head` 就能一次性覆盖这个键在所有容器里的增删。
    """
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a:
                drifts.append((p, "(无此键)", b[k]))
            elif k not in b:
                drifts.append((p, a[k], "(键已删除)"))
            else:
                walk(a[k], b[k], p, drifts)
        return
    if _is_scalar_list(a) and _is_scalar_list(b):
        sa, sb = set(a), set(b)
        for e in sorted(sa - sb, key=str):
            drifts.append((f"{path}.{e}", "(存在)", "(已删除)"))
        for e in sorted(sb - sa, key=str):
            drifts.append((f"{path}.{e}", "(无)", "(新增)"))
        if sa == sb and a != b:
            drifts.append((path + ".order", a, b))
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            drifts.append((path + ".len", len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}.#{i}", drifts)
        return
    if a != b:
        drifts.append((path, a, b))


def compare(pa, pb, allow):
    A = json.load(open(pa, encoding="utf-8"))
    B = json.load(open(pb, encoding="utf-8"))
    if set(A) != set(B):
        print(f"[错误] 两份 dump 的章节集合不同："
              f"仅 A 有 {len(set(A) - set(B))} 章，仅 B 有 {len(set(B) - set(A))} 章")
        return 1

    drifts = []
    for tag in sorted(A):
        walk(A[tag], B[tag], "", drifts)

    # 按签名聚合
    agg = {}
    for path, va, vb in drifts:
        agg.setdefault(signature(path), []).append((path, va, vb))

    print("=" * 92)
    print(f"比对 {len(A)} 章　漂移 {len(drifts)} 处　字段签名 {len(agg)} 种")
    print("=" * 92)
    allow = set(allow)
    unexpected = []
    for sig in sorted(agg):
        rows = agg[sig]
        hit = sig.split(".")[-1] in allow or sig in allow
        mark = "  预期" if hit else "  ✗ 未预期"
        if not hit:
            unexpected.append(sig)
        print(f"\n[{sig}]  {len(rows)} 处{mark}")
        for path, va, vb in rows[:4]:
            print(f"    {path}\n        {va!r} → {vb!r}")
        if len(rows) > 4:
            print(f"    …另有 {len(rows) - 4} 处")

    print("\n" + "=" * 92)
    if unexpected:
        print(f"✗ 有 {len(unexpected)} 种字段签名出现**未预期**漂移："
              f"{'、'.join(unexpected)}")
        print("  要么改坏了，要么该把它们加进 --allow 并说明为什么预期。")
        return 1
    print(f"✓ 零回归通过：漂移只落在预期字段（{'、'.join(sorted(allow)) or '无'}）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="墨尺零回归验证")
    ap.add_argument("--tree", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), help="用哪棵树算分")
    ap.add_argument("--corpus", nargs="+", help="语料路径（目录或文件）")
    ap.add_argument("--per", type=int, default=20, help="每本最多抽多少章")
    ap.add_argument("--dump", help="把 analyze 结果写成 JSON")
    ap.add_argument("--compare", nargs=2, metavar=("BASE", "NEW"),
                    help="比对两份 dump")
    ap.add_argument("--allow", default="",
                    help="预期会漂移的字段名，逗号分隔")
    a = ap.parse_args()

    if a.compare:
        sys.exit(compare(a.compare[0], a.compare[1],
                         [x.strip() for x in a.allow.split(",") if x.strip()]))
    if not a.dump or not a.corpus:
        sys.exit("需要 --dump 与 --corpus（或用 --compare）")
    dump(a.tree, a.corpus, a.per, a.dump)


if __name__ == "__main__":
    main()
