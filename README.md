# vnStat

vnStat is a console-based network traffic monitor that uses the network
interface statistics provided by the kernel as information source. This
means that vnStat won't actually be sniffing any traffic and also ensures
light use of system resources regardless of network traffic rate.

By default, traffic statistics are stored on a five minute level for the last
48 hours, on a hourly level for the last 4 days, on a daily level for the
last 2 full months and on a yearly level forever. The data retention durations
are fully user configurable. Total seen traffic and a top days listing is also
provided. Optional image output is available in systems with the
[GD Graphics Library](https://libgd.github.io/) installed. Image output support
uses of TrueType fonts if support is included in used GD Graphics Library.

See the [official webpage](https://humdi.net/vnstat/) for additional details
and output examples.

## Getting started

vnStat works best when installed. It's possible to either use the latest
stable release, get the current development version from git or use a
Docker container containing the pre-compiled latest stable release.

### Stable version

  1. `wget https://humdi.net/vnstat/vnstat-latest.tar.gz`
  2. optional steps for verifying the file signature
     1. `wget https://humdi.net/vnstat/vnstat-latest.tar.gz.asc`
     2. `gpg --keyserver keys.openpgp.org --recv-key 0xDAFE84E63D140114`
     3. `gpg --verify vnstat-latest.tar.gz.asc vnstat-latest.tar.gz`
     4. the signature is correct if the output shows "Good signature from Teemu Toivola"
  3. `tar zxvf vnstat-latest.tar.gz`
  4. `cd vnstat-*`

### Development version

  1. `git clone https://github.com/vergoh/vnstat`
  2. `cd vnstat`

In both above cases, continue with instructions from the [INSTALL](INSTALL.md) or
[INSTALL_BSD](INSTALL_BSD.md) file depending on used operating system.
Instructions for upgrading from a previous version are included in the
[UPGRADE](UPGRADE.md) file. Release notes can be found from the [CHANGES](CHANGES)
file.

### Docker container

```text
docker run -d \
    --restart=unless-stopped \
    --network=host \
    -e HTTP_PORT=8685 \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/timezone:/etc/timezone:ro \
    --name vnstat \
    vergoh/vnstat
```

For more details regarding container usage, available environment variables and
a docker-compose.yml example, see the [vergoh/vnstat-docker](https://github.com/vergoh/vnstat-docker)
git repository or [Docker Hub](https://hub.docker.com/r/vergoh/vnstat). The same
container images are also being published as `ghcr.io/vergoh/vnstat`.

## Contacting the author

  - **email** - Teemu Toivola &lt;tst at iki dot fi&gt;
  - **irc** - Vergo ([IRCNet](http://www.irchelp.org/networks/ircnet/))
  - **git** - https://github.com/vergoh/vnstat

Bug reports, improvement ideas, feature requests and pull requests should be
sent using the matching features on GitHub as those are harder to miss or
forget.

---

## vnstat-tuned：分钟级账期增强版

这是由中文用户维护的 vnStat fork。本节为追加说明，上方原始 README 保持不变。
上方的下载、Docker 和开发版命令安装的是**上游 vnStat**，不是这个 fork。

本项目基于稳定版 **v2.13**，基线提交为
`a77ace6e24028f22ec7213000daedfd5c7a9d70f`，不是尚未发布的 2.14 开发版。
原始开发版 README 中的 TrueType 字体说明不适用于本项目的 2.13 构建。
最初 fork 的开发版快照仍在 `master`，增强版默认分支为 `billing-v2.13`。

### 修改范围

新增**一分钟精度的月度账期设置**，可以指定每月几号、几点、几分开始新账期。
月度汇总不再被内存中的五分钟合并边界限制：非五分钟整点的设置使用一分钟缓存。
持久化的五分钟历史数据、SQLite 数据库结构、网卡计数器、字节计量方式、
数据保留默认值、程序名称及 GPL-2.0 许可保持原样，不新增另一套采集服务。

这不是主机商账单 API、抓包程序、配额控制器或网站后台。网卡统计与主机商
计量可能存在差异；一分钟账期也不等于逐包准确计费。

### 账期配置

在守护进程及查询工具使用的配置文件中设置，例如每月 7 日 18:24 开始新账期：

```ini
# 使用服务器本地时区，每月 7 日 18:24 切换账期。
MonthRotate 7
MonthRotateHour 18
MonthRotateMinute 24
MonthRotateAffectsYears 0
UseUTC 0

# 保持较短的采集间隔；这不是数据库保存频率。
PollInterval 5
UpdateInterval 20
```

| 配置项 | 有效范围 | 默认值 |
| --- | --- | --- |
| `MonthRotate` | 1–28，与上游一致 | 1 |
| `MonthRotateHour` | 0–23 | 0 |
| `MonthRotateMinute` | **0–59 的任意整数** | 0 |
| `MonthRotateAffectsYears` | 0 或 1 | 0 |
| `UseUTC` | 0 或 1 | 0 |

- 分钟 `24`、`26`、`59` 都有效，不再要求是 5 的倍数，也不会自动取整。
- 越界值会警告并退回默认值，例如 `MonthRotateMinute 60` 会退回 `0`。
- `UseUTC 1` 按 UTC 切换；`UseUTC 0` 按进程本地时区切换。`vnstatd`、`vnstat`
  和 `vnstati` 必须使用一致的配置及时区。固定 UTC+8 可使用 `Asia/Singapore`；
  网站访问者的时区不应改变服务器的统计账期。
- 年度统计默认按自然年计算。设置 `MonthRotateAffectsYears 1` 后，年度边界
  也使用 1 月的同一日期、小时和分钟。
- 月度记录标签仍为 `YYYY-MM-01`。以上示例的 1 月标签表示
  1 月 7 日 18:24 至 2 月 7 日 18:24，起点包含，终点不包含。
- 默认小时和分钟均为 `0`，不添加配置时仍按午夜切换。

### 从五分钟账期版升级

原有 `0、5、10…55` 设置继续有效；现在可直接把近似值 `25` 改为真实值 `24`。
已有数据库**不需要结构迁移**，但旧数据不会自动重新分桶或按新账期追溯重算。
修改账期前备份数据库和配置，选择计划好的切换边界，协调采集与查询进程的配置。
不要在同一个月中频繁切换规则，也不要同时运行两个采集守护进程。

采集沿用上游计数器差分方式：一个采集间隔的流量归入该间隔起点所在的缓存。
如果采集间隔跨越账期边界，程序无法知道每个数据包在边界哪一侧，不会伪造
按比例拆分的精确数据。建议保持 `PollInterval 5`、`UpdateInterval 20`，避免
配置数分钟的采集间隔。`SaveInterval` 只控制写入数据库的频率，不是采集精度。

一分钟缓存仅在账期分钟不是 5 的倍数时启用，每次保存可能有更多小缓存记录，
但不会把持久化的五分钟表扩展成一分钟表，也不会改变数据保留期。

### 95 百分位统计

95 百分位仍使用上游五分钟历史样本，不生成伪造的一分钟样本。
账期若设为 `18:24`，首个完整样本从 `18:25` 开始；下个账期边界附近的不完整
五分钟样本同样排除。只有**完全落在账期内**的五分钟样本参与统计，避免跨账期
样本混入。月度总量仍按一分钟缓存分别汇总，不会因百分位排除样本而少计。
新账期开始后，若还没有完整五分钟样本，百分位查询可能暂时返回无可用数据。

### JSON 与 XML 输出

JSON 顶层追加 `monthrotate`、`monthrotatehour`、`monthrotateminute`、
`monthrotateaffectsyears` 和 `useutc`；XML 追加包含这些设置的 `billing` 元素。
原有流量字段及月度标签保留。这些字段表示**查询进程当前使用的配置**，不是
数据库中逐月保存的历史账期快照。解析程序应允许新增字段。

已修复 JSON/XML 字符串转义和小数地区设置问题。XML 百分位标签由非法的
`95th_percentile` 改为合法的 `percentile_95`，依赖旧拼写的程序需要调整。

### 构建这个 fork

Debian/Ubuntu 可从发行版仓库安装构建依赖：

```sh
sudo apt-get install build-essential autoconf automake pkg-config \
  libsqlite3-dev libgd-dev check
git clone https://github.com/in-valid-username/vnstat-tuned.git
cd vnstat-tuned
autoreconf -fi
./configure
make -j2
make check
```

验证通过后，可参考上方保留的上游安装与服务说明。部署前保留数据库和配置备份。
本项目目前没有发布修改版 Docker 镜像。

### 代码审查与验证

已按模块审查手写 C 源码、头文件、测试、示例程序及构建/服务定义；不宣称对
自动生成的 Autotools 文件逐行审计。审查和测试能降低风险，**不能证明绝无 bug**。

修复记录、上游修复来源、验证方法及剩余限制见[审查记录](docs/fork-review.md)。
新增测试覆盖全部 60 个合法分钟值、账期前后、年界、闰年、时区、夏令时、
真实采集缓存、汇总不丢失、不重复、导入标签和估算。

使用 Python 3 在独立构建目录中验证：

```sh
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-gcc
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-clang --compiler clang
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-sanitized --compiler clang --sanitize
python3 tests/example_security.py
```

示例测试还需要 Perl、PHP 及 ctype。上游测试夹具有意保留部分分配对象或结束
子进程，因此测试运行器关闭泄漏检测，但内存访问和未定义行为检查仍开启。
不同编译器或选项请使用不同构建目录。公开测试仅含合成数据和通用配置。

输出解析测试需要 Python 3；覆盖小数逗号时还需生成 `de_DE.UTF-8` 等地区设置：

```sh
python3 tests/output_parse_tests.py /tmp/vnstat-tuned-gcc/vnstat --comma-locale de_DE.UTF-8
```

真实守护进程验证应在**隔离的 Linux 虚拟机内**以 root 运行，需要
iproute2/util-linux，以及用于兼容性对照的未修改 v2.13 构建：

```sh
sudo unshare --net python3 tests/daemon_smoke.py /tmp/vnstat-tuned-gcc \
  --upstream-build /tmp/upstream-v2.13 --evidence /tmp/billing-smoke
```

该测试拒绝宿主网络命名空间，仅生成有界的合成流量。查询 UTC 数据时，建议
查询工具使用 `TZ=UTC`，减少上游日历时间表示在夏令时附近的歧义。
历史时区及特殊夏令时边界的限制详见审查记录，不承诺恢复所有历史偏移规则。

部分 Linux/WSL 与旧版 Clang sanitizer 组合可能在启动时出现地址布局冲突，
这个问题也能在独立简单程序中复现。隔离验证构建可使用 `--sanitize --no-pie`，
只对该测试构建关闭 PIE，ASan/UBSan 仍开启，不影响正常生产构建。
