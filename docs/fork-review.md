# 修复与兼容性

本分支增加分钟级账期，并修复采集、数据库、输出和示例程序中的具体缺陷。源码基线见[来源说明](reference/baseline.md)，配置与采样规则见[账期指南](billing.md)。

## 修复记录

| 模块 | 原问题 | 实现与回归位置 |
| --- | --- | --- |
| 元数据 SQL | 128 字节缓冲区按 512 字节长度格式化，长元数据会越界 | [dbsql.c](../src/dbsql.c) 的 `db_setinfo` 使用 SQLite 动态格式化；[数据库测试](../tests/dbsql_tests.c) |
| UTC 采集缓存 | 将数据库日历时间当作实际 epoch，非 UTC 进程可能延迟采集或丢失初始间隔 | `db_getinterfaceinfo_epoch` 分离实际时间读取；[守护进程测试](../tests/daemon_tests.c) |
| 保留期 SQL | 256 字节缓冲区按 512 字节长度传入 | [dbsql.c](../src/dbsql.c) 按实际数组长度格式化 |
| 数据合并 | 来源查询失败时在错误数据库句柄回滚 | [dbmerge.c](../src/dbmerge.c) 与 [合并测试](../tests/dbmerge_tests.c) |
| 小时图 | 单位填充超出行边界，长接口标题可能溢出 | [image.c](../src/image.c)、[image_support.c](../src/image_support.c) 与 [图片测试](../tests/image_tests.c) |
| 图片速率 | 零值或小于单位的速率产生零分母 | 同上，检查分母并保留非零速率 |
| 95 百分位 | 结束边界包含下月样本，固定样本上限忽略夏令时 | [percentile.c](../src/percentile.c) 仅统计账期内完整样本；[百分位测试](../tests/percentile_tests.c) |
| JSON/XML 平均值 | RX+TX 平均值表达式缺括号 | [dbjson.c](../src/dbjson.c)、[dbxml.c](../src/dbxml.c) |
| 输出格式 | XML 元素名非法，文本未转义，小数逗号使 JSON 无效 | [输出说明](output.md) 与 [解析测试](../tests/output_parse_tests.py) |
| CGI/PHP 示例 | Shell 插值、HTML 转义和缓存校验存在不安全路径 | [examples](../examples)、[示例回归](../tests/example_security.py) |
| 测试退出码 | 直接返回失败数量可能溢出为成功退出码 | [vnstat_tests.c](../tests/vnstat_tests.c) 对非零失败返回 `EXIT_FAILURE` |
| 源码包 | Markdown 复制规则依赖源码内构建，分发遗漏文档和测试 | [Makefile.am](../Makefile.am) 使用 `srcdir` 和显式分发清单 |

示例修复参考上游提交 [2098360](https://github.com/vergoh/vnstat/commit/2098360)、[1158c9b](https://github.com/vergoh/vnstat/commit/1158c9b)、[5f49455](https://github.com/vergoh/vnstat/commit/5f49455)、[994d323](https://github.com/vergoh/vnstat/commit/994d323) 和 [978d8d9](https://github.com/vergoh/vnstat/commit/978d8d9)。小时图修复参考 [e6d6260](https://github.com/vergoh/vnstat/commit/e6d6260)。

## 时区与历史数据

上游数据库 getter 使用日历时间表示。`UseUTC 1` 与非 UTC 查询进程组合时，夏令时缺失、重复时间以及历史偏移可能产生歧义；现代固定 UTC+8 账期没有夏令时切换。查询建议见[账期指南](billing.md#时区与标签)。

历史新加坡用例依照数据库 getter 的契约比较日期。Ubuntu 22.04、Ubuntu 24.04 和 macOS 的 SQLite 对 1970 年 UTC+7:30 的换算不同，因此该用例检查正确的月界、样本数、覆盖率和总量，现代账期用例仍检查精确时间。

账期输出字段反映当前查询配置。数据库未保存逐月配置历史，账期变更也不重算旧记录。完整说明见[输出字段](output.md#账期字段)。

## 已知问题

- 部分历史汇总平均值使用当前年份的闰年状态。
- 极端百分位限制参数的乘法范围仍需单独检查。
- 非法 UTF-8 别名和旧 metrics/示例的部分显示边界仍需处理。

上述项目保留为后续修复项。已执行的系统、工具链和测试结果见[2026-10-04 验证](reports/2026-10-04-validation.md)。
