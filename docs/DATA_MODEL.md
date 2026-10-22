# 数据模型 v0.2

完整正式语料在 `data/collected.json.gz`，原始 12 人试验数据保留作单元测试，不是默认输入。

人物状态：`source_verified` 表示已采集、校验结构化陈述；`reviewed` 表示人工核对的公开履历；`candidate` 不参与排名。自动采集不冒称人工逐人审核。

教育包含 `institution`、`level`、`sources`、具体 `degree_entities`。`level` 为 `bachelor/master/phd/postdoc/unknown`。博士层级按来源实体及其子类层级识别，具体实体仍保留，不声称所有博士类学位都具有相同训练。荣誉学位设置 `honorary` 并排除。未知层级不产生权重。

任职包含 `institution`、`role`、`observed`、`current`、可用的 `start/end` 和 `sources`。`observed: true` 说明存在已获取的任职陈述；`current: null` 是当前状态未知，不会补成 true。来源有去世记录或明确过去结束日期时标记 `current: false`。`role_basis` 说明角色来自职业类型关系还是企业类别；职业类型不能保证每个历史岗位的具体职级。

每条来源优先保留 `https://www.wikidata.org/wiki/Q…#Q…-statement-UUID` 锚点及其 HTTPS P854 原始引用。空值、somevalue 匿名节点和未分类学位不能被当作实际机构或博士。

个人奖项含 `type/year/sources`。支持 `fields/abel/wolf_math/nobel/turing/ieee_honor/ieee_edison`；未给年份的不补写。`milestones` 是单独的机构事件数组，需要独立唯一 ID、机构归属和引用，不能从个人学历自动推导。

`coverage_report` 记录完整采集机构、事实批次、人物总数、职业过滤、学历缺失、人工合并和来源日期。它说明实际公开源覆盖，不代表官网名单人口普查的完整率。

浏览器输入 `site/data.json.gz` 为轻量副本：共用字段由 `people_defaults` 提供，省略重复的任职日期与原始引用；算法不需要的完整细节保存在 `site/profiles/<shard>.json.gz`，点击人物时加载。完整版永远可从 `site/corpus.json.gz` 下载。
