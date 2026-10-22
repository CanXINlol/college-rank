# 数据模型与来源约定

所有排名输入都在 `data/curated.json`。候选文件沿用相同结构，但 `status: candidate` 永远不参与排名。

```json
{
  "as_of": "2026-10-22",
  "coverage": "curated-pilot",
  "institutions": [
    {"id":"x","name":"X 大学","en":"University X","country":"中国","code":"CN","short":"UX","kind":"university","url":"https://example.edu","wikidata":"Q123"}
  ],
  "people": [
    {
      "id":"stable-person-id",
      "name":"Example Person",
      "field":"计算机科学",
      "status":"reviewed",
      "checked_at":"2026-10-22",
      "education":[{"institution":"x","level":"phd","honorary":false,"sources":["https://example.edu/cv"]}],
      "appointments":[{"institution":"x","role":"faculty","current":true,"sources":["https://example.edu/profile"]}],
      "awards":[{"type":"turing","year":2024,"sources":["https://example.edu/award"]}]
    }
  ],
  "milestones": []
}
```

以上是结构示例，不能当作真实人物导入。

机构 `kind` 支持 `university`、`institute`、`company`；企业不进入学术节点排名。每个人需稳定唯一 ID，不能仅按姓名合并。Wikidata 候选采用 `wd:QID`，核验导入时需与现有规范机构及人员 ID 合并。

教育 `level` 支持 `bachelor`、`master`、`phd`、`postdoc`、`unknown`。`postdoc` 表示培养经历，不是学位。未知层级不计权重；荣誉学位设置 `honorary: true` 后排除。

任职 `role` 支持 `faculty`、`adjunct`、`emeritus`、`researcher`、`postdoc`、`industry`、`unknown`。只有 `current` 严格等于 `true` 的选定角色才产生边；`null` 表示未知，`false` 为历史记录。可附 `start`、`end` ISO 日期。

`sources` 必须是非空 HTTPS 链接数组，引用应直接支持相应事实。核验日期是本项目核对日期，不等于来源发布日期。没有核对的实时状态必须留空，不能用“无离职日期”代替当前任职证据。

奖项类型：`fields`、`abel`、`wolf_math`、`nobel`、`turing`、`ieee_honor`、`ieee_edison`。按人/奖项类型/年份去重。

IEEE Milestone 独立记录示例：

```json
{"id":"ieee-event-stable-id","institution":"x","year":2000,"status":"reviewed","sources":["https://history.ieee.org/example"]}
```

需要核对实际创新机构与地点；不得仅因一名参与者曾经在某校上学，就把该成就归给母校。当前种子数据未收录 Milestone。

快照数据库为不可变 `snapshots(sha256, created_at, payload)`，相同内容哈希只存一次。它保留每次榜单输入，支持审计和复现；不是用于百万级多用户查询的生产数据库。
