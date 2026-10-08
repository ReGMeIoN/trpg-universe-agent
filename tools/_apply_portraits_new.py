# -*- coding: utf-8 -*-
"""登记两个新团的 PC 立绘（口径：PC 严格用卡内原图；后辈用主人给的 _立绘.jpg）。

源图已逐张人工过目（AI 生成的水印会单独标注）。脚本只做三件事：
  1. 校验源文件存在（防错字）
  2. 拷进 数据/头像/<团名>_<角色名>.<ext>
  3. 回写 characters.json 的 avatar（写前备份 + 写后复验）

用法:
    python tools/_apply_portraits_new.py            # dry-run
    python tools/_apply_portraits_new.py --apply
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))
IMG = ROOT / ".trpg" / "card_images"
JUNIOR = WS / "素材" / "魔法少女育成计划 6" / "带带魔法少女后辈卡"
DATA = WS / "数据"
AVATARS = DATA / "头像"

G_YY = "阴阳差事录 超自然怪谈"
G_MG6 = "魔法少女育成计划 6"

# 角色 id -> 源图（左：卡内图目录/后辈立绘目录）
PORTRAITS: dict[str, dict[str, Path]] = {
    G_YY: {
        "yy_yuxiuli": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "于秀丽(1) (1)__image2.jpg",
        "yy_liulong": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "刘泷(1) (1)__image1.png",
        "yy_yexiaoxiao": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "叶千筱 (3)__image1.jpg",
        "yy_linxiaoyuan": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "林小鸢（赤鸢） (2)__image2.jpg",
        "yy_yuannuonuo": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "袁糯糯 (1)__image2.jpg",
        "yy_xuanyuandongqing": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "轩辕冬青(1)(3) (1)__image2.png",
        # 知行：卡内 image2.jpeg 的 zip CRC 写错导致 z.read() 抛 BadZipFile，
        # 曾被判成「图损坏、无立绘」。实则解压出来的字节完好（已用 PIL 验过是 1280×1280 JPEG）→
        # 给 `_extract_sheet_images.py` / `_cards_batch.py` 加了绕过 CRC 的读法后正常抽出（2026-10-05）。
        "yy_zhixing": IMG / "yin-yang_阴阳差事录_超自然怪谈" / "阴阳差事录-牛(1)__image2.jpg",
    },
    G_MG6: {
        "mg6_eryiling_shasha": IMG / "mahou6_魔法少女育成计划_6" / "二伊棂纱纱__image1.jpg",
        "mg6_ciwei": IMG / "mahou6_魔法少女育成计划_6" / "带带后辈魔法少女-Zweig__image1.png",
        "mg6_baixuan": IMG / "mahou6_魔法少女育成计划_6" / "白萱 (1)__image2.jpg",
        "mg6_luxila": IMG / "mahou6_魔法少女育成计划_6" / "露西菈 (2)__image2.jpg",
        "mg6_dujuan": JUNIOR / "杜鹃_立绘.jpg",
        "mg6_yu": JUNIOR / "雨_立绘.jpg",
        "mg6_farernase": JUNIOR / "法尔纳塞_立绘.jpg",
        "mg6_shenchuan_maliya": JUNIOR / "神川玛利亚_立绘.jpg",
        "mg6_xizhi_huatian": JUNIOR / "花田_立绘.jpg",
    },
}
# 已知瑕疵（写进报告，不阻挡登记）
NOTES = {
    "yy_xuanyuandongqing": "卡内原图右下角带「豆包AI生成」水印（与圣剑英雄谭飒飒米的小红书水印同类；按口径原样使用）",
    "yy_zhixing": "卡内原图右下角同样带「豆包AI生成」水印；卡 zip 的 CRC 写错（工具已绕过）",
    "mg6_baixuan": "用的是「生长形态」立绘（卡内另有「毁灭形态」image1）",
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    chars_path = DATA / "characters.json"
    doc = json.loads(chars_path.read_text(encoding="utf-8"))
    index = {c.get("id"): c for c in doc.get("characters") or []}

    plan: list[tuple[str, str, Path, Path]] = []
    missing_src, missing_node = [], []
    for group, table in PORTRAITS.items():
        for cid, src in table.items():
            if cid not in index:
                missing_node.append(cid)
                continue
            if not src.is_file():
                missing_src.append(str(src))
                continue
            name = index[cid].get("name") or cid
            ext = src.suffix.lower()
            dst = AVATARS / f"{group}_{name}{ext}"
            plan.append((cid, name, src, dst))

    print(f"待登记 {len(plan)} 张")
    for cid, name, src, dst in plan:
        print(f"  {cid:<28} {name:<20} <- {src.name}  ->  {dst.name}")
    if missing_node:
        print(f"!! 补丁里没有这些 id: {missing_node}")
    if missing_src:
        print(f"!! 源文件不存在 {len(missing_src)} 个:")
        for m in missing_src:
            print(f"   {m}")
        if not apply:
            print("   (dry-run 会继续；--apply 会被拦下)")
    print("\n已知瑕疵:")
    for cid, note in NOTES.items():
        print(f"  {cid}: {note}")

    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    if missing_src:
        print("\n源文件缺失 -> 拒绝写入")
        return 1

    AVATARS.mkdir(parents=True, exist_ok=True)
    bak = chars_path.with_name(chars_path.name + f".bak_portrait_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(chars_path, bak)
    for cid, name, src, dst in plan:
        shutil.copy2(src, dst)
        index[cid]["avatar"] = f"数据/头像\\{dst.name}"
    chars_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")

    chk = json.loads(chars_path.read_text(encoding="utf-8"))
    ci = {c.get("id"): c for c in chk["characters"]}
    ok = 0
    for cid, name, src, dst in plan:
        av = ci[cid].get("avatar")
        rel = (av or "").split("\\")[-1].split("/")[-1]
        if av and (DATA / "头像" / rel).is_file():
            ok += 1
        else:
            print(f"  !! 复验失败 {cid}: avatar={av}")
    print(f"复验: {ok}/{len(plan)} 张头像已落地且路径可解析")
    print(f"头像目录现有 {len(list(AVATARS.glob('*')))} 个文件")
    return 0 if ok == len(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
