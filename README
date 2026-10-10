# vnstat-tuned

vnstat-tuned 为 [vnStat](https://github.com/vergoh/vnstat) 增加分钟级月度账期，可以按每月指定日期、小时和分钟汇总网卡流量。统计沿用内核计数器和原有 SQLite 数据库；持久化的五分钟历史分辨率保持不变。

## 快速开始

在 Debian 或 Ubuntu 上安装构建依赖并编译：

```sh
sudo apt-get install build-essential autoconf automake pkg-config \
  libsqlite3-dev libgd-dev check
git clone --branch billing-v2.13 https://github.com/in-valid-username/vnstat-tuned.git
cd vnstat-tuned
autoreconf -fi
./configure
make -j2
make check
```

安装与服务配置见[构建和测试](docs/build-and-test.md)。在守护进程及查询工具共用的配置文件中设置账期，例如每月 7 日 18:24：

```ini
MonthRotate 7
MonthRotateHour 18
MonthRotateMinute 24
UseUTC 0
```

`UseUTC 0` 使用进程本地时区。修改现有账期前备份配置和数据库，并在计划好的边界切换；旧记录保留原有汇总结果。参数、采样精度和升级步骤见[账期配置](docs/billing.md)。

## 文档

- [账期配置](docs/billing.md)：参数、时区、采样与切换。
- [JSON 与 XML](docs/output.md)：账期字段和输出兼容性。
- [构建和测试](docs/build-and-test.md)：依赖、安装和回归测试。
- [修复与兼容性](docs/fork-review.md)：修复位置、上游来源和已知问题。
- [验证报告](docs/reports/2026-10-04-validation.md)：测试环境、结果与失败记录。

## 来源与许可

vnStat 原作者为 Teemu Toivola。本分支使用 GPT-6.1 Sol 辅助开发，代码按 [GPL-2.0](COPYING) 分发。源代码基线及上游文档见[来源说明](docs/reference/baseline.md)。
