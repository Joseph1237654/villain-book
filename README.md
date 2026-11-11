# 反派书：通往自由理性之路

**The Villain Book: A Road to Freedom and Reason**

**2.0 版：九位人物，五种特质**

通过九位流行文化人物，把他们的**个人力量与心理模式**视为学习对象：坚定的意志力、缜密的计划、不可动摇的决心、众心一致的团队、充满野心的理想。

## 当前状态

- 九章目录与统一分析框架已经完成，选目按网文、漫画两编组织。
- 序、导论与三篇样章已有中英双语初稿：方源、魂天帝、万磁王。
- 2.0 版采用四部网文与五部漫画的九人名单，作品与人物对应关系见 `OUTLINE.md`。
- 成品提供中文版、英文版、双语版，每种均有 HTML、TXT、EPUB。
- 内容按章节逐步启用；`planned` 章节不会进入成品。

阅读全书结构：[OUTLINE.md](OUTLINE.md)  
核对附件选目：[CATALOG_AUDIT.md](CATALOG_AUDIT.md)  
查看写作规范：[STYLEGUIDE.md](STYLEGUIDE.md)  
查看双语术语：[GLOSSARY.md](GLOSSARY.md)

## 构建

项目只需要 Python 3.11 或更高版本，不依赖第三方包。

```powershell
python scripts/build_book.py --check
python scripts/build_book.py --variant all
python -m unittest discover -s tests -v
```

成品输出到 `dist/`：

```text
dist/
  index.html
  villain-book-zh.html
  villain-book-zh.txt
  villain-book-zh.epub
  villain-book-en.html
  villain-book-en.txt
  villain-book-en.epub
  villain-book-bilingual.html
  villain-book-bilingual.txt
  villain-book-bilingual.epub
  manifest.json
  SHA256SUMS.txt
```

`index.html` 是双语网页阅读版，可在浏览器中直接打开，也可由 GitHub Pages 发布。

## 开始写下一章

目录中的每一章已经在 `book.toml` 中预先登记。以韩立为例：

```powershell
python scripts/new_chapter.py han-li
```

命令会创建 `content/04-han-li.md`，并将该章状态从 `planned` 改为 `draft`。随后补写中英文正文：

```markdown
<!-- lang:zh -->
中文正文

<!-- lang:en -->
English text
```

再次运行构建即可把该章加入三种成品。章节状态可设为：

- `planned`：仅保留目录，不进入成品。
- `draft`：已有双语初稿，进入成品。
- `review`：结构完整，正在核对事实与译名。
- `final`：可发布版本。

## 项目结构

```text
book.toml                 书名、版本、编目与九章状态
content/                  中英双语章节源文件
scripts/build_book.py     零依赖 HTML / TXT / EPUB 构建器
scripts/new_chapter.py    按目录创建下一章双语骨架
tests/                    构建与出版结构测试
.github/workflows/        自动构建、测试并发布 GitHub Pages
```

GitHub Actions 在推送到 `main` 后自动执行内容校验、构建和测试，并把 `dist/` 发布到 GitHub Pages。首次使用时，需要在仓库的 **Settings → Pages** 中将来源设为 **GitHub Actions**。

## 写作原则

- 理解动机，但不取消责任。
- 不把冷酷等同于强大，不把效率等同于正确。
- 每一章都写出愿景的真实吸引力，也写出它删除了什么。
- 区分合作与依赖、价值承诺与身份执念、可逆试验与升级承诺。
- 中英文事实与判断保持一致，但不要求逐句直译。

## 版权

本书讨论受版权和商标保护的虚构人物与作品，不主张角色、商标或原作情节的所有权。公开发布前请阅读 [RIGHTS.md](RIGHTS.md)，确认许可、引文与第三方素材授权。当前仓库未设置开放许可，默认保留所有权利。

## English

This repository is a bilingual, progressively published book about nine popular-culture figures: four from web fiction and five from comics. Each chapter treats their personal power and psychological patterns as objects of study: unwavering will, rigorous plans, immovable resolve, cohesive teams, and ambitious ideals. It then applies two tests: **freedom** and **reason**.

The book is not a celebration of villainy or a disguised success manual. It asks how a villain's power forms, how that power operates, what it deletes, whether dissent and exit remain possible, and whether judgment stays open to correction.

The project currently contains a bilingual preface, introduction, and three sample chapters on Fang Yuan, Hun Tiandi, and Magneto. The remaining chapters are configured in `book.toml` and will enter the finished editions as their bilingual drafts are completed.

Version 2.0 follows the nine figures confirmed in the current outline.

Build all editions with:

```powershell
python scripts/build_book.py --variant all
```

The only runtime requirement is Python 3.11 or newer.

