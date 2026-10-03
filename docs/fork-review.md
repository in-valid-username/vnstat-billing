# Billing fork: scope, review and validation

## Baseline and design

The implementation starts from upstream stable v2.13, commit
`a77ace6e24028f22ec7213000daedfd5c7a9d70f`. The original fork's development
snapshot remains on `master`; this is not a rewritten upstream history.
See the [upstream release](https://github.com/vergoh/vnstat/releases/tag/v2.13).

Monthly cutoffs use the existing day setting plus an hour and a minute on the
five-minute grid. This matches the existing collection buckets and avoids a
new database schema or a second accounting daemon. Defaults reproduce the
existing midnight cutoff. Yearly rotation remains opt-in. Imports retain their
original labels; changing settings does not reassign old traffic.

Not changed: kernel counter collection, bucket resolution, byte units, retention
defaults, interface discovery, binaries, service installation or licensing.
The fork does not implement provider billing, packet capture, quotas, a website
or remote control. No production systems were modified during development.

## Review coverage

All authored `src/*.c` and `src/*.h`, the C test modules and headers, example
CGI/PHP scripts, configuration, authored build definitions and service templates
were read across the main review and two completed independent review areas.
The main review covered acquisition, interface detection, cache, daemon,
database, configuration and billing changes. Independent reviews covered
output/merge/image/percentile code and examples/build/service integration.
Generated Autotools output and external dependencies are not claimed as
individually audited. Documentation was checked for the modified contracts.

Reading all code is not formal verification. Tests cover specified cases, not
every possible operating system, corrupt input or historical timezone rule.
Findings below distinguish demonstrated defects from defensive hardening.

## Findings and changes

| Area | Observation in v2.13 | Change / regression evidence |
| --- | --- | --- |
| Metadata SQL | `db_setinfo` has a 128-byte array but passes 512 to the insert formatter; sufficiently long metadata overruns it | Allocate SQLite-formatted SQL dynamically; long metadata insert/update test |
| Daemon UTC cache | Database calendar timestamps are reused as actual epochs; `UseUTC 1` with a non-UTC process timezone can delay collection or discard an initial interval | Separate real-epoch daemon lookup from the retained CLI calendar contract; winter/summer, UTC, UTC+8 and New York tests |
| SQL hardening | Retention query passes 512 for a 256-byte array | Use the actual array size; no separate exploitability claim |
| Merge failure | A failed source lookup rolls back using the wrong active database handle | Select destination before rollback; failure-path regression |
| Hourly graph | Unit padding exceeds a row's bounds; a long disabled interface title can append beyond its buffer | Backport upstream unit-padding repair and bound the title append; unit-mode/long-title regressions |
| Image rates | Zero/subunit rates can become zero denominators | Guard denominators without hiding nonzero rates; image regressions |
| Percentile | Legacy range end is inclusive and can include the next month's first slot; fixed maximum assumes a DST-free 31-day month | Exact billing start and last five-minute slot, actual sample expectation; boundary/DST regressions |
| JSON/XML averages | Percentile total average has missing parentheses | Divide combined RX+TX by the complete sampled duration |
| XML output | `<95th_percentile>` is not a legal XML element name | Emit `<percentile_95>`; consumers using text matching must update |
| Output escaping | Interface/alias text is inserted without JSON/XML escaping | Escape delimiters and controls; XML 1.0 forbidden ASCII controls become U+FFFD |
| JSON locales | Decimal-comma locales produce invalid JSON percentages | Serialize numeric fractions with a decimal point; decimal-comma parser tests |
| Example CGI | Shell-command interpolation and HTML/cache handling have proven unsafe paths | Argument-list execution, escaping and cache validation; 21 example security regressions |
| Test harness | Returning a raw failed-test count can wrap to a successful process exit status | Return `EXIT_FAILURE` for any nonzero failure count |
| Source package | Markdown documentation copy rules assume an in-tree build | Use `srcdir`, explicit dependencies and include Markdown/test documentation in distribution |

Example hardening follows upstream fixes, including commits
`2098360`, `1158c9b`, `5f49455`, `994d323` and `978d8d9`.
The hourly graph repair follows upstream commit `e6d6260`.
These are targeted repairs, not a wholesale import of the unreleased tree.

## Local virtual-machine validation

An isolated WSL2 virtual machine running Ubuntu 22.04 was created from an
official Ubuntu WSL image. It was not an existing user distro or a production
VPS. Toolchain: GCC 11.4, Clang 14, SQLite 3.37.2, GD 2.3, Perl 5.34 and PHP 8.1.
The original v2.13 suite passed all 589 checks before comparison.

Local results on 2026-10-04:

| Validation | Result |
| --- | --- |
| GCC full C suite | 642 checks, 0 failures, 0 errors; UTC and UTC+8 |
| Clang full C suite | 642 checks, 0 failures, 0 errors |
| Clang AddressSanitizer + UndefinedBehaviorSanitizer | 642 checks, 0 failures, 0 errors; no sanitizer diagnostics |
| Real daemon compatibility smoke | RX/TX increase after reload and restart; original CLI totals match |
| Database checks in smoke test | Schema unchanged; integrity check `ok` |
| Smoke output | JSON/XML parse successfully; valid nonempty summary PNG |
| JSON/XML regression parser | 10 tests passed, including decimal-comma locale; no skips |
| CGI/PHP example regression suite | 21 tests passed |
| Source package `make distcheck` | Build/check/install/uninstall passed |

Fork validation is reproducible with:

```sh
python3 tests/run_fork_checks.py /tmp/billing-gcc
python3 tests/run_fork_checks.py /tmp/billing-clang --compiler clang
python3 tests/run_fork_checks.py /tmp/billing-sanitized --compiler clang --sanitize --no-pie
python3 tests/output_parse_tests.py /tmp/billing-gcc/vnstat --comma-locale de_DE.UTF-8
python3 tests/example_security.py
sudo unshare --net python3 tests/daemon_smoke.py /tmp/billing-gcc \
  --upstream-build /tmp/upstream-v2.13 --evidence /tmp/billing-smoke
```

The smoke test refuses the host network namespace. It sends bounded UDP echo
traffic over an isolated veth pair, using an upstream-created database. It
checks collection, SIGHUP, graceful shutdown/restart, matching totals through
the original CLI, unchanged schema, SQLite integrity, JSON/XML parsing and PNG
output. It does not change the VM clock. Synthetic C tests exercise cutoff
boundaries, leap years, local DST, UTC, import labels and partial periods.

The historical Singapore regression compares sample dates with the existing
database getter's contract rather than hardcoding Unix epochs. SQLite versions
on Ubuntu 22.04, Ubuntu 24.04 and macOS differ in their handling of Singapore's
1970 UTC+7:30 offset. The test still requires the correct January billing start,
sample count, coverage and totals; modern cutoff tests retain exact expectations.

Sanitizer checks cover address/undefined behavior. Leak detection is disabled
because upstream test fixtures intentionally leave allocations or exit child
processes. This does not certify the absence of memory leaks in every path.

One PIE sanitizer run exited with SIGSEGV before test output on this WSL2
kernel/Clang 14 environment. An independent program containing only `puts`
reproduced empty-stderr startup failures (14 of 30 PIE runs), whereas the same
probe built without PIE passed 30 of 30. The full suite also passed on retry.
The Linux verification runner therefore offers opt-in `--no-pie` for sanitizer
builds; it does not change normal builds or disable address/UB checks. This
observation is an environment limitation, not a claim that SIGSEGV should
generally be ignored. Original failure logs are retained locally.

## Compatibility and operational limits

- Cutoffs accept days 1-28 and five-minute-aligned minutes only. No automatic
  rounding: choose the accepted approximation explicitly.
- The interval that straddles a cutoff still has upstream sampling uncertainty.
  Five-minute billing is not exact per-packet or provider-side billing.
- `UseUTC 0` uses process local time. Fixed UTC+8 should use `Asia/Singapore` in
  every service/query process. Browser timezone changes must not alter billing.
- For `UseUTC 1`, run query tools with `TZ=UTC` when practical. Upstream's
  pseudo-local calendar representation cannot fully preserve nonexistent or
  ambiguous DST times or all historical timezone offsets. The percentile
  billing window now reads raw month labels to avoid shifting into the wrong
  month, but historical sample timestamps retain the legacy getter contract.
  Modern fixed UTC+8 billing does not have that DST ambiguity.
- Changing the cutoff midway through a period can mix accounting conventions
  in the same monthly label. Back up and switch at a coordinated boundary.
- JSON billing fields and XML `billing` describe the query configuration,
  not historical per-row settings. The XML percentile tag correction is a
  deliberate output compatibility change.
- Zero-time monthly defaults and old database schema are retained. Reading
  totals with an old binary works, but old binaries do not understand the new
  hour/minute semantics. Do not alternate collecting daemons.
- Linux x86-64 was tested locally. BSD/macOS/32-bit runtime behavior is not
  independently verified here; existing upstream CI remains available.
- Historical summary averages that use the current year's leap-year state,
  extreme percentile limit multiplication, malformed UTF-8 aliases and legacy
  metrics/example presentation edge cases remain separate follow-up work.
  They are not claimed fixed by this billing change.

Public fixtures contain synthetic data only. Credentials, infrastructure
inventories and private route research are outside this repository.
