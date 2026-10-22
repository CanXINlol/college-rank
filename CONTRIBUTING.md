# 贡献指南

欢迎新增真实履历、官方目录适配器和方法改进。先复现本地测试再提交 PR。

数据贡献需要：稳定人员/机构 ID、教育层级、任职角色和状态、核验日期、直接支持事实的公开引用。未知保留未知，不补写猜测。优先使用大学/研究机构官网、个人官方 CV、授予学位记录、奖项官方目录。勿提交私人联系方式、无法公开的数据、整页受版权保护的原文或无来源的“AI 推测”。

修改 `data/curated.json` 后运行：

```bash
python3 -m collegerank validate
python3 -m unittest discover -s tests -v
node --test tests/*.test.mjs
python3 -m collegerank export
```

讨论新权重时请解释它度量什么，以及对学校规模、学科与地区的影响。算法改动应同步 Python 和 JS，并通过一致性测试。
