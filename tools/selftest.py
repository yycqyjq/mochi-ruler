#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""墨尺 · 无语料自测（开发工具，不参与服务运行）

不依赖任何标杆语料，构造用例即可跑：提交前与 CI 必过的一道门。
覆盖四块：
    1 拆章    各章头格式拆得预期章数；目录行选型不被带偏；<300 字碎片丢弃
    2 评分    good() 双向阈值与 None 语义、_wavg 跳过归一、退出打分项返回 None
    3 完整性  metrics() 恒产 47 键；SHOW / DESC / LABEL / BENCHMARKS /
              ITEM_TARGET 互相对得上（改指标漏同步时在这里炸，而不是线上 500）
    4 冒烟    server.analyze 全链路（含「整篇」兜底）与合规硬规则

用法：
    python3 tools/selftest.py            # 静默跑，失败才出栈
    python3 tools/selftest.py -v         # 逐用例

标杆语料相关的深度体检（分离度 / 左尾 / 泛化）不在这里——那是 audit.py /
expand_eval.py 的活，需要本地语料；本文件只保证「评分核心没被改坏」。
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# server 在 import 时把 sys.argv[1] 当端口解析；带 -v 运行会把 '-v' 炸成
# ValueError，所以 import 期间先摘掉参数，import 完再还给 unittest。
_argv = sys.argv
sys.argv = [_argv[0]]
import qc_core as q                          # noqa: E402
import server                                # noqa: E402
sys.argv = _argv

# 单段正文（约 84 字），重复 4 次拼成 ≥300 字的「有效章」
PARA = ("天擦黑，雨又落下来了。风从门缝里钻进来，吹得灯苗歪向一边，"
        "影子在墙上晃了两下，又不动了。他把柴卸在屋檐下，捆绳一松，"
        "柴散了一地，手指冻得发僵，捏不住细的，只好一根一根慢慢来。")
B = PARA * 4


class SplitChapters(unittest.TestCase):
    """拆章：README「拆章规则」表里的每种格式 + 两条护栏。"""

    def _titles(self, text):
        return [t for t, _ in q.split_chapters(text)]

    def test_markdown(self):
        self.assertEqual(
            self._titles(f"# 第一章 入夜\n\n{B}\n\n# 第二章 敲门\n\n{B}"),
            ["# 第一章 入夜", "# 第二章 敲门"])

    def test_markdown_multi_level(self):
        # 「# 卷名 / ## 第N章」两级 Markdown 结构（2026-09-23 修复）。
        # 原实现只认单个 `#`，会把整篇并成 1 章——实测某标准 AI 目录
        # 45/46 个文件受影响（该目录 53 章 → 523 章）。拆章错 = 测量单位错。
        self.assertEqual(
            self._titles(f"# 第一卷 卷名\n\n## 第1章 入夜\n\n{B}"
                         f"\n\n## 第2章 敲门\n\n{B}"),
            ["## 第1章 入夜", "## 第2章 敲门"])
        # 二～六级都认；「## 楔子」这类特殊章节同样生效
        self.assertEqual(
            self._titles(f"###### 第1章 入夜\n\n{B}\n\n###### 第2章 敲门\n\n{B}"),
            ["###### 第1章 入夜", "###### 第2章 敲门"])
        self.assertEqual(
            self._titles(f"# 书名\n\n## 楔子\n\n{B}\n\n## 第1章 入夜\n\n{B}"),
            ["## 楔子", "## 第1章 入夜"])

    def test_zh_numbered(self):
        self.assertEqual(
            self._titles(f"第一章 入夜\n\n{B}\n\n第二章 敲门\n\n{B}"),
            ["第一章 入夜", "第二章 敲门"])

    def test_colon_after_number(self):
        # 「第X章：标题」必须顶格匹配（2026-09-16 修复的格式）
        self.assertEqual(
            self._titles(f"第1章：入夜\n\n{B}\n\n第2章：敲门\n\n{B}"),
            ["第1章：入夜", "第2章：敲门"])

    def test_two_level_head(self):
        self.assertEqual(
            self._titles(f"第四集 卷名 第十七章 幽深地穴\n\n{B}"
                         f"\n\n第四集 卷名 第十八章 出口\n\n{B}"),
            ["第四集 卷名 第十七章 幽深地穴", "第四集 卷名 第十八章 出口"])

    def test_dun_numbered(self):
        self.assertEqual(
            self._titles(f"1、入夜\n\n{B}\n\n2、敲门\n\n{B}"),
            ["1、入夜", "2、敲门"])

    def test_digit_prefix(self):
        self.assertEqual(
            self._titles(f"书名\n\n01开篇\n\n{B}\n\n02 别离\n\n{B}"),
            ["01开篇", "02 别离"])

    def test_english(self):
        self.assertEqual(
            self._titles(f"Chapter 1\n\n{B}\n\nChapter 2\n\n{B}"),
            ["Chapter 1", "Chapter 2"])

    def test_special_only_book(self):
        # 全书只有「楔子 / 番外」章头时由特殊章节模式接管
        self.assertEqual(
            self._titles(f"楔子\n\n{B}\n\n番外 一\n\n{B}\n\n番外 二\n\n{B}"),
            ["楔子", "番外 一", "番外 二"])

    def test_wedge_before_chapters(self):
        # 混排：开头的楔子靠「第一章」的切点自然成章（现行行为）
        self.assertEqual(
            self._titles(f"楔子\n\n{B}\n\n第一章 入夜\n\n{B}"),
            ["楔子", "第一章 入夜"])

    def test_dir_lines_do_not_hijack_selection(self):
        # 选型判据是「有效段最多」：目录行能把顿点模式的切段数刷得很高，
        # 但都是 <300 字的无效段，不得赢过真正的章号模式（990 万字案例）。
        dirs = "\n".join(f"{i}. {i + 62}" for i in range(1, 41))
        text = f"第一章 入夜\n\n{B}\n\n{dirs}\n\n第二章 敲门\n\n{B}"
        self.assertEqual(self._titles(text), ["第一章 入夜", "第二章 敲门"])

    def test_short_fragment_dropped(self):
        # <300 字碎片直接丢弃：既不单独成章，也不并入相邻章节
        text = f"第一章 入夜\n\n{B}\n\n（未完待续）\n\n第二章 敲门\n\n{B}"
        ts = self._titles(text)
        self.assertEqual(ts, ["第一章 入夜", "第二章 敲门"])


class Scoring(unittest.TestCase):
    """good() 双向阈值、None 语义、退出打分项。"""

    def test_good_directions(self):
        # 越低越好：target < over
        self.assertEqual(q.good(1.0, 1.0, 3.0), 10.0)
        self.assertEqual(q.good(3.0, 1.0, 3.0), 0.0)
        self.assertEqual(q.good(2.0, 1.0, 3.0), 5.0)
        # 越高越好：target > over（公式自带方向，不需要方向表）
        self.assertEqual(q.good(3.0, 3.0, 1.0), 10.0)
        self.assertEqual(q.good(1.0, 3.0, 1.0), 0.0)
        self.assertEqual(q.good(2.0, 3.0, 1.0), 5.0)
        # None = 本章不适用；退化阈值；越界夹紧
        self.assertIsNone(q.good(None, 1.0, 3.0))
        self.assertEqual(q.good(5.0, 1.0, 1.0), 0.0)
        self.assertEqual(q.good(-9.0, 1.0, 3.0), 10.0)
        self.assertEqual(q.good(99.0, 1.0, 3.0), 0.0)

    def test_retired_items_return_none(self):
        # 退出打分的项：原始值照算，item_score 必须是 None（前端显示 —）
        for k, v in (("ttr", 50.0), ("net_short", 0.4), ("enum", 1.2),
                     ("imm_cog", 0.5), ("imm_perc", 1.0), ("imm_soma", 2.0)):
            self.assertIsNone(q.item_score(k, v), k)

    def test_show_items_all_have_thresholds(self):
        for k in server.SHOW:
            self.assertIsNotNone(q.ITEM_TARGET.get(k), k)
            self.assertIsNotNone(q.item_score(k, 0.0), k)

    def test_wavg_skips_none_and_renormalizes(self):
        self.assertAlmostEqual(q._wavg({"a": 10.0, "b": 0.0}, {"a": 1, "b": 3}), 2.5)
        self.assertAlmostEqual(q._wavg({"a": 10.0, "b": None}, {"a": 1, "b": 3}), 10.0)
        self.assertEqual(q._wavg({}, {"a": 1}), 0.0)

    def test_score_functions_in_range(self):
        m = q.metrics(B)
        dims = {}
        for name, fn in (("real", q.score_real), ("human", q.score_human),
                         ("imm", q.score_imm), ("rhy", q.score_rhy),
                         ("syn", q.score_syn)):
            items, dim = fn(m)
            self.assertTrue(0.0 <= dim <= 10.0, name)
            for v in items.values():
                self.assertTrue(v is None or 0.0 <= v <= 10.0)
            dims[name] = dim
        # 总分 = 五维等权平均
        self.assertAlmostEqual(q.score_total(dims), sum(dims.values()) / 5.0, places=9)

    def test_dial_sent_none_without_dialogue(self):
        self.assertIsNone(q.metrics(B)["dial_sent"])
        self.assertIsInstance(q.metrics("“进来吧。”他侧了侧身。" + B)["dial_sent"], float)


class Integrity(unittest.TestCase):
    """多层清单互相对得上：改指标漏同步时在这里炸，而不是接口 500。"""

    EXTRA = {"chars", "ttr", "net_short", "enum", "imm_perc", "imm_cog", "imm_soma"}

    def test_metrics_47_keys_on_edge_inputs(self):
        for text in ("", " ", "他走了。", "“对。”", "……", PARA, PARA * 4, PARA * 40):
            m = q.metrics(text)
            self.assertEqual(set(m), set(server.SHOW) | self.EXTRA,
                             f"键数不符：{text[:12]!r}")
            for v in m.values():
                if isinstance(v, float):
                    self.assertTrue(math.isfinite(v))

    def test_show_is_40_unique(self):
        self.assertEqual(len(server.SHOW), 40)
        self.assertEqual(len(set(server.SHOW)), 40)

    def test_labels_desc_rawdir_cover_show(self):
        for k in server.SHOW:
            self.assertIn(k, server.LABEL, k)
            self.assertIn(k, server.DESC, k)
            self.assertIn(k, server.RAW_DIR, k)

    def test_dimitems_cover_show(self):
        covered = set()
        for items in server.DIM_ITEMS.values():
            covered |= set(items)
        self.assertEqual(covered, set(server.SHOW))

    def test_benchmarks_shape(self):
        self.assertEqual(len(q.BENCHMARKS), 25)
        for code, book in q.BENCHMARKS.items():
            self.assertEqual(book.get("_n"), 100, code)
            for k in server.SHOW:
                self.assertIn(k, book, f"{code}.{k}")
                self.assertIsInstance(book[k], (int, float), f"{code}.{k}")

    def test_bench_label_has_no_orphans(self):
        extra = (set(q.BENCH_LABEL) - set(server.SHOW)
                 - {"real", "human", "imm", "rhy", "syn"})
        self.assertFalse(extra, f"BENCH_LABEL 里有不在 SHOW 的键：{extra}")


class ServerSmoke(unittest.TestCase):
    """server.analyze 全链路 + 合规硬规则。"""

    TEXT = f"# 第一章 入夜\n\n{B}\n\n# 第二章 敲门\n\n{B}"

    def test_analyze_two_chapters(self):
        r = server.analyze(self.TEXT, "自测")
        self.assertEqual(r["summary"]["chapters"], 2)
        for ch in r["chapters"]:
            self.assertEqual(set(ch["score"]),
                             {"real", "human", "imm", "rhy", "syn", "total"})
            for v in ch["score"].values():
                self.assertTrue(0.0 <= v <= 10.0)
            self.assertEqual(set(ch["metrics"]), set(server.SHOW))
            self.assertEqual(set(ch["items"]), set(server.SHOW))
        for k in ("real", "human", "imm", "rhy", "syn", "total"):
            self.assertIn(k, r["bench"])
        for k in server.SHOW:
            self.assertIn(k, r["label"], k)
            self.assertIn(k, r["desc"], k)
            self.assertIn(k, r["rawdir"], k)

    def test_analyze_short_text_falls_back_to_whole(self):
        r = server.analyze("太短了。", "短")
        self.assertEqual(r["summary"]["chapters"], 1)
        self.assertEqual(r["chapters"][0]["title"], "（整篇）")

    def test_compliance_hard_rules(self):
        hits = dict(q.compliance(PARA * 4 + "（编辑注：此处略）**重点**"))
        self.assertIn("圆括号·注记污染", hits)
        self.assertIn("正文加粗", hits)
        self.assertIn("破折号超限", dict(q.compliance("——就这样。" * 5)))

    def test_compliance_strict_grade_b(self):
        prev = q.compliance.strict
        try:
            q.compliance.strict = True
            hits = dict(q.compliance("他说：这是 E12 号实验。" + PARA))
            self.assertIn("[B]拉丁字母", hits)
            self.assertIn("[B]阿拉伯数字", hits)
        finally:
            q.compliance.strict = prev

    def test_tail_lyric_caught(self):
        body = PARA + "\n\n他知道，这一切才刚刚开始。\n\n" + PARA
        self.assertIn("章末抒情偷跑", dict(q.compliance(body)))

    def test_clean_json_safe(self):
        self.assertEqual(server._clean(float("nan")), 0.0)
        self.assertEqual(server._clean(float("inf")), 999.0)
        self.assertEqual(server._clean(float("-inf")), -999.0)
        self.assertEqual(server._clean(1.23456), 1.2346)


if __name__ == "__main__":
    unittest.main()
