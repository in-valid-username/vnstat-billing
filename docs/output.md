# JSON 与 XML 输出

本分支保留流量字段和月度标签，追加查询所用的账期配置。输出入口为 [dbjson.c](../src/dbjson.c) 的 `showjson` 和 [dbxml.c](../src/dbxml.c) 的 `showxml`。

## 账期字段

| 设置 | JSON 顶层字段 | XML `billing` 子元素 |
| --- | --- | --- |
| 起始日 | `monthrotate`，整数 | `monthrotate` |
| 小时 | `monthrotatehour`，整数 | `monthrotatehour` |
| 分钟 | `monthrotateminute`，整数 | `monthrotateminute` |
| 年度边界 | `monthrotateaffectsyears`，布尔值 | `monthrotateaffectsyears`，0 或 1 |
| UTC 模式 | `useutc`，布尔值 | `useutc`，0 或 1 |

这些字段反映查询进程的当前配置。数据库未逐行保存历史账期参数；修改查询配置不会重新分配旧流量。时间与标签规则见[账期配置](billing.md#时区与标签)。解析器应允许新增字段。

## 输出修复

接口名和别名由 `jsonstring`、`xmlstring` 转义。XML 1.0 禁止的 ASCII 控制字符替换为 U+FFFD；JSON 百分比由 `jsonpercentage` 使用小数点输出，不随进程的小数逗号地区设置改变。

XML 百分位元素使用合法名称 `percentile_95`。旧名称 `95th_percentile` 的文本匹配使用方需要更新。百分位统计窗口见[采样与保存](billing.md#采样与保存)。

输出回归入口为 [output_parse_tests.py](../tests/output_parse_tests.py)；测试方法见[构建和测试](build-and-test.md#输出与示例)。
