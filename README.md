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

## vnstat-tuned fork

This section is appended to the original fork README. The upstream text above
is retained unchanged; its download, Docker and development commands install
**upstream vnStat**, not this fork. This fork is independent of upstream and
is based on the stable **v2.13** tag (`a77ace6e24028f22ec7213000daedfd5c7a9d70f`),
not the unreleased 2.14 development tree. In particular, the development
README's TrueType font reference does not describe this 2.13-based build.
The original development snapshot remains available on `master`.

### Scope

The fork adds a configurable monthly billing boundary with **five-minute
precision**, without changing the five-minute collection resolution or the
SQLite database schema. Kernel counters, interface monitoring, byte units,
retention, binary names and the GPL-2.0 license remain upstream-compatible.
It is not a hosting-provider billing API, a packet sniffer, a quota enforcer,
or a web dashboard. Provider accounting and kernel interface counters can
differ.

```ini
# Generic example: each billing month starts on day 7 at 18:25.
MonthRotate 7
MonthRotateHour 18
MonthRotateMinute 25
MonthRotateAffectsYears 0
UseUTC 0
```

- `MonthRotate`: 1 through 28, unchanged from upstream.
- `MonthRotateHour`: 0 through 23; default 0.
- `MonthRotateMinute`: 0, 5, 10, ..., 55; default 0.
- Invalid settings produce a configuration warning and revert to their
  defaults. A minute such as 24 is **not** rounded automatically; choose 25
  explicitly if that approximation is suitable.
- With `UseUTC 1`, the cutoff uses UTC. With `UseUTC 0`, it uses the daemon's
  local timezone. Use the **same config and timezone** for vnstatd, vnstat and
  vnstati. For fixed UTC+8 billing, use a non-DST timezone such as
  `Asia/Singapore`; browser timezones must not change accounting boundaries.
- Yearly totals remain calendar-based unless `MonthRotateAffectsYears 1`
  is selected. Then the annual cutoff is the same day/time in January.
- Existing monthly labels remain `YYYY-MM-01`. For example, a January label
  covers January 7 18:25 through February 7 18:25 in the example above.
  Existing databases need **no schema migration**. They are not retroactively
  rebilled when settings change. Back up the database, coordinate daemon and
  client configuration, and switch at a planned billing boundary.
- Sampling and delayed saves retain upstream behavior. A polling interval
  that straddles a boundary cannot be split into exact per-packet billing;
  neither five-minute alignment nor this fork eliminates that uncertainty.
- The cutoff also applies to monthly/yearly rates, period estimates and the
  current month's 95th-percentile sample window.

### Machine-readable output

JSON adds top-level `monthrotate`, `monthrotatehour`, `monthrotateminute`,
`monthrotateaffectsyears` and `useutc`. XML adds a `billing` element containing
the same settings. Existing traffic fields and date labels are preserved.
These are the **query process's current settings**, not stored per-period
configuration or historical billing evidence. Consumers should ignore
unknown additive fields and use calendar labels with the configured timezone.

### Build this fork

On Debian/Ubuntu, install build dependencies from the distribution repositories:

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

Follow the retained upstream installation and service instructions after
testing. Keep a database/config backup and avoid running two collecting
daemons against the same database. No modified Docker image is published here.

### Review and verification

The authored C sources, headers, tests, examples and build/service definitions
were divided into explicit review areas. Generated Autotools files are not
claimed as individually audited. Review and sanitizer tests reduce risk;
they do **not** establish that any program is bug-free.

See [the fork review record](docs/fork-review.md) for findings, provenance,
reproducers, validation results and residual limitations. New billing tests
exercise boundary inclusion, year rollover, leap years, timezones, DST,
configuration validation, legacy labels and estimates.

For an out-of-tree verification build with Python 3:

```sh
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-gcc
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-clang --compiler clang
python3 tests/run_fork_checks.py /tmp/vnstat-tuned-sanitized --compiler clang --sanitize
python3 tests/example_security.py
```

The last command also requires Perl and PHP with ctype. Sanitizer runs disable
leak detection because upstream tests intentionally exit or leave fixture
objects allocated; memory-access and undefined-behavior checks remain enabled.
Use new build directories for different compilers or flags. Public tests and
examples use synthetic interfaces and generic billing settings only.

Additional output tests require Python 3 and, for decimal-comma coverage, a
generated locale such as `de_DE.UTF-8`:

```sh
python3 tests/output_parse_tests.py /tmp/vnstat-tuned-gcc/vnstat --comma-locale de_DE.UTF-8
```

The XML percentile element is corrected from the invalid `95th_percentile`
to `percentile_95`. JSON/XML text escaping and numeric-locale handling are
also repaired; adapt consumers that relied on the invalid XML spelling.

The real-daemon smoke test requires root **inside an isolated Linux VM**,
iproute2/util-linux and an unmodified v2.13 build for compatibility checks:

```sh
sudo unshare --net python3 tests/daemon_smoke.py /tmp/vnstat-tuned-gcc \
  --upstream-build /tmp/upstream-v2.13 --evidence /tmp/billing-smoke
```

It refuses the host network namespace and uses only bounded synthetic traffic.
For UTC accounting, `TZ=UTC` is recommended for query tools to avoid legacy
calendar timestamp ambiguity around local daylight-saving transitions.

On Linux/WSL with older Clang sanitizer runtimes, a startup address-layout
conflict can occur even in an independent trivial program. For an isolated
verification build, `--sanitize --no-pie` keeps ASan/UBSan checks enabled while
disabling PIE only for that test build. It does not affect normal builds.
