#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 静态自检（开发工具，不参与服务运行）

扫三类「静态检查一秒能抓、但人工评审容易漏」的问题——2026-09-23 体检时
这三类**各真实踩过一次**，都是静默故障：

  ① CSS 变量未定义：`var(--rule-strong)` 全站只在用它的那一行出现过，从未定义
     → 浏览器不报错，那行样式只是**静默失效**（十字线画出来也没颜色）。
  ② JS `const` 重新赋值：`const list = ...` 紧接着 `list = list.filter(...)`
     → 运行时抛 TypeError，整条功能路径崩掉（按「只看有违规」就崩）。
  ③ 前端项数漂移：`DIM_ITEMS_FALLBACK` 与 `index.html` 的「N 项」是**手写的**，
     与 `len(server.SHOW)` 不会自动同步——后端加项后前端静默错列。

零依赖（只用标准库），可安全接进 CI。

用法：
    python3 tools/static_check.py          # 全过 → 退出码 0；有问题 → 1
    python3 tools/static_check.py -v       # 附带每项检查的细节

⚠ 有意**保守**：宁可漏报，不可误报——误报会让人开始忽略这个检查。
   - CSS 只认「静态定义」；JS 里 `setProperty('--x')` 出来的也算已定义，避免误报。
   - const 检查带作用域边界（详见 _check_const_assign），跨函数同名不报。
   - **不查 README 的项数**：里面的旧数字多是历史记录（如「42 → 39 项」），
     按项目纪律该原样保留，查了必误报。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")


# ------------------------------------------------------------------ ① CSS 变量

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
VAR_DEF = re.compile(r"(--[\w-]+)\s*:")
VAR_USE = re.compile(r"var\(\s*(--[\w-]+)")


def _collect_css_text():
    """所有 CSS 来源的文本（.css 全文 + .html 的 <style> 块）。"""
    chunks = []
    for fn in sorted(os.listdir(STATIC)):
        p = os.path.join(STATIC, fn)
        if fn.endswith(".css"):
            chunks.append(("static/" + fn, open(p, encoding="utf-8").read()))
        elif fn.endswith(".html"):
            t = open(p, encoding="utf-8").read()
            for i, blk in enumerate(re.findall(r"<style[^>]*>(.*?)</style>",
                                               t, re.S), 1):
                chunks.append((f"static/{fn} <style#{i}>", blk))
    return chunks


def check_css_vars(verbose):
    """① var(--x) 用了但从未定义。"""
    problems = []
    defined, used = set(), {}
    for name, text in _collect_css_text():
        body = CSS_COMMENT.sub("", text)
        defined |= set(VAR_DEF.findall(body))
        for m in VAR_USE.finditer(body):
            used.setdefault(m.group(1), name)

    # JS 动态设置的变量也算定义（如 el.style.setProperty('--x', v)）
    for fn in sorted(os.listdir(STATIC)):
        if not fn.endswith(".js"):
            continue
        t = open(os.path.join(STATIC, fn), encoding="utf-8").read()
        defined |= set(re.findall(r"setProperty\(\s*['\"](--[\w-]+)", t))

    for var in sorted(set(used) - defined):
        problems.append((used[var], 0, f"{var} 被使用但从未定义 → 该行样式静默失效"))
    if verbose:
        print(f"    CSS 变量：定义 {len(defined)} 个，使用 {len(used)} 个")
    return problems


# ------------------------------------------------------------------ ② const 赋值

CONST_RE = re.compile(r"^(\s*)const\s+([A-Za-z_$][\w$]*)\s*=")
# ⚠ 不能锚行首：赋值常带前缀（`if (x) y = 1`、`return y = 1`）。
# 首次写这版就是锚了 `^(\s*)`，结果漏掉了 `if (chOnlyViol) list = ...` 这个真 bug。
# `(?<![\w$.])` 排除 `obj.prop =` 与 `abcNAME =`；`(?!=|>)` 排除 `==` / `===` / `=>`。
ASSIGN_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*=(?!=|>)")


def _check_const_assign(path, text):
    """找出「const 声明后又赋值」。

    作用域靠**闭合行**判定：每个 const 记录它何时退出作用域（首次出现花括号深度
    低于声明深度的那一行）。赋值时找**最近的、尚未闭合的、且在赋值行之前**的同名
    const——这样 `function a(){const x=1}` 与 `function b(){x=5}` 不会被误判成
    同一个 x（前者在 a 的 `}` 处就已闭合）。

    ⚠ 有意保守：同名 const 若在赋值点之前已全部闭合，就不报（宁漏不误报）。
    """
    out = []
    depth = 0
    consts = {}                       # name -> [ {line, depth, closed}, ... ]
    for i, raw in enumerate(text.splitlines(), 1):
        if raw.strip().startswith("//"):
            depth += raw.count("{") - raw.count("}")
            continue
        m = CONST_RE.match(raw)
        if m:
            consts.setdefault(m.group(2), []).append(
                {"line": i, "depth": depth, "closed": None})
        else:
            for m2 in ASSIGN_RE.finditer(raw):
                cand = [r for r in consts.get(m2.group(1), [])
                        if r["closed"] is None and r["line"] < i]
                if cand:
                    rec = max(cand, key=lambda r: r["line"])
                    out.append((i, m2.group(1), rec["line"]))
                    break
        depth += raw.count("{") - raw.count("}")
        for recs in consts.values():  # 用更新后的深度判「是否已出作用域」
            for r in recs:
                if r["closed"] is None and depth < r["depth"]:
                    r["closed"] = i
    return out


def check_const_assign(verbose):
    """② JS 里 const 声明后又被赋值。"""
    problems = []
    for fn in sorted(os.listdir(STATIC)):
        if not fn.endswith(".js"):
            continue
        p = os.path.join(STATIC, fn)
        hits = _check_const_assign(p, open(p, encoding="utf-8").read())
        for line, name, decl in hits:
            problems.append((f"static/{fn}", line,
                             f"{name} 在第 {decl} 行声明为 const，第 {line} 行又赋值"
                             f" → 运行时抛 TypeError"))
        if verbose:
            print(f"    static/{fn}：{len(hits)} 处 const 重新赋值")
    return problems


# ------------------------------------------------------------------ ③ 项数一致

FALLBACK_BLOCK = re.compile(r"DIM_ITEMS_FALLBACK\s*=\s*\{(.*?)\n\};", re.S)
FALLBACK_LIST = re.compile(r"([A-Za-z_]\w*)\s*:\s*\[(.*?)\]", re.S)
FALLBACK_ITEM = re.compile(r"['\"]([\w]+)['\"]")


def _load_show():
    """拿 server.SHOW（server 在 import 时会把 argv[1] 当端口读走，先顶上）。"""
    sys.path.insert(0, ROOT)
    _argv = sys.argv[:]
    sys.argv = [sys.argv[0], "8765"]
    try:
        for m in ("qc_core", "server"):
            sys.modules.pop(m, None)
        import server
        return list(server.SHOW)
    finally:
        sys.argv = _argv


def check_item_count(verbose):
    """③ 前端硬编码的项数 / 项名清单 与 len(server.SHOW) 是否一致。"""
    problems = []
    show = _load_show()
    n = len(show)
    if verbose:
        print(f"    server.SHOW：{n} 项")

    # (a) app.js 的 DIM_ITEMS_FALLBACK：总数 + 项名集合
    js = open(os.path.join(STATIC, "app.js"), encoding="utf-8").read()
    blk = FALLBACK_BLOCK.search(js)
    if not blk:
        problems.append(("static/app.js", 0, "找不到 DIM_ITEMS_FALLBACK 定义"))
    else:
        items, per = [], []
        for dim, body in FALLBACK_LIST.findall(blk.group(1)):
            got = FALLBACK_ITEM.findall(body)
            items += got
            per.append(f"{dim}={len(got)}")
        if len(items) != n:
            problems.append(("static/app.js", 0,
                             f"DIM_ITEMS_FALLBACK 共 {len(items)} 项"
                             f"（{', '.join(per)}），server.SHOW 是 {n} 项"))
        miss, extra = set(show) - set(items), set(items) - set(show)
        if miss or extra:
            problems.append(("static/app.js", 0,
                             f"DIM_ITEMS_FALLBACK 与 SHOW 的项名不符："
                             f"缺 {sorted(miss) or '无'} / 多 {sorted(extra) or '无'}"))
        if verbose:
            print(f"    DIM_ITEMS_FALLBACK：{len(items)} 项（{', '.join(per)}）")

    # (b) index.html 的「N 项」
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    for i, line in enumerate(html.splitlines(), 1):
        for m in re.finditer(r"(\d+)\s*项", line):
            if int(m.group(1)) != n:
                problems.append(("static/index.html", i,
                                 f"文案写「{m.group(1)} 项」，server.SHOW 是 {n} 项"))
    if verbose:
        print("    index.html：项数文案已核对")
    return problems


# ------------------------------------------------------------------ 主流程

CHECKS = [
    ("① CSS 变量未定义", check_css_vars),
    ("② JS const 重新赋值", check_const_assign),
    ("③ 前端项数 / 项名与 SHOW 一致", check_item_count),
]


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    print(f"墨尺静态自检（根目录 {ROOT}）\n")
    total = 0
    for title, fn in CHECKS:
        print(f"  {title}")
        try:
            problems = fn(verbose)
        except Exception as e:                      # noqa: BLE001
            print(f"    ✗ 检查本身出错：{type(e).__name__}: {e}")
            total += 1
            continue
        if not problems:
            print("    ✓ 无问题")
            continue
        total += len(problems)
        for path, line, msg in problems:
            loc = f"{path}:{line}" if line else path
            print(f"    ✗ {loc}  {msg}")
    print()
    if total:
        print(f"✗ 共 {total} 个问题（见上）")
        return 1
    print("✓ 静态自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
