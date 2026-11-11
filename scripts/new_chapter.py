#!/usr/bin/env python3
"""Create a bilingual chapter scaffold from book.toml and mark it as draft."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "book.toml"


def activate_chapter(config_text: str, chapter_id: str) -> str:
    lines = config_text.splitlines()
    block_start: int | None = None
    block_end = len(lines)
    in_target = False

    for index, line in enumerate(lines):
        if line.strip() == "[[chapters]]":
            if in_target:
                block_end = index
                break
            block_start = index
            in_target = False
            continue
        if block_start is not None and re.match(r"^id\s*=\s*", line.strip()):
            value = line.split("=", 1)[1].strip().strip('"')
            if value == chapter_id:
                in_target = True

    if not in_target or block_start is None:
        raise SystemExit(f"Could not find target chapter block for '{chapter_id}'.")

    for index in range(block_start, block_end):
        if re.match(r"^status\s*=", lines[index].strip()):
            lines[index] = 'status = "draft"'
            return "\n".join(lines) + "\n"
    raise SystemExit(f"Could not find status field for '{chapter_id}'.")


def chapter_template(chapter: dict[str, object]) -> str:
    title_zh = str(chapter["title_zh"])
    title_en = str(chapter["title_en"])
    subtitle_zh = str(chapter.get("subtitle_zh", ""))
    subtitle_en = str(chapter.get("subtitle_en", ""))
    return f"""<!-- lang:zh -->

> {subtitle_zh}

## 五种特质

- **意志力**：他在压力、损失和反对中如何继续行动？
- **计划**：他如何把目标拆成资源、时机、组织与步骤？
- **决心**：他如何选定方向，并承担随之而来的代价？
- **团队**：他如何让不同的人围绕同一个目标行动？
- **理想**：他试图重写怎样的更大秩序？

## 视野

他承诺怎样的世界？这个承诺回应了什么真实问题，又删除了哪些复杂性？

## 伤口

创伤、羞辱、丧失或不安全感如何塑造了他的判断？

## 聚拢

谁跟随他？他们得到的是安全、利益、身份、意义，还是仅仅免于恐惧？

## 执行

他依靠哪些能力、信息、组织和叙事把意志变成行动？

## 坚持

他为何持续？是价值承诺、身份融合、沉没成本，还是无法承认失败？

## 自由检验

同意、异议与退出空间在哪里失守？

## 理性检验

证据、可逆性与共同审议在哪里失守？

## 反向练习

保留哪些能力，同时加上什么边界，才能避免支配？

## 文本与语境

- 作品与版本待补。

<!-- lang:en -->

> {subtitle_en}

## Five Traits

- **Will**: How does he keep acting through pressure, loss, and opposition?
- **Planning**: How does he turn a goal into resources, timing, organization, and steps?
- **Resolve**: How does he choose a direction and accept its costs?
- **Team**: How does he make different people act around one goal?
- **Ideal**: What larger order does he seek to rewrite?

## Vision

What world does this figure promise? What real problem does the promise answer, and what complexity does it delete?

## The Wound

How do trauma, humiliation, loss, or insecurity shape the character's judgment?

## Allegiance

Who follows, and what do they receive: safety, interest, identity, meaning, or only relief from fear?

## Execution

Which capacities, information, organizations, and narratives turn will into action?

## Persistence

Why does the character continue: fidelity to a value, identity fusion, sunk cost, or an inability to admit failure?

## Freedom Test

Where do consent, dissent, and exit fail?

## Reason Test

Where do evidence, reversibility, and shared deliberation fail?

## Reverse Practice

Which capacities can be preserved, and what boundary would prevent domination?

## Text and Context

- Works and versions to be added.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chapter_id", help="Chapter id from book.toml, for example 'han-li'.")
    args = parser.parse_args()

    config_text = CONFIG.read_text(encoding="utf-8")
    with CONFIG.open("rb") as handle:
        config = tomllib.load(handle)
    chapter = next(
        (item for item in config["chapters"] if item["id"] == args.chapter_id), None
    )
    if chapter is None:
        available = ", ".join(item["id"] for item in config["chapters"])
        raise SystemExit(f"Unknown chapter id '{args.chapter_id}'.\nAvailable: {available}")
    if chapter.get("status") in {"draft", "review", "final"}:
        raise SystemExit(f"Chapter '{args.chapter_id}' is already active.")

    destination = ROOT / str(chapter["file"])
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(chapter_template(chapter), encoding="utf-8")
    CONFIG.write_text(activate_chapter(config_text, args.chapter_id), encoding="utf-8")
    print(f"created {destination.relative_to(ROOT)}")
    print(f"activated {args.chapter_id} in book.toml")
    print("Run: python scripts/build_book.py --variant all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

