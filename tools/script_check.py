# -*- coding: utf-8 -*-
"""
script_check.py — 网络小说创作技能 v7.27 章节剧本机械质检
用法: python script_check.py <剧本文件.md>
格式规范见 references/短剧剧本.md（场景头/△动作行/角色名：台词/【字幕】）；
转换协议见 references/小说转剧本.md。退出码: 0=通过(可含警告) / 1=硬伤 / 2=输入错误。
分级: [✗] 硬伤(禁止交付) / [!] 警告(必须过目) / [i] 信息
"""
import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 与 check_chapter/retention 同口径：汉字+中文标点（v7.47：排除 U+3000 全角空格）
COUNTABLE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf"
    "\u3001-\u303f"
    "\uff00-\uffef"
    "\u2018\u2019\u201c\u201d\u2014\u2026]"
)
# v7.47：HANZI 补 Ext A——此前与 check_chapter 口径不一致，台词句含 Ext A
# 生僻字时不计入 sent_all，「超20字台词句占比」分母偏小
HANZI = re.compile("[\u4e00-\u9fff\u3400-\u4dbf]")
# v7.47：场景头支持中文数字——「场景一 内景-…」手写剧本此前不识别，
# 误报硬伤「未检出任何场景头」
SCENE_HEAD = re.compile(r"^\s*\u573a\u666f\s*(\d+|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07]{1,3})\s*[\uff5c|]?\s*(\u5185\u666f|\u5916\u666f)")
# 台词分隔冒号：全角为主、半角兼容（v7.30：混用半角冒号的剧本此前整段按旁白计，
# 对白占比被系统性低估，可能触发 45% 硬卡误判）
# v7.47：`(.*)` 替代 `(.+)`——空台词行「张三：」此前落入散行按旁白性文字计，
# no_dlg_run 虚高可能触发"连续无对白"误报
DIALOG = re.compile(r"^\s*([^\u25b3\u3010\u3011\u573a\u25b2][^\uff1a:]{0,14})[\uff1a:](.*)$")
# v7.25：「暗道」作为实体名词（沿着暗道走）不再误判心理残留——须带心理前缀（心中暗道）或
# 后接冒号/引号（暗道："……"）才算心理描写；心想/内心/默念/暗想 保留原判
PSYCH = re.compile("\u5fc3\u60f3|\u5fc3\u4e2d\u6697|\u5185\u5fc3|\u9ed8\u5ff5|\u6697\u60f3"
                   "|(?:\u5fc3\u4e2d|\u5fc3\u91cc|\u6697\u81ea|\u6697\u6697)\u6697\u9053"
                   "|\u6697\u9053[\uff1a\u201c]")
NARR = re.compile(r"^\s*\u3010\u65c1\u767d\u3011|^\s*\u65c1\u767d\uff1a")
MAX_NARR = 2        # 旁白每章上限（小说转剧本·二）
MAX_SUBTITLE = 2    # 【字幕】每章上限
MAX_ACTION_LEN = 60  # △单行字数上限
MAX_NO_DLG_RUN = 15  # 连续无对白行数上限
DIALOG_HARD = 45.0   # 对白占比硬卡线
DIALOG_WARN = 60.0   # 对白占比达标线（45-60 警告）


def countable_len(s):
    return len(COUNTABLE.findall(s))


def main():
    ap = argparse.ArgumentParser(description="章节剧本机械质检 v7.27（格式/占比/心理残留/卡点）")
    ap.add_argument("file")
    args = ap.parse_args()
    # v7.47：isfile 替代 exists——目录输入时 exists 为 True 而 open() 抛
    # IsADirectoryError 未捕获（traceback + exit 1）
    if not os.path.isfile(args.file):
        print(f"[✗] 输入错误：找不到剧本文件 {args.file}")
        sys.exit(2)
    # v7.47：utf-8-sig 剥 BOM（与 check_chapter/fix_said_tags 口径一致）
    lines = [l.rstrip() for l in open(args.file, encoding="utf-8-sig", errors="replace").read().splitlines() if l.strip()]
    failures, warnings = [], []
    if not lines:
        # v7.47：空文件按输入错误 exit 2——此前 exit 1 与"内容硬伤"混同
        print("[✗] 输入错误：空文件")
        sys.exit(2)

    title = lines[0]
    if not (re.search("\u7b2c\\s*\\d+\u7ae0|\u7b2c\\s*\\d+\u96c6", title) and "\u5267\u672c" in title):
        warnings.append(f"首行缺「第N章 …（改编剧本）」标记：{title[:30]}")

    scene_idxs = [i for i, l in enumerate(lines) if SCENE_HEAD.match(l)]
    n_scenes = len(scene_idxs)
    if n_scenes == 0:
        failures.append("未检出任何场景头（格式：场景1 内景-地点-时间）")
    elif n_scenes < 2 or n_scenes > 5:
        warnings.append(f"场景数 {n_scenes} 超出 2-4 建议区（转场要省钱省事）")

    dlg_chars, total_chars = 0, 0
    subtitle_cnt, narr_cnt = 0, 0
    long_actions = []
    no_dlg_run, max_run = 0, 0
    last_scene_has_dlg = False
    tail_is_action = False
    sent_over = sent_all = 0

    for i, l in enumerate(lines[1:], start=1):
        s = l.strip()
        if not s:
            continue
        total_chars += countable_len(s)
        if SCENE_HEAD.match(s):
            no_dlg_run = 0
            last_scene_has_dlg = False
            # v7.47：补 tail_is_action 重置——此前文件以场景头收尾时该标志还是
            # 上一个 △ 行的值，误报"文件以动作/描述行收尾"（告警文字与事实不符）
            tail_is_action = False
            continue
        if s.startswith("\u25b3"):
            ln = countable_len(s)
            if ln > MAX_ACTION_LEN:
                long_actions.append((i, ln))
            no_dlg_run += 1
            max_run = max(max_run, no_dlg_run)
            tail_is_action = True
            continue
        if s.startswith("\u3010"):
            if "\u5b57\u5e55" in s:
                subtitle_cnt += 1
            if NARR.match(s):
                narr_cnt += 1
            no_dlg_run += 1
            max_run = max(max_run, no_dlg_run)
            tail_is_action = False
            continue
        # v7.47：裸「旁白：」前置分支——此前 NARR 只在 startswith("【") 分支内
        # 匹配，裸形式落入 DIALOG 按对白计（旁白上限检查对该形式完全失效，
        # 对白占比虚高；实测 81.6%）
        if NARR.match(s):
            narr_cnt += 1
            no_dlg_run += 1
            max_run = max(max_run, no_dlg_run)
            tail_is_action = False
            continue
        m = DIALOG.match(s)
        if m:
            content = m.group(2)
            c = countable_len(content)
            dlg_chars += c + countable_len(m.group(1))
            no_dlg_run = 0
            last_scene_has_dlg = True
            tail_is_action = False
            for sent in re.split("[\uff01\uff1f\u3002\uff1b\u2026]+", content):
                if HANZI.search(sent):
                    sent_all += 1
                    if countable_len(sent) > 20:
                        sent_over += 1
            continue
        # 既非△/场景/字幕/对白的散行：按旁白性文字计
        no_dlg_run += 1
        max_run = max(max_run, no_dlg_run)
        tail_is_action = True

    if total_chars == 0:
        print("[✗] 无可计内容")
        sys.exit(1)
    ratio = dlg_chars / total_chars * 100
    if n_scenes > 0 and not last_scene_has_dlg:
        warnings.append("末场景无台词卡点——每集结尾必须画面+台词双钩（卡点铁律）")
    if tail_is_action:
        warnings.append("文件以动作/描述行收尾——尾行应为台词或【字幕】强卡点")
    if any(PSYCH.search(l) for l in lines):  # 逐行匹配，防跨行拼接误命中（v7.25）
        failures.append("检出心理描写残留（心想/暗道/内心/默念）——剧本心理必须全部外化（动作+台词）")
    if subtitle_cnt > MAX_SUBTITLE:
        warnings.append(f"【字幕】{subtitle_cnt} 处 > 上限 {MAX_SUBTITLE}")
    if narr_cnt > MAX_NARR:
        warnings.append(f"旁白 {narr_cnt} 处 > 上限 {MAX_NARR}（仅限时间跳转衔接）")
    for i, ln in long_actions:
        warnings.append(f"第{i}行 △动作描述 {ln} 字 > {MAX_ACTION_LEN}——拆短，只写镜头能拍到的")
    if max_run > MAX_NO_DLG_RUN:
        warnings.append(f"连续 {max_run} 行无对白 > {MAX_NO_DLG_RUN}——节奏拖沓，拆台词或删描写")
    if ratio < DIALOG_HARD:
        failures.append(f"对白占比 {ratio:.1f}% < {DIALOG_HARD:.0f}%（剧本比小说更依赖台词）")
    elif ratio < DIALOG_WARN:
        warnings.append(f"对白占比 {ratio:.1f}%（45-60 警告区，达标线 {DIALOG_WARN:.0f}%）")
    if sent_all and sent_over / sent_all > 0.3:
        warnings.append(f"超20字台词句占 {sent_over / sent_all * 100:.0f}%——单句 ≤15 字优先，口语化拆分")

    print("=" * 46)
    print("【剧本质检】" + os.path.basename(args.file))
    print("=" * 46)
    print(f"[i] 场景={n_scenes} 对白占比={ratio:.1f}% 字幕={subtitle_cnt} 旁白={narr_cnt} "
          f"最长连续无对白={max_run}行 超长台词句={sent_over}/{sent_all}")
    for f in failures:
        print(f"[✗] {f}")
    for w in warnings:
        print(f"[!] {w}")
    if failures:
        print("结论：剧本有硬伤，先修复再复测（只动病灶场景）")
        sys.exit(1)
    print("结论：剧本过检" + ("（含警告，逐条过目）" if warnings else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
