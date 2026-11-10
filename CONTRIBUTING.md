# 参与修订

## 适合提交的内容

- 事实错误、人物版本差异或引用不准确。
- 论证跳跃、概念混用、对动机的过度推断。
- 中文或英文版本的判断不一致。
- 自由、理性、纠错、退出等核心术语使用不一致。
- 构建器、EPUB 结构、可访问性或 GitHub Pages 流程问题。

## 提交流程

1. 一个 Pull Request 尽量只处理一章或一个构建问题。
2. 说明修改的是事实、结构、措辞还是出版流程。
3. 标出所依据的原作、改编版本或可靠二手资料。
4. 新增或改动双语章节后运行：

```powershell
python scripts/build_book.py --check
python -m unittest discover -s tests -v
```

## 编辑判断

- 不收录长段原作文本、盗版资源或未经授权的角色图片。
- 不把“理解反派”改写为“替反派辩护”。
- 不把某一改编版本的设定当作所有版本的事实。
- 提取可迁移能力时，必须同时写出边界、风险和替代做法。
- 新增人物前先确认它是否能提供新的机制，而不只是增加知名度。

## English

Keep each pull request focused on one chapter or one publishing concern. Identify whether a change concerns fact, structure, wording, or tooling, and name the primary text or adaptation behind factual corrections.

Run both commands before submitting:

```powershell
python scripts/build_book.py --check
python -m unittest discover -s tests -v
```

Understanding a villain is not the same as excusing the villain. The project favors short, necessary quotation, clear version distinctions, and capacity analysis that includes boundaries and alternatives.

