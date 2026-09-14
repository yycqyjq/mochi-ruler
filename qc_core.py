#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_core.py — 网文「真人感 / 人味 / 代入感 / 节奏 / 句法」体检核心库

打分规范（全库统一，只此一套）：
    所有分数一律 0–10 分，**越高越好**，越高越不像 AI 网文。
    分三层，逐层汇总：
      1. 逐项分  每个指标一个 0–10：good(v, 达标值, 超标值)
         达标值 → 10 分，超标值 → 0 分，中间线性。达标值可大于也可以小于
         超标值，公式自带方向，所以**不再需要任何「越低越好/越高越好」方向表**。
      2. 五维分  该维各指标逐项分的加权平均（权重只表达相对重要性，由 _wavg()
                 按权重和归一化，结果必然 0–10）
         真人感  越高越好（= 10 − 旧「AI 味」：反转句 / 模糊语 / 破折号 / 加粗 …）
         人味    越高越好（口语 / 情绪外显 / 叠词）——**低 AI 味 ≠ 有人味**，
                 干巴巴的文本可能既没 AI 痕迹也没人味，两者互补
         代入感  越高越好（感知 / 认知 / 身体 / 受限）
         节奏    越高越好（长句 p90 / 短句 p10 / 段长 CV / 书面虚词）
         句法    越高越好（第三人称代词密度 / 代词起句率 / 句长中位 /
                 转折连词）——2026-09-13 新增。真人长篇与 AI 文本实测，
                 这四项是本工具里区分度最高的一组（代词密度、代词起句、
                 转折连词三项 AUC ≥ 0.98，两边几乎不重叠）；而人工罗列的
                 「AI 俗套词表」（心中一凛 / 嘴角勾起 / 不禁 …）实测两端
                 命中都≈0，**没有区分力**，故不参与打分。
      3. 总分    五维等权平均（各占 1/5），同样 0–10、越高越好

    一句话记住这次改造：把「AI 味越低越好」翻成「真人感越高越好」，
    两者数值互补（真人感 = 10 − AI 味）。原始指标与标杆基准都没动；
    2026-09-13 起 `act`（动作密度，方向实测为反）与 `ttr`（词汇多样性，
    区分度弱）**退出打分**，只在原始指标里保留数值备查。

本文件是库，不是命令行工具：不直接运行，由 server.py 导入。
（旧版 docstring 里列过一整套 --diff / --check / --fix / --trend 之类的命令，
那些入口从未随本文件交付，全部不存在，别照着敲。）

用法：
    import qc_core as q

    chs  = q.split_chapters(text)            # 拆章
    m    = q.metrics(body)                   # 单章指标
    q.item_score(k, m[k])   # 单个指标的逐项分，0–10，越高越好
    q.score_real(m)[1]      # 真人感，0–10，越高越好
    q.score_human(m)[1]     # 人味，0–10，越高越好
    q.score_imm(m)[1]       # 代入感，0–10，越高越好
    q.score_rhy(m)[1]       # 节奏，0–10，越高越好
    q.score_syn(m)[1]       # 句法，0–10，越高越好
    q.score_total({...})    # 总分，0–10，越高越好
    q.compliance(body, title)   # 合规硬规则，返回违规项列表
    q.check(files)              # 达标验收，按 CHECK 门槛打印 PASS/FAIL

另有一项独立机制（不在五维里）：
    合规    硬规则（圆括号注记 / 违禁元词 / 破折号超限 / 加粗 / 章内重复 /
            群像 / 章末抒情），命中即列为违规项

门槛（CHECK）：
    达标线取自标杆中位数，供 check() 做 PASS/FAIL 门禁与「最该先改」排序。

标杆基准（BENCHMARKS）：
    对中文长篇逐章统计得到：每本按全书均匀抽样（单章 ≥1200 字），
    先算各本中位，再取跨本中位。键名为匿名代号，具体书目不入库。

    2026-09-14 重建（旧的是 7 本、只取前 40 章，且其中一本是在错误拆章上
    算出来的）：现为 **24 本 × 全书等距 100 章**，剔除了两本不可用的
    （一本整本未拆出章节，一本章均近万字疑似合章）。
    更关键的是口径：**只存原始指标中位，不再存五维分**。
    旧的每个条目里存着 ai / human / imm / net / rhythm / syn 六个**字面量**，
    是用当时那套公式算的死数——公式一改（如 net 撤编、g_turn 入库）
    它们就与新口径脱节，还会让新指标因为「基准里没这个值」而永远显示 —。
    现在五维分在运行时用当前公式从原始指标算，口径永远自洽。
"""

import re
import statistics
import collections


# ---------------------------------------------------------------- 正则

REV = re.compile(r"不是[^。！？\n]{1,30}[，、][^。！？\n]{0,10}是")
BOLD = re.compile(r"\*\*[^*\n]+\*\*")
SIMILE = re.compile(
    r"像是|就像|活像|仿佛|如同|似的|一般地|"
    r"(?<![好不想图画偶影录相])像[^\s，。！？、]{1,8}"
)
DASH_END = re.compile(r"——[^，。！？\n]{1,14}[。！]")
HEADWORD = re.compile(r"(?:^|[。！？…\n])([\u4e00-\u9fa5]{1,2})")

# 第三人称代词。「其他」不是代词，用后顾断言排除；「她 / 它」无此搭配。
PRON3 = re.compile(r"(?<!其)他|她|它")

# 转折连词（2026-09-13 新增，句法维）。详见 SYN_GOOD_BAD 上方的标定注释：
# 这是全库单项区分度最高的指标（AUC 0.989），且与 pron3 / pron_start /
# sent_med 的相关都 ≤0.17，是独立信号，不是「短句化」的回声。
TURN = re.compile(r"但是|可是|不过|然而|却|反倒|反而")

QUOTE = re.compile("[\u201c\u201d\u300c\u300d\u2018\u2019\"']")

PERC = re.compile(
    r"看见|看到|瞧见|望见|瞥见|盯着|听见|听到|听出|闻到|尝到|摸到|"
    r"感觉到|感到|觉得|看清|听清"
)
COG = re.compile(
    r"发现|意识到|反应过来|才明白|才想明白|愣了|愣住|愣了一|回过神|"
    r"察觉|注意到|才反应|忽然|猛地|一下子|这才"
)
SOMA = re.compile(
    r"疼|痛|麻|痒|酸|冷(?!静|淡|清)|热(?!闹|情|爱|衷)|沉(?!默|淀|思|睡)|"
    r"软|硬|喘|抖|颤|汗|心跳|恶心|发花|无力|僵|涨|闷|饿|渴|困(?!难|境|住)"
)
LIM = re.compile(
    r"只能|看不清|看不出|听不清|听不出|够不着|够不到|辨不出|分不清|"
    r"分不出|认不出|说不清|想不起|不知道是|看不全"
)
ORAL = re.compile(r"吧|啊|呢|嘛|啥|咋|甭|呗|哟|嘿|哼|哎|唉|啧|瞧瞧|可不是")
LIT = re.compile(r"其|之|乃|遂|亦|矣|乎|者|所|则|而|哉|焉|尔|夫")
ACT = re.compile(
    r"起身|扭头|转身|回头|抬手|低头|抬头|伸手|抓住|拽|拎|拍|踢|推|拉|抬|转|"
    r"站起|坐下|躺|蜷|缩|抖|颤|抚摸|攥|捏|挥|迈|奔|跑|停住|顿住|"
    r"摇头|点头|皱眉|咬|喘|屏息"
)
EMO = re.compile(r"笑|哭|怒|怕|喜|悲|惊|慌|恨|急|叹|骂|乐|愁|恼|羞|惧|忧")

LATIN = re.compile(r"[A-Za-z]")
ARABIC = re.compile(r"[0-9]")
ROMAN = re.compile(r"[\u2160-\u2169]")
PAREN = re.compile(r"[（(][^）)]{0,40}[）)]")
BAN_WORDS = ["章组", "细纲", "大纲", "卷I", "卷Ⅱ", "卷X"]
BAN_CODE = re.compile(r"[ELF]\s?\d+")
LYRIC = re.compile(r"他感到|她感到|这一刻|他知道|她知道|他明白|她明白|"
                   r"他觉得|她觉得|他意识到|她意识到")
NOD = re.compile(r"点头|颔首|沉默|没有说话|不语|没吭声")
CLICHE = re.compile(r"不禁|忍不住|下意识|缓缓地|微微地|淡淡地|"
                    r"眼中闪过一丝|嘴角勾起|瞳孔一缩|心中一凛")
DEDE = re.compile(r"的[^，。！？]{0,6}的[^，。！？]{0,6}的")
ISDE = re.compile(r"是[^，。！？]{1,12}的[。！？]")
ONOMAT = re.compile(r"啪嗒|哗啦|咕噜|咔嚓|咚|嗒|唰|嗡|吱|哐|砰|嗖")
SPACE = re.compile(r"左边|右边|上边|下边|前头|后头|上头|底下|里头|外头|跟前")
BREATH = re.compile(r"喘|呼吸|心跳|屏住|憋|胸口|发闷")
EXCLAIM = re.compile(r"！")
REDUPL = re.compile(r"(.)\1(?![一-龥])")
TELL = re.compile(r"他知道|她知道|他明白|她明白|他意识到|她意识到|"
                  r"他感到|她感到|他清楚|她清楚|他忽然明白")
NEGO = re.compile(r"不是[^。！？\n]{1,22}——[^。！？\n]{1,22}")
ENUM = re.compile(
    r"有的[^，。！？]{1,12}[，、][^，。！？]{0,8}有的|"
    r"[^，。！？\n]{2,8}、[^，。！？\n]{2,8}、[^，。！？\n]{2,8}"
)
HOOK = re.compile(
    r"突然|忽然|竟然|居然|没想到|不对|奇怪|异常|异样|第一次|从没|从来没|"
    r"谁也没|没人|不知从哪|凭空|毫无预兆|"
    r"不知|没说|没答|没有回答|沉默|没吭声|不语|"
    r"原来|竟是|却是|谁知|"
    r"死了|没了|毁了|塌了|碎了|消失|"
    r"必须|只剩|来不及|明日|明天|三日内|期限|再不|"
    r"\uff1f"
)
CONFLICT = re.compile(
    r"打|杀|争|吵|威胁|危险|怒|骂|攻击|逃|追|怕|死|伤|血|"
    r"刀|剑|枪|爆|崩|碎|吼|扑|撞|撕|抢|敌|斗|战|危机|险"
)
THINK = re.compile(r"([\u4e00-\u9fa5]{2,4})(?:心想|暗想|心里想|心中暗想|暗自|心道)")
VAGUE = re.compile(
    r"在心里|过了很久|很久|半晌|好一会儿|看了一会儿|看了很久|看了半天|"
    r"听了一会儿|一样东西|一件事|一句话|的时候|这个字|这两个字|三个字|"
    r"这两个|一会儿|片刻|没多久"
)

# ---------------------------------------------------------------- 阈值

GOOD_BAD = {
    "rev":    (0.30, 0.80),
    "tail":   (0.18, 0.34),
    "bold":   (0.0,  1.0),
    "simile": (1.00, 2.50),
    "short":  (0.30, 0.45),
    "dash":   (0.50, 6.00),
    "head":   (0.05, 0.12),
    "vague":    (0.80, 3.00),
    "para_med": (26.0, 14.0),
    "short_run": (3.0, 6.0),
    "tell":     (0.15, 0.50),
    "nego":     (0.10, 1.00),
    "enum":     (0.05, 0.40),
    "sent_den": (35.0, 70.0),
    "dede":     (0.15, 0.60),
    "isde":     (0.50, 1.50),
    "onomat":   (0.30, 1.00),
    "space":    (0.20, 1.20),
}
CV_RANGE = (0.60, 0.42)
# 权重只需表达「相对重要性」，不必凑成 1.0 —— 各 score_* 用 _wavg() 做归一化。
WEIGHTS = {
    "rev": 0.10, "tail": 0.05, "bold": 0.04, "cv": 0.05,
    "simile": 0.06, "short": 0.02, "dash": 0.08, "head": 0.02,
    "vague": 0.10, "para_med": 0.04, "short_run": 0.02,
    "tell": 0.02, "nego": 0.10, "enum": 0.04, "sent_den": 0.10,
    "dede": 0.03, "isde": 0.03, "onomat": 0.02, "space": 0.02,
}

IMM_RANGE = {
    "imm_perc": (0.80, 2.00),
    "imm_soma": (1.00, 2.50),
}

IMM_GOOD_BAD = {
    "breath":     (0.20, 0.90),
    "imm_perc":   (3.0, 1.0),
    "imm_cog":    (2.0, 0.6),
    "imm_soma":   (2.5, 0.8),
    "imm_lim":    (0.5, 0.1),
}
IMM_WEIGHTS = {"imm_perc": 0.10, "imm_cog": 0.40, "imm_soma": 0.10,
               "imm_lim": 0.15, "breath": 0.10}

HUMAN_GOOD_BAD = {
    "net_oral": (1.20, 0.40),
    "net_dial": (0.30, 0.15),
    "emo":      (2.00, 0.80),
    "exclaim":  (2.00, 0.20),
    "redupl":   (6.00, 2.00),
}
# `ttr`（词汇多样性）2026-09-13 起退出打分：实测真人长篇与 AI
# 文本完全重叠，且有一篇 AI 的 ttr 是全体最高，不能当判据。权重按比例
# 分给其余各项。
# 「网文味」2026-09-13 起不再单列维度：它测的是文体特征而非缺陷，方向
# 不成立。net_oral 本就在人味维，net_dial（对话占比）并入人味，
# score_net 及其阈值表随之删除。
HUMAN_WEIGHTS = {"net_oral": 0.22, "net_dial": 0.10, "emo": 0.39,
                 "exclaim": 0.22, "redupl": 0.17}

RHY_GOOD_BAD = {
    "comma_in": (55.0, 15.0),
    "sent_p90": (65.0, 30.0),
    "sent_p10": (8.0, 3.0),
    "para_cv":  (0.42, 0.25),
    "lit":      (9.0,  3.0),
}
RHY_WEIGHTS = {"sent_p90": 0.45, "sent_p10": 0.15,
               "para_cv": 0.10, "lit": 0.10, "comma_in": 0.20}

# 句法维（2026-09-13 新增）。三项都从「真人长篇 vs AI 文本」的
# 逐章实测里标定（每来源随机 ≤60 章，取中位）：
#     pron3       真人 2.16–16.19（中位 9.85）  AI 17.84–30.86（中位 28.71）
#                 —— 两边完全不重叠，AUC = 1.00
#     pron_start  真人 0.000–0.070（中位 0.024）AI 0.082–0.153（中位 0.145）
#                 —— 两边完全不重叠，AUC = 1.00
#     sent_med    真人 16–71 字（中位 30）      AI 8–18.5 字（中位 15）
#                 —— AI 系统性短句化，AUC 0.96（16–18.5 区间有重叠）
# 说明：句长中位 / 短句占比 / 句号密度 是同一个「短句化」现象的不同测面，
# 这里只取句长中位一项，避免同一个毛病被重复扣分。
#
# g_turn（转折连词/千字，2026-09-13 新增）：
#     真人 P01–P99 = 0.31–7.68（中位 2.62）  AI P01–P99 = 0.00–1.22（中位 0.10）
#     —— AUC 0.989。用「每千字」而不是「每百句」口径，见下面的口径警告。
#
# ⚠️ 口径警告（2026-09-13 实测，新指标必看）：
#   「每百句」比值型会被句长系统性绑架：句子越长，每句撞上目标词的概率越高，
#   X/百句 ≈ 常数 × 句长。实测 g_turn 的每百句版与 sent_med 相关 0.96，
#   换成每千字后相关降到 −0.01。判据：**在真人样本上做 X ~ sent_med 回归，
#   看 AI 残差的 AUC**。g_turn 每千字残差 AUC = 0.990（独立信号）；
#   同期候选 oral_modal（语气词）每百句残差 AUC = 0.183——方向反转，
#   说明它只是句长的回声，故未入库。**新增指标必须过这一关。**
SYN_GOOD_BAD = {
    "pron3":      (12.00, 17.50),
    "pron_start": (0.045, 0.080),
    "sent_med":   (26.0,  15.0),
    "g_turn":     (2.50,  0.20),
}
# 权重只表达相对重要性，_wavg() 会按权重和归一化，不必凑成 1.0。
# g_turn 与 pron3 / pron_start 同为「完全不重叠」级信号，给同级权重。
SYN_WEIGHTS = {"pron3": 0.45, "pron_start": 0.30, "sent_med": 0.25,
               "g_turn": 0.30}

CHECK = [
    # (指标, 方向, 达标线, 中文名, 说明)　方向 min = 越高越好，max = 越低越好
    ("rev", "max", 0.30, "反转句/千字", "不是A，是B"),
    ("simile", "max", 1.00, "明喻/千字", "像…一样"),
    ("bold", "max", 0.0, "正文加粗", "小说正文不该有"),
    ("dash", "max", 0.50, "破折号收束/千字", "——短句。"),
    ("vague", "max", 0.80, "AI模糊语/千字", "在心里/过了很久/的时候"),
    ("nego", "max", 0.10, "否定-破折号/千字", "不是A——是B"),
    ("enum", "max", 0.20, "罗列排比/千字", "顿号三连"),
    ("sent_den", "max", 35.0, "句/千字", "句子切太碎"),
    ("para_med", "min", 26.0, "段长中位", "段落太碎"),
    ("sent_p90", "min", 60.0, "长句p90", "写不出长句"),
    ("real", "min", 8.50, "真人感(分)", "0–10，越高越不像AI"),
    ("human", "min", 6.00, "人味(分)", "口语/情绪/叠词"),
    ("imm", "min", 5.00, "代入感(分)", "感知/身体/受限"),
    ("rhythm", "min", 7.00, "节奏(分)", "长短句张力"),
    ("syn", "min", 7.00, "句法(分)", "代词密度/起句/句长"),
    ("total", "min", 7.50, "总分(分)", "五维等权"),
]


def check(files):
    """达标验收：达标线取自预置基准的中位数。输出逐章通过率与全书判定。"""
    rows = []
    for f in files:
        t = open(f, encoding="utf-8").read()
        for title, body in split_chapters(t):
            if len(re.sub(r"\s", "", body)) < 1200:
                continue
            rows.append((title, body))
    if not rows:
        print("未找到足够章节（需 >=1200 字）")
        return

    vals = []
    for title, body in rows:
        m = metrics(body)
        m["real"] = score_real(m)[1]
        m["human"] = score_human(m)[1]
        m["imm"] = score_imm(m)[1]
        m["rhythm"] = score_rhy(m)[1]
        m["total"] = score_total({k: m[k] for k in DIM_WEIGHTS})
        vals.append((title, m))

    def med(k):
        v = sorted(x[1][k] for x in vals)
        return v[len(v) // 2]

    print()
    print("=" * 72)
    print("达标验收（达标线取自预置基准中位数）")
    print("=" * 72)
    print(f"{'指标':<18}{'达标线':>10}{'你的值':>10}{'逐章通过':>10}   判定")
    print("-" * 72)
    passed = 0
    gaps = []
    for k, direction, line, label, note in CHECK:
        v = med(k)
        ok_ch = sum(1 for _, m in vals
                    if (m[k] <= line if direction == "max" else m[k] >= line))
        ok = (v <= line) if direction == "max" else (v >= line)
        sym = ("≤" if direction == "max" else "≥")
        verdict = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            gap = (v - line) if direction == "max" else (line - v)
            gaps.append((gap / max(abs(line), 1e-6), label, v, line, sym))
        print(f"{label:<18}{sym + format(line, '.2f'):>10}{v:>10.2f}"
              f"{str(ok_ch) + '/' + str(len(vals)):>10}   {verdict}")
    print("-" * 72)
    print(f"通过 {passed}/{len(CHECK)} 项")
    if gaps:
        gaps.sort(reverse=True)
        print("\n最该先改的 3 项（按差距排序）：")
        for r, label, v, line, sym in gaps[:3]:
            print(f"   {label:<18} 现 {v:.2f} → 目标 {sym}{line:.2f}"
                  f"（还差 {r*100:.0f}%）")
    else:
        print("全部达标。")
    print()


BENCHMARKS = {
    # 键名为匿名代号，具体书目不入库。字段只有原始指标中位 + 抽样章数 _n，
    # 五维分不存（运行时算），新增指标自动获得基准。
    "B01": {'_n': 100, 'vague': 0.3693, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3287, 'enum': 0.0, 'simile': 0.7452, 'sent_den': 23.7371, 'para_med': 58.0, 'short_run': 1.0, 'tail': 0.0235, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0, 'onomat': 0.0, 'space': 0.0, 'short': 0.063, 'head': 0.0161, 'tell': 0.0, 'cv': 0.6888, 'sent_p90': 79.5, 'sent_p10': 6.0, 'comma_in': 88.8797, 'lit': 15.1581, 'para_cv': 0.5025, 'emo': 4.7988, 'net_oral': 1.098, 'net_dial': 0.315, 'exclaim': 6.8249, 'redupl': 8.9121, 'imm_cog': 1.1527, 'imm_perc': 2.3422, 'imm_soma': 2.3063, 'imm_lim': 0.354, 'breath': 0.3752, 'pron3': 9.9561, 'pron_start': 0.0216, 'sent_med': 39.5, 'g_turn': 1.7716},
    "B02": {'_n': 100, 'vague': 0.2159, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.0, 'simile': 0.3472, 'sent_den': 22.7724, 'para_med': 49.75, 'short_run': 1.0, 'tail': 0.0312, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0, 'onomat': 0.0, 'space': 0.0, 'short': 0.037, 'head': 0.0152, 'tell': 0.0, 'cv': 0.5506, 'sent_p90': 73.5, 'sent_p10': 14.0, 'comma_in': 90.7486, 'lit': 22.7843, 'para_cv': 0.4762, 'emo': 3.2948, 'net_oral': 0.6571, 'net_dial': 0.2251, 'exclaim': 3.5966, 'redupl': 4.0332, 'imm_cog': 1.2579, 'imm_perc': 1.2448, 'imm_soma': 2.7877, 'imm_lim': 0.3051, 'breath': 0.0, 'pron3': 10.5555, 'pron_start': 0.041, 'sent_med': 41.0, 'g_turn': 2.5539},
    "B03": {'_n': 100, 'vague': 0.8694, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.3285, 'simile': 0.4946, 'sent_den': 45.9316, 'para_med': 27.75, 'short_run': 3.0, 'tail': 0.0674, 'bold': 0.0, 'dede': 0.0, 'isde': 0.4516, 'onomat': 0.0, 'space': 0.0, 'short': 0.1567, 'head': 0.0158, 'tell': 0.0, 'cv': 0.6386, 'sent_p90': 39.0, 'sent_p10': 6.0, 'comma_in': 47.8602, 'lit': 8.9436, 'para_cv': 0.6639, 'emo': 2.4065, 'net_oral': 3.2658, 'net_dial': 0.4603, 'exclaim': 2.8531, 'redupl': 13.2252, 'imm_cog': 0.3834, 'imm_perc': 0.9405, 'imm_soma': 1.6295, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 10.9577, 'pron_start': 0.0317, 'sent_med': 18.0, 'g_turn': 1.6464},
    "B04": {'_n': 100, 'vague': 0.6527, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3244, 'enum': 0.0, 'simile': 0.6342, 'sent_den': 38.2628, 'para_med': 44.5, 'short_run': 2.0, 'tail': 0.0374, 'bold': 0.0, 'dede': 0.0, 'isde': 0.948, 'onomat': 0.0, 'space': 0.0, 'short': 0.1293, 'head': 0.025, 'tell': 0.0, 'cv': 0.7163, 'sent_p90': 49.0, 'sent_p10': 5.0, 'comma_in': 49.5629, 'lit': 8.8642, 'para_cv': 0.7578, 'emo': 5.3834, 'net_oral': 4.4325, 'net_dial': 0.4434, 'exclaim': 4.2335, 'redupl': 13.201, 'imm_cog': 0.9494, 'imm_perc': 1.8586, 'imm_soma': 1.2563, 'imm_lim': 0.3127, 'breath': 0.0, 'pron3': 8.4827, 'pron_start': 0.0216, 'sent_med': 22.0, 'g_turn': 4.8387},
    "B05": {'_n': 100, 'vague': 0.7348, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.0, 'simile': 0.6191, 'sent_den': 35.4471, 'para_med': 41.0, 'short_run': 1.0, 'tail': 0.0345, 'bold': 0.0, 'dede': 0.0, 'isde': 0.3655, 'onomat': 0.0, 'space': 0.0, 'short': 0.0512, 'head': 0.0196, 'tell': 0.0, 'cv': 0.579, 'sent_p90': 49.0, 'sent_p10': 9.0, 'comma_in': 53.9096, 'lit': 18.3587, 'para_cv': 0.5943, 'emo': 5.0866, 'net_oral': 1.6523, 'net_dial': 0.2753, 'exclaim': 2.633, 'redupl': 6.332, 'imm_cog': 0.959, 'imm_perc': 1.2854, 'imm_soma': 2.7353, 'imm_lim': 0.3253, 'breath': 0.0, 'pron3': 5.427, 'pron_start': 0.0217, 'sent_med': 24.0, 'g_turn': 3.4287},
    "B06": {'_n': 100, 'vague': 0.3202, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.324, 'simile': 0.9266, 'sent_den': 43.1542, 'para_med': 23.0, 'short_run': 3.0, 'tail': 0.0611, 'bold': 0.0, 'dede': 0.0, 'isde': 0.6367, 'onomat': 0.1401, 'space': 0.0, 'short': 0.3031, 'head': 0.0153, 'tell': 0.0, 'cv': 0.8617, 'sent_p90': 47.0, 'sent_p10': 4.0, 'comma_in': 52.1946, 'lit': 14.7795, 'para_cv': 0.9057, 'emo': 4.2324, 'net_oral': 1.5639, 'net_dial': 0.5, 'exclaim': 7.173, 'redupl': 17.0432, 'imm_cog': 0.8973, 'imm_perc': 0.9707, 'imm_soma': 1.5718, 'imm_lim': 0.3096, 'breath': 0.0, 'pron3': 4.9099, 'pron_start': 0.0123, 'sent_med': 16.25, 'g_turn': 2.9897},
    "B07": {'_n': 100, 'vague': 1.1257, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3156, 'enum': 0.0, 'simile': 1.0912, 'sent_den': 33.4877, 'para_med': 36.5, 'short_run': 2.0, 'tail': 0.0437, 'bold': 0.0, 'dede': 0.0, 'isde': 2.1267, 'onomat': 0.0, 'space': 0.0, 'short': 0.1034, 'head': 0.0142, 'tell': 0.0, 'cv': 0.6877, 'sent_p90': 54.5, 'sent_p10': 7.0, 'comma_in': 64.4551, 'lit': 8.0349, 'para_cv': 0.6365, 'emo': 2.7983, 'net_oral': 2.6107, 'net_dial': 0.4104, 'exclaim': 0.3544, 'redupl': 8.9494, 'imm_cog': 0.4395, 'imm_perc': 0.8318, 'imm_soma': 1.0291, 'imm_lim': 0.3273, 'breath': 0.0, 'pron3': 4.7915, 'pron_start': 0.019, 'sent_med': 24.25, 'g_turn': 1.2331},
    "B08": {'_n': 100, 'vague': 0.2214, 'nego': 0.0, 'dash': 0.0, 'rev': 0.2783, 'enum': 0.2844, 'simile': 1.2587, 'sent_den': 32.459, 'para_med': 38.0, 'short_run': 2.0, 'tail': 0.0455, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0692, 'onomat': 0.37, 'space': 0.0, 'short': 0.1126, 'head': 0.0096, 'tell': 0.0, 'cv': 0.5859, 'sent_p90': 50.0, 'sent_p10': 6.0, 'comma_in': 84.3975, 'lit': 11.175, 'para_cv': 0.5007, 'emo': 5.1224, 'net_oral': 1.8511, 'net_dial': 0.2511, 'exclaim': 8.2394, 'redupl': 7.5925, 'imm_cog': 0.6127, 'imm_perc': 1.8636, 'imm_soma': 2.683, 'imm_lim': 0.0, 'breath': 0.2143, 'pron3': 15.4425, 'pron_start': 0.0521, 'sent_med': 30.0, 'g_turn': 3.1844},
    "B09": {'_n': 100, 'vague': 1.476, 'nego': 0.0, 'dash': 0.0, 'rev': 0.4794, 'enum': 0.0, 'simile': 0.9749, 'sent_den': 27.1197, 'para_med': 40.25, 'short_run': 1.0, 'tail': 0.0233, 'bold': 0.0, 'dede': 0.0, 'isde': 0.4879, 'onomat': 0.0, 'space': 0.0, 'short': 0.0632, 'head': 0.0189, 'tell': 0.0, 'cv': 0.6053, 'sent_p90': 65.0, 'sent_p10': 9.0, 'comma_in': 46.6757, 'lit': 12.3929, 'para_cv': 0.5496, 'emo': 4.2971, 'net_oral': 6.4229, 'net_dial': 0.3143, 'exclaim': 5.6765, 'redupl': 8.1633, 'imm_cog': 2.9311, 'imm_perc': 2.1239, 'imm_soma': 1.4451, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 9.9587, 'pron_start': 0.02, 'sent_med': 33.25, 'g_turn': 3.4014},
    "B10": {'_n': 100, 'vague': 0.2603, 'nego': 0.0, 'dash': 0.0, 'rev': 0.2759, 'enum': 0.2768, 'simile': 1.2239, 'sent_den': 34.4775, 'para_med': 40.25, 'short_run': 1.0, 'tail': 0.0258, 'bold': 0.0, 'dede': 0.0, 'isde': 0.1493, 'onomat': 0.2655, 'space': 0.0, 'short': 0.0985, 'head': 0.0093, 'tell': 0.0, 'cv': 0.5975, 'sent_p90': 49.0, 'sent_p10': 5.0, 'comma_in': 85.4711, 'lit': 11.8242, 'para_cv': 0.4537, 'emo': 5.7233, 'net_oral': 1.8648, 'net_dial': 0.3611, 'exclaim': 5.7572, 'redupl': 10.2168, 'imm_cog': 0.617, 'imm_perc': 1.3038, 'imm_soma': 2.3977, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 12.0501, 'pron_start': 0.0387, 'sent_med': 29.0, 'g_turn': 2.8335},
    "B11": {'_n': 100, 'vague': 0.7391, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.0, 'simile': 0.9632, 'sent_den': 48.1361, 'para_med': 23.0, 'short_run': 2.0, 'tail': 0.1111, 'bold': 0.0, 'dede': 0.0, 'isde': 0.4916, 'onomat': 0.0, 'space': 0.0, 'short': 0.1596, 'head': 0.0111, 'tell': 0.0, 'cv': 0.4984, 'sent_p90': 33.0, 'sent_p10': 8.0, 'comma_in': 49.51, 'lit': 20.2481, 'para_cv': 0.5472, 'emo': 3.45, 'net_oral': 0.9851, 'net_dial': 0.2976, 'exclaim': 2.2247, 'redupl': 12.3957, 'imm_cog': 0.9908, 'imm_perc': 0.9881, 'imm_soma': 1.4437, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 5.3636, 'pron_start': 0.0113, 'sent_med': 19.0, 'g_turn': 4.4042},
    "B12": {'_n': 100, 'vague': 0.6478, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.0, 'simile': 0.0, 'sent_den': 18.2, 'para_med': 60.5, 'short_run': 1.0, 'tail': 0.0, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0, 'onomat': 0.0, 'space': 0.0, 'short': 0.0814, 'head': 0.0182, 'tell': 0.0, 'cv': 0.7811, 'sent_p90': 108.0, 'sent_p10': 8.0, 'comma_in': 75.1294, 'lit': 20.5648, 'para_cv': 0.5795, 'emo': 7.1262, 'net_oral': 2.4211, 'net_dial': 0.4545, 'exclaim': 1.996, 'redupl': 10.5603, 'imm_cog': 1.1045, 'imm_perc': 0.9538, 'imm_soma': 3.6072, 'imm_lim': 0.31, 'breath': 0.0, 'pron3': 5.6005, 'pron_start': 0.0, 'sent_med': 47.5, 'g_turn': 4.277},
    "B13": {'_n': 100, 'vague': 0.9371, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3487, 'enum': 0.0, 'simile': 1.1432, 'sent_den': 32.5794, 'para_med': 56.75, 'short_run': 1.0, 'tail': 0.0548, 'bold': 0.0, 'dede': 0.0, 'isde': 0.9482, 'onomat': 0.0, 'space': 0.0, 'short': 0.017, 'head': 0.0251, 'tell': 0.0, 'cv': 0.6321, 'sent_p90': 55.0, 'sent_p10': 9.0, 'comma_in': 54.8193, 'lit': 12.4826, 'para_cv': 0.5662, 'emo': 4.0351, 'net_oral': 1.7873, 'net_dial': 0.3781, 'exclaim': 0.0, 'redupl': 4.374, 'imm_cog': 0.7403, 'imm_perc': 1.3748, 'imm_soma': 2.079, 'imm_lim': 0.2298, 'breath': 0.0, 'pron3': 11.8091, 'pron_start': 0.0267, 'sent_med': 26.0, 'g_turn': 3.1785},
    "B14": {'_n': 100, 'vague': 0.7398, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3946, 'enum': 0.0, 'simile': 1.0077, 'sent_den': 12.4279, 'para_med': 84.75, 'short_run': 1.0, 'tail': 0.0, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0, 'onomat': 0.0, 'space': 0.0, 'short': 0.05, 'head': 0.0286, 'tell': 0.0, 'cv': 0.594, 'sent_p90': 134.5, 'sent_p10': 12.0, 'comma_in': 71.9262, 'lit': 9.8712, 'para_cv': 0.479, 'emo': 3.2762, 'net_oral': 0.8629, 'net_dial': 0.3431, 'exclaim': 0.0, 'redupl': 7.5468, 'imm_cog': 0.4532, 'imm_perc': 1.9701, 'imm_soma': 2.3092, 'imm_lim': 0.3419, 'breath': 0.0, 'pron3': 13.7275, 'pron_start': 0.0, 'sent_med': 79.5, 'g_turn': 2.843},
    "B15": {'_n': 100, 'vague': 0.4866, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.0, 'simile': 0.4854, 'sent_den': 20.058, 'para_med': 56.25, 'short_run': 1.0, 'tail': 0.0241, 'bold': 0.0, 'dede': 0.0, 'isde': 0.1232, 'onomat': 0.0, 'space': 0.0, 'short': 0.0833, 'head': 0.0238, 'tell': 0.0, 'cv': 0.652, 'sent_p90': 90.5, 'sent_p10': 11.0, 'comma_in': 55.0146, 'lit': 17.3012, 'para_cv': 0.5622, 'emo': 2.1117, 'net_oral': 0.9716, 'net_dial': 0.4264, 'exclaim': 0.5689, 'redupl': 6.3091, 'imm_cog': 0.4871, 'imm_perc': 1.3085, 'imm_soma': 0.9732, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 11.7439, 'pron_start': 0.0256, 'sent_med': 45.0, 'g_turn': 3.293},
    "B16": {'_n': 87, 'vague': 1.231, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.4125, 'simile': 0.4409, 'sent_den': 36.1991, 'para_med': 35.0, 'short_run': 2.0, 'tail': 0.0462, 'bold': 0.0, 'dede': 0.0, 'isde': 0.9112, 'onomat': 0.0, 'space': 0.0, 'short': 0.1538, 'head': 0.019, 'tell': 0.0, 'cv': 0.7644, 'sent_p90': 57.0, 'sent_p10': 6.0, 'comma_in': 53.6564, 'lit': 9.4378, 'para_cv': 0.6962, 'emo': 5.8877, 'net_oral': 2.5633, 'net_dial': 0.5319, 'exclaim': 1.5957, 'redupl': 13.2275, 'imm_cog': 1.3145, 'imm_perc': 1.9952, 'imm_soma': 1.81, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 2.3641, 'pron_start': 0.0, 'sent_med': 21.0, 'g_turn': 3.5247},
    "B17": {'_n': 100, 'vague': 0.569, 'nego': 0.0, 'dash': 0.0, 'rev': 0.3264, 'enum': 0.0, 'simile': 0.632, 'sent_den': 46.0043, 'para_med': 41.0, 'short_run': 1.0, 'tail': 0.0357, 'bold': 0.0, 'dede': 0.0, 'isde': 0.9238, 'onomat': 0.0, 'space': 0.0, 'short': 0.0828, 'head': 0.0241, 'tell': 0.0, 'cv': 0.7944, 'sent_p90': 45.0, 'sent_p10': 5.0, 'comma_in': 44.5036, 'lit': 8.8801, 'para_cv': 0.7494, 'emo': 3.6224, 'net_oral': 5.2261, 'net_dial': 0.6155, 'exclaim': 5.4524, 'redupl': 12.5125, 'imm_cog': 0.82, 'imm_perc': 1.9516, 'imm_soma': 1.2034, 'imm_lim': 0.316, 'breath': 0.0, 'pron3': 9.1304, 'pron_start': 0.0157, 'sent_med': 17.0, 'g_turn': 2.5525},
    "B18": {'_n': 100, 'vague': 0.481, 'nego': 0.0, 'dash': 0.0, 'rev': 0.222, 'enum': 0.0, 'simile': 0.5049, 'sent_den': 19.9846, 'para_med': 55.0, 'short_run': 1.0, 'tail': 0.0, 'bold': 0.0, 'dede': 0.0, 'isde': 0.2885, 'onomat': 0.0, 'space': 0.0, 'short': 0.0488, 'head': 0.0245, 'tell': 0.0, 'cv': 0.626, 'sent_p90': 85.0, 'sent_p10': 10.0, 'comma_in': 45.4347, 'lit': 14.6101, 'para_cv': 0.4291, 'emo': 2.1513, 'net_oral': 1.7472, 'net_dial': 0.3333, 'exclaim': 0.0, 'redupl': 5.4576, 'imm_cog': 0.9307, 'imm_perc': 0.9718, 'imm_soma': 0.5337, 'imm_lim': 0.0, 'breath': 0.0, 'pron3': 9.8663, 'pron_start': 0.0, 'sent_med': 48.0, 'g_turn': 3.9604},
    "B19": {'_n': 100, 'vague': 0.3713, 'nego': 0.0, 'dash': 0.0, 'rev': 0.0, 'enum': 0.3094, 'simile': 1.1359, 'sent_den': 28.1751, 'para_med': 32.0, 'short_run': 2.0, 'tail': 0.0234, 'bold': 0.0, 'dede': 0.0, 'isde': 0.2602, 'onomat': 0.0, 'space': 0.0, 'short': 0.1137, 'head': 0.0396, 'tell': 0.0, 'cv': 0.7135, 'sent_p90': 65.0, 'sent_p10': 8.5, 'comma_in': 56.5432, 'lit': 16.4941, 'para_cv': 0.6954, 'emo': 3.4757, 'net_oral': 0.9685, 'net_dial': 0.4998, 'exclaim': 2.3228, 'redupl': 11.5552, 'imm_cog': 1.2682, 'imm_perc': 1.506, 'imm_soma': 1.8605, 'imm_lim': 0.3123, 'breath': 0.0, 'pron3': 10.4344, 'pron_start': 0.071, 'sent_med': 29.75, 'g_turn': 0.9063},
    "B20": {'_n': 100, 'vague': 1.4739, 'nego': 0.0, 'dash': 0.0, 'rev': 0.1566, 'enum': 0.57, 'simile': 1.2902, 'sent_den': 37.9329, 'para_med': 24.0, 'short_run': 4.0, 'tail': 0.0289, 'bold': 0.0, 'dede': 0.0, 'isde': 0.5026, 'onomat': 0.0, 'space': 0.2341, 'short': 0.2469, 'head': 0.0127, 'tell': 0.0, 'cv': 0.8724, 'sent_p90': 55.0, 'sent_p10': 4.0, 'comma_in': 51.3971, 'lit': 4.7133, 'para_cv': 0.7429, 'emo': 3.8569, 'net_oral': 6.8494, 'net_dial': 0.4743, 'exclaim': 7.4219, 'redupl': 23.6098, 'imm_cog': 0.9828, 'imm_perc': 1.5302, 'imm_soma': 1.8218, 'imm_lim': 0.0635, 'breath': 0.0, 'pron3': 10.825, 'pron_start': 0.0171, 'sent_med': 18.5, 'g_turn': 1.8147},
    "B21": {'_n': 100, 'vague': 0.2387, 'nego': 0.0, 'dash': 0.0, 'rev': 0.2702, 'enum': 0.2894, 'simile': 1.0878, 'sent_den': 31.3811, 'para_med': 42.0, 'short_run': 1.0, 'tail': 0.0106, 'bold': 0.0, 'dede': 0.0, 'isde': 0.2068, 'onomat': 0.2806, 'space': 0.0, 'short': 0.0851, 'head': 0.0104, 'tell': 0.0, 'cv': 0.5685, 'sent_p90': 52.0, 'sent_p10': 6.0, 'comma_in': 75.6393, 'lit': 11.6744, 'para_cv': 0.4484, 'emo': 4.9552, 'net_oral': 1.3617, 'net_dial': 0.4292, 'exclaim': 3.5983, 'redupl': 11.3612, 'imm_cog': 0.5217, 'imm_perc': 0.8946, 'imm_soma': 2.6224, 'imm_lim': 0.2099, 'breath': 0.0, 'pron3': 9.8394, 'pron_start': 0.029, 'sent_med': 32.0, 'g_turn': 3.4035},
    "B22": {'_n': 100, 'vague': 0.2329, 'nego': 0.0, 'dash': 0.0, 'rev': 0.2697, 'enum': 0.0, 'simile': 0.4884, 'sent_den': 19.4973, 'para_med': 40.0, 'short_run': 2.0, 'tail': 0.0319, 'bold': 0.0, 'dede': 0.0, 'isde': 0.0431, 'onomat': 0.0, 'space': 0.3001, 'short': 0.1144, 'head': 0.0296, 'tell': 0.0, 'cv': 0.9028, 'sent_p90': 109.5, 'sent_p10': 11.5, 'comma_in': 66.1329, 'lit': 9.9003, 'para_cv': 1.1999, 'emo': 6.8046, 'net_oral': 1.4463, 'net_dial': 0.4683, 'exclaim': 1.2406, 'redupl': 1.1907, 'imm_cog': 0.4038, 'imm_perc': 1.0599, 'imm_soma': 2.2134, 'imm_lim': 0.1566, 'breath': 0.1757, 'pron3': 4.6745, 'pron_start': 0.012, 'sent_med': 35.0, 'g_turn': 2.3361},
    "B23": {'_n': 100, 'vague': 0.3455, 'nego': 0.0, 'dash': 0.0, 'rev': 0.2943, 'enum': 0.39, 'simile': 1.4318, 'sent_den': 31.0699, 'para_med': 25.5, 'short_run': 3.0, 'tail': 0.0957, 'bold': 0.0, 'dede': 0.0, 'isde': 0.4287, 'onomat': 0.0, 'space': 0.0, 'short': 0.2596, 'head': 0.0132, 'tell': 0.0, 'cv': 0.854, 'sent_p90': 65.5, 'sent_p10': 6.0, 'comma_in': 69.9069, 'lit': 11.8851, 'para_cv': 0.7568, 'emo': 4.2214, 'net_oral': 1.3366, 'net_dial': 0.3469, 'exclaim': 6.8722, 'redupl': 15.4417, 'imm_cog': 0.8945, 'imm_perc': 1.1943, 'imm_soma': 1.4251, 'imm_lim': 0.3128, 'breath': 0.0, 'pron3': 9.3577, 'pron_start': 0.0448, 'sent_med': 24.0, 'g_turn': 2.3674},
    "B24": {'_n': 100, 'vague': 0.9121, 'nego': 0.0, 'dash': 0.3118, 'rev': 0.2143, 'enum': 0.2487, 'simile': 0.765, 'sent_den': 19.2641, 'para_med': 54.0, 'short_run': 1.0, 'tail': 0.0237, 'bold': 0.0, 'dede': 0.0, 'isde': 0.591, 'onomat': 0.0, 'space': 0.0, 'short': 0.0691, 'head': 0.0183, 'tell': 0.0, 'cv': 0.827, 'sent_p90': 110.5, 'sent_p10': 8.0, 'comma_in': 45.5396, 'lit': 18.8476, 'para_cv': 0.6845, 'emo': 3.1883, 'net_oral': 1.3744, 'net_dial': 0.5804, 'exclaim': 1.1428, 'redupl': 7.3159, 'imm_cog': 0.7269, 'imm_perc': 1.6686, 'imm_soma': 1.4865, 'imm_lim': 0.2552, 'breath': 0.0, 'pron3': 9.3661, 'pron_start': 0.0336, 'sent_med': 38.0, 'g_turn': 2.0035},
}

# BENCH_KEYS / BENCH_NEG / BENCH_POS 是旧版「AI 味」时代的遗留：BENCH_KEYS 被
# check() 之外的任何地方都没用到，BENCH_NEG / BENCH_POS 是「越低越好 / 越高越好」
# 的方向分类——全库统一成「越高越好」之后这套分类已无意义，且随 2026-09-13
# 删除 env_* / imm_static 时已拆掉一半。2026-09-14 基准重建时一并移除。
# 基准里也不再存 ai / net 等存死维度值，见 server.py 的 bench 计算。
BENCH_LABEL = {
    "real": "真人感", "human": "人味", "imm": "代入感", "rhythm": "节奏",
    "syn": "句法",
    "rev": "反转句/千字", "simile": "明喻/千字", "head": "句首集中",
    "dash": "破折号收束", "bold": "正文加粗", "cv": "句长CV",
    "imm_perc": "感知/千字", "imm_cog": "认知反应", "imm_soma": "身体感受",
    "imm_lim": "受限标记",
    "net_dial": "对话占比", "net_oral": "口语/千字", "net_short": "短句占比",
    "sent_p90": "长句p90", "sent_p10": "短句p10", "para_cv": "段长CV",
    "lit": "书面虚词", "act": "动作密度", "emo": "情绪外显",
    "vague": "AI模糊语", "para_med": "段长中位", "short_run": "连续短段",
    "tell": "讲出来", "nego": "否定-破折号纠正", "enum": "罗列",
    "sent_den": "句/千字", "tail": "段尾金句", "short": "单行短段",
    "ttr": "词汇多样性",
    "pron3": "第三人称代词", "pron_start": "代词起句率", "sent_med": "句长中位",
    "g_turn": "转折连词",
}


# ---------------------------------------------------------------- 基础

def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def _wavg(s, w):
    """逐项分的加权平均，先按权重和归一化。

    权重表只表达相对重要性，不必凑成 1.0；删掉指标时也不用重新配平。
    输入是 0–10 的逐项分，输出必然落在 0–10。
    """
    tot = sum(w.values())
    return clamp(sum(s[k] * w[k] for k in w) / tot) if tot else 0.0


def good(v, target, over):
    """把单指标原始值折算成 0–10 分，越高越好。

    target = 达标值 → 10 分；over = 超标值 → 0 分；中间线性取值。
    target 可以大于也可以小于 over（两种方向都行），公式自带方向，
    因此不需要任何额外的「越低越好 / 越高越好」方向表。
    旧版「AI 味」用的正是它的补数 10 − good(v)，两者数值严格互补。
    """
    if over == target:
        return 0.0
    return clamp((over - v) / (over - target) * 10)


# 逐项评分规范：(达标值, 超标值)。由各维度阈值表合并而来。
ITEM_TARGET = {}
for _tbl in (GOOD_BAD, IMM_GOOD_BAD, HUMAN_GOOD_BAD,
             RHY_GOOD_BAD, SYN_GOOD_BAD):
    ITEM_TARGET.update(_tbl)
ITEM_TARGET["cv"] = CV_RANGE
# `act`（动作密度）与 `ttr`（词汇多样性）已退出打分，故此处不再给阈值；
# 两个原始值仍由 metrics() 照常算出，供对照。

# 达标是一个「区间」而不是单点的指标（落在区间内满分，越出区间扣分）。
RANGE_KEYS = set(IMM_RANGE)


def item_score(k, v):
    """单个指标的逐项分，0–10，越高越好。

    区间型指标（imm_perc / imm_soma）落在区间内给 10 分，越出区间按距离扣分。
    没有阈值规范、或取值为 None 时返回 None（前端显示为 —）。
    """
    if v is None:
        return None
    if k in RANGE_KEYS:
        lo, hi = IMM_RANGE[k]
        if lo <= v <= hi:
            return 10.0
        if v < lo:
            return clamp(10 - (lo - v) / max(lo * 0.6, 1e-6) * 10)
        return clamp(10 - (v - hi) / max(hi * 0.5, 1e-6) * 10)
    t = ITEM_TARGET.get(k)
    if t is None:
        return None
    return good(v, t[0], t[1])


def strip_meta(t):
    t = re.sub(r"^#.*$", "", t, flags=re.M)
    t = re.sub(r"^>.*$", "", t, flags=re.M)
    return t


def split_chapters(text):
    """按常见中文网文格式拆章，支持 Markdown / 中文章号 / 数字序号 / Chapter /
    纯数字前缀（如「01开篇」「02 别离」）。

    「纯数字前缀」这一类（数字紧跟标题、中间没有「第…章」也没有顿号）在导出
    的网文 txt 里很常见，但它没有任何显式分隔符，误伤风险高，所以加了四重
    护栏：① 该行前面必须是空行；② 数字 1–4 位；③ 数字后紧跟汉字；④ 整行
    ≤24 字，且数字后不能是「年/月/日…」这类时间单位。实测在长篇网文与
    AI 语料上，只有原本就拆不开的那一本被修正，其余文件拆章结果逐字不变。
    """
    pats = [
        r"\n(?=#\s+(?:第[一二三四五六七八九十百千\d]{1,6}[章节]|楔子|序章|番外))",
        r"\n(?=\s*(?:第[一二三四五六七八九十百千\d]{1,6}[章节])(?:\s|$))",
        r"\n(?=\s*(?:Chapter|CHAPTER)\s*\d+\b)",
        r"\n(?=\s*(?:楔子|序章|番外)(?:\s|$))",
        r"\n(?=\s*\d{1,4}[、.．]\s*\S)",
        r"\n[ \t\u3000\r]*\n(?=[ \t\u3000\r]*\d{1,4}[ \t\u3000\r]?"
        r"(?!年|月|日|时|分|秒|点|号|届|周年|℃|%)[\u4e00-\u9fa5][^\n]{0,22}\n)",
    ]
    parts = max((re.split(p, text) for p in pats), key=len)
    out = []
    for p in parts:
        title = p.split("\n")[0].strip()
        body = strip_meta(p)
        if len(re.sub(r"\s", "", body)) < 300:
            continue
        out.append((title, body))
    return out


def sentences(body):
    b = re.sub(r"[*>#]", "", body)
    return [re.sub(r"\s", "", s)
            for s in re.split(r"[。！？…]+", b) if len(re.sub(r"\s", "", s)) >= 2]


def paras(body):
    """正文段落。排除 Markdown 分隔线（---/***/===），否则章尾会被
    分隔线占据，导致钩子、段长、短段率等全部算错。"""
    out = []
    for l in body.split("\n"):
        s = l.strip()
        if not s or len(re.sub(r"\s", "", s)) < 2:
            continue
        if re.fullmatch(r"[-=*\u2014\u2013_]{2,}", s):
            continue
        out.append(s)
    return out


def is_dialogue(p):
    return bool(QUOTE.search(p))


# ---------------------------------------------------------------- 指标

def tail_gold_hits(body):
    hits = []
    for p in paras(body):
        if is_dialogue(p):
            continue
        seg = [x for x in re.split(r"[。！？…]", p) if x.strip()]
        if not seg:
            continue
        s = re.sub(r"\s", "", seg[-1])
        if 5 <= len(s) <= 20 and not re.search(r"[了吗呢吧啊哦哟]", s) \
                and re.search(r"是|在|有|得|成|叫", s):
            hits.append(s)
    return hits


def imm_stats(body):
    k = max(len(re.sub(r"\s", "", body)), 1) / 1000.0
    return {
        "imm_perc": len(PERC.findall(body)) / k,
        "imm_cog": len(COG.findall(body)) / k,
        "imm_soma": len(SOMA.findall(body)) / k,
        "imm_lim": len(LIM.findall(body)) / k,
    }


def net_stats(body):
    ps = paras(body)
    ss = sentences(body)
    dial = [p for p in ps if QUOTE.search(p)]
    short = [s for s in ss if len(s) <= 10]
    k = max(len(re.sub(r"\s", "", body)), 1) / 1000.0
    return {
        "net_dial": len(dial) / max(len(ps), 1),
        "net_oral": len(ORAL.findall(body)) / k,
        "net_short": len(short) / max(len(ss), 1),
    }


def _ttr(body, n=2):
    """词汇多样性：不同 n-gram 数 / 汉字总数 × 100（逐章算，汇总取中位）。

    **2026-09-13 起退出打分，只算原始值备查。**
    区分度弱，不可当 AI / 真人的判据：同一实现下实测，真人长篇与 AI 文本
    的逐章中位完全重叠（真人 11.6–82.8，AI 47.1–80.3），且其中一篇 AI 的
    ttr 是全体最高。
    （旧注释里「真人 36–54、AI 22–34」的数字与当前实现不可复现，已删。）
    """
    c = re.sub(r"[^\u4e00-\u9fa5]", "", body)
    if len(c) < n + 1:
        return 0.0
    grams = set(c[i:i + n] for i in range(len(c) - n + 1))
    return len(grams) / len(c) * 100


def _short_run(ps):
    run = best = 0
    for p in ps:
        if len(re.sub(r"\s", "", p)) <= 12:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def rhythm_stats(body, ss, ps):
    k = max(len(re.sub(r"\s", "", body)), 1) / 1000.0
    L = sorted(len(s) for s in ss) or [0]
    PL = [len(re.sub(r"\s", "", p)) for p in ps]
    pcv = (statistics.pstdev(PL) / statistics.mean(PL)) if len(PL) > 2 else 0.0
    return {
        "sent_p90": float(L[min(int(len(L) * 0.90), len(L) - 1)]),
        "sent_p10": float(L[int(len(L) * 0.10)]),
        "para_cv": pcv,
        "lit": len(LIT.findall(body)) / k,
        # act 2026-09-13 起退出打分，只算原始值备查：实测 AI 文本的动作密度
        # 反而高于真人长篇（方向为反），不能按「越高越好」给分。
        "act": len(ACT.findall(body)) / k,
        "emo": len(EMO.findall(body)) / k,
    }


def near_dup(body, n=28):
    ps = [re.sub(r"[^\u4e00-\u9fa5]", "", p) for p in paras(body)]
    ps = [p for p in ps if len(p) >= n]
    seen, dups = set(), []
    for p in ps:
        key = p[:n]
        if key in seen:
            dups.append(p[:34])
        else:
            seen.add(key)
    return dups


def crowd_flat(body):
    run = 0
    for p in paras(body):
        if len(re.sub(r"\s", "", p)) <= 8 and NOD.search(p):
            run += 1
            if run >= 3:
                return True
        else:
            run = 0
    return False


def tail_lyric(body):
    ps = paras(body)
    return LYRIC.findall("".join(ps[-3:])) if ps else []


def compliance(body, title=""):
    """硬规则检查，分三级：

    A 级（写作硬伤，默认报）：圆括号注记污染 / 违禁元词 / 破折号超限 /
        正文加粗 / 章内近重复 / 群像禁忌 / 章末抒情偷跑
    B 级（体例，仅 --strict）：阿拉伯数字 / 拉丁字母 / 罗马数字
    C 级（实测反向，仅 --strict 参考）：文学腔（缓缓/微微/不禁…）——老书反而更多
    """
    out = []
    if compliance.strict:
        la = sorted(set(LATIN.findall(body)))
        if la:
            out.append(("[B]拉丁字母", f"{len(LATIN.findall(body))} 处 " + "".join(la)[:20]))
        ar = sorted(set(ARABIC.findall(body)))
        if ar:
            out.append(("[B]阿拉伯数字", f"{len(ARABIC.findall(body))} 处 " + "".join(ar)))
        rm = sorted(set(ROMAN.findall(body)))
        if rm:
            out.append(("[B]罗马数字", f"{len(ROMAN.findall(body))} 处"))
    pr = PAREN.findall(body)
    if pr:
        out.append(("圆括号·注记污染", f"{len(pr)} 处 例:{pr[0][:18]}"))
    bw = [w for w in BAN_WORDS if w in body]
    if BAN_CODE.search(body):
        bw.append("编号(如E12/L3/F8)")
    if bw:
        out.append(("违禁元词", "、".join(bw)))
    d = body.count("\u2014\u2014")
    if d > 3:
        out.append(("破折号超限", f"{d} 处 (>3)"))
    bd = len(BOLD.findall(body))
    if bd:
        out.append(("正文加粗", f"{bd} 处"))
    nd = near_dup(body)
    if nd:
        out.append(("章内近重复", f"{len(nd)} 处 例:{nd[0][:22]}"))
    if crowd_flat(body):
        out.append(("群像禁忌", "连续 3 段点头/沉默"))
    tl = tail_lyric(body)
    if tl:
        out.append(("章末抒情偷跑", "、".join(sorted(set(tl)))))
    if compliance.strict:
        cl = CLICHE.findall(body)
        if cl:
            out.append(("[C]文学腔(参考)", "、".join(sorted(set(cl)))))
    return out


compliance.strict = False


def metrics(body):
    n = len(re.sub(r"\s", "", body))
    k = max(n / 1000.0, 0.001)
    ss = sentences(body)
    ps = paras(body)
    lens = [len(s) for s in ss] or [1]
    cv = (statistics.pstdev(lens) / statistics.mean(lens)) if len(lens) > 2 else 0.0
    tg = tail_gold_hits(body)
    short = [p for p in ps if len(re.sub(r"\s", "", p)) <= 12]
    heads = collections.Counter(HEADWORD.findall(re.sub(r"[*>#]", "", body)))
    top = (heads.most_common(1)[0][1] / max(len(ss), 1)) if heads else 0.0
    out = {
        "chars": n, "cv": cv,
        "rev": len(REV.findall(body)) / k,
        "tail": len(tg) / max(len(ps), 1),
        "bold": float(len(BOLD.findall(body))),
        "simile": len(SIMILE.findall(body)) / k,
        "short": len(short) / max(len(ps), 1),
        "dash": len(DASH_END.findall(body)) / k,
        "head": top,
        "vague": len(VAGUE.findall(body)) / k,
        "sent_den": len(ss) / k,
        "pron3": len(PRON3.findall(body)) / k,
        "g_turn": len(TURN.findall(body)) / k,
        "pron_start": ((sum(1 for s in ss if s and s[0] in "他她它")
                        / max(len(ss), 1)) if ss else 0.0),
        "nego": len(NEGO.findall(body)) / k,
        "enum": len(ENUM.findall(body)) / k,
        "tell": len(TELL.findall(body)) / k,
        "ttr": _ttr(body),
        "dede": len(DEDE.findall(body)) / k,
        "isde": len(ISDE.findall(body)) / k,
        "onomat": len(ONOMAT.findall(body)) / k,
        "space": len(SPACE.findall(body)) / k,
        "breath": len(BREATH.findall(body)) / k,
        "exclaim": len(EXCLAIM.findall(body)) / k,
        "redupl": len(REDUPL.findall(body)) / k,
        "comma_in": body.count("\uff0c") / k,
        "_tail_hits": tg,
    }
    out.update(imm_stats(body))
    out.update(net_stats(body))
    out.update(rhythm_stats(body, ss, ps))
    out["para_med"] = (float(statistics.median(
        [len(re.sub(r"\s", "", p)) for p in ps])) if ps else 0.0)
    out["short_run"] = float(_short_run(ps))
    out["sent_med"] = (float(statistics.median(lens)) if ss else 0.0)
    return out


# ---------------------------------------------------------------- 评分
#
# 全部 0–10、越高越好。每个 score_* 返回 (逐项分, 维度分)；逐项分与维度分
# 都是 goodness，不再有「越低越好」的分量。五维等权合成总分。

def score_real(m):
    """真人感：0–10，越高越不像 AI 网文。

    各指标逐项分 good() 的加权平均。权重不必归一到 1，_wavg() 会处理。
    """
    s = {k: good(m[k], g, b) for k, (g, b) in GOOD_BAD.items()}
    s["cv"] = good(m["cv"], *CV_RANGE)
    return s, _wavg(s, WEIGHTS)


def score_imm(m):
    """代入感：0–10，越高越好。imm_perc / imm_soma 达标是区间，区间内满分。"""
    s = {}
    for key, (g, b) in IMM_GOOD_BAD.items():
        if key in IMM_RANGE:
            lo, hi = IMM_RANGE[key]
            v = m[key]
            if v < lo:
                s[key] = clamp(10 - (lo - v) / max(lo * 0.6, 1e-6) * 10)
            elif v > hi:
                s[key] = clamp(10 - (v - hi) / max(hi * 0.5, 1e-6) * 10)
            else:
                s[key] = 10.0
        else:
            s[key] = good(m[key], g, b)
    return s, _wavg(s, IMM_WEIGHTS)


def score_human(m):
    """人味：0–10，越高越像真人。与真人感互补——真人感测「没有机器痕迹」，
    人味测「有人的品质」（口语、对话占比、情绪、叠词）。低 AI 味 ≠ 有人味。
    """
    s = {k: good(m[k], g, b) for k, (g, b) in HUMAN_GOOD_BAD.items()}
    return s, _wavg(s, HUMAN_WEIGHTS)


def score_rhy(m):
    """节奏：0–10，越高越好。"""
    s = {k: good(m[k], g, b) for k, (g, b) in RHY_GOOD_BAD.items()}
    return s, _wavg(s, RHY_WEIGHTS)


def score_syn(m):
    """句法：0–10，越高越好。

    测的是「句子怎么搭」，不是「用了哪些词」——AI 文本的两个硬特征：
    主语全靠第三人称代词顶（不肯换人名 / 称谓 / 省略），以及系统性短句化。
    与「人味」维互补：人味看词汇与情绪，句法看骨架。
    """
    s = {k: good(m[k], g, b) for k, (g, b) in SYN_GOOD_BAD.items()}
    return s, _wavg(s, SYN_WEIGHTS)


# 总分权重：五维等权（各 1/5）。
DIM_WEIGHTS = {"real": 0.20, "human": 0.20, "imm": 0.20,
               "rhy": 0.20, "syn": 0.20}


def score_total(d):
    """总分：五维等权平均，0–10，越高越不像 AI 网文。

    d 形如 {"real": 8.1, "human": 7.3, "imm": 6.9, "rhy": 9.2, "syn": 9.6}。
    """
    return clamp(sum(d[k] * w for k, w in DIM_WEIGHTS.items()))


def bar(v, width=12):
    f = int(round(clamp(v, 0, 10) / 10 * width))
    return "\u2588" * f + "\u00b7" * (width - f)


def grade(t):
    return ("干净" if t < 2.5 else "轻微" if t < 5.0
            else "偏重" if t < 7.0 else "很重")


def grade_imm(v):
    return ("强" if v >= 7.0 else "中" if v >= 5.0
            else "弱" if v >= 3.0 else "差")

