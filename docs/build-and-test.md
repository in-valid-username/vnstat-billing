# 构建和测试

从本仓库源码构建分钟级账期版本。上游下载包和 `vergoh/vnstat` 容器仍提供上游功能；本分支的来源见[基线说明](reference/baseline.md)。

## 编译与安装

Debian/Ubuntu 的依赖和构建命令见 [README](../README.md#快速开始)。`libgd-dev` 用于可选图片输出，`check` 用于 C 测试；其他系统依赖见 [INSTALL.md](../INSTALL.md) 和 [INSTALL_BSD.md](../INSTALL_BSD.md)。

先运行 `make check`，再按安装指南设置路径、配置和服务。已有安装先备份配置和数据库，停止旧守护进程后更换二进制。账期修改单独按[切换步骤](billing.md#升级与切换)进行。

源码包的 Markdown 清单由 [Makefile.am](../Makefile.am) 的 `EXTRA_DIST` 维护。`README` 是 `README.md` 的分发副本；安装、升级和卸载的无扩展名文件同样由对应 Markdown 生成。

## C 回归与 Sanitizer

[run_fork_checks.py](../tests/run_fork_checks.py) 在独立目录构建并测试。不同编译器和选项分别使用一个目录：

```sh
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-gcc
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-clang --compiler clang
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-sanitized --compiler clang --sanitize
```

运行器开启 AddressSanitizer 和 UndefinedBehaviorSanitizer。上游测试夹具保留部分分配对象或退出子进程，因此该运行器关闭泄漏检测。内存泄漏检查需另设能完成资源释放的测试条件。

WSL2/Clang 14 的部分 PIE Sanitizer 进程曾在测试启动前崩溃，复现条件见[失败记录](reports/2026-10-04-validation.md#sanitizer-启动失败)。该环境可给隔离测试构建添加 `--no-pie`；正常构建不受此选项影响。

## 输出与示例

JSON/XML 检查需要 Python 3；小数逗号测试还需生成相应 locale：

```sh
python3 tests/output_parse_tests.py /tmp/vnstat-tuned-gcc/vnstat --comma-locale de_DE.UTF-8
python3 tests/example_security.py
```

示例测试需要 Perl、PHP 及 ctype。解析行为见[输出说明](output.md)。

## 守护进程验证

在隔离的 Linux 虚拟机内以 root 运行，需要 iproute2、util-linux 和未修改的上游 v2.13 构建：

```sh
sudo unshare --net python3 tests/daemon_smoke.py /tmp/vnstat-tuned-gcc \
  --upstream-build /tmp/upstream-v2.13 --evidence /tmp/billing-smoke
```

[daemon_smoke.py](../tests/daemon_smoke.py) 拒绝宿主网络命名空间，在独立 veth 对上发送有界 UDP 回显流量。检查采集、重载、重启、原版 CLI 读取、数据库完整性、JSON/XML 和 PNG；测试不修改虚拟机时钟。

对应环境和结果保存在[验证报告](reports/2026-10-04-validation.md)。
