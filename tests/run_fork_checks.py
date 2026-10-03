#!/usr/bin/env python3
"""Build an out-of-tree test variant; run from the vnstat source directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--no-pie", action="store_true",
                        help="Linux sanitizer-only workaround for runtime startup conflicts")
    args = parser.parse_args()
    if args.no_pie and (not args.sanitize or not sys.platform.startswith("linux")):
        parser.error("--no-pie requires --sanitize on Linux")
    source = Path.cwd().resolve()
    build = args.build.resolve()
    build.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(CC=args.compiler, TZ="UTC", LC_ALL="C")
    flags = "-O2 -g -Wall -Wextra"
    if args.sanitize:
        flags = "-O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer"
        env["LDFLAGS"] = "-fsanitize=address,undefined"
        env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
        env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
        if args.no_pie:
            flags += " -fno-pie"
            env["LDFLAGS"] += " -no-pie"
    env["CFLAGS"] = flags
    with (build / "verification.log").open("w") as log:
        def run(command, cwd):
            log.write("$ " + " ".join(map(str, command)) + "\n")
            log.flush()
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                print((build / "verification.log").read_text()[-16000:])
                raise SystemExit(result.returncode)
        run(["autoreconf", "-fi"], source)
        run([str(source / "configure")], build)
        run(["make", "-j2"], build)
        run(["make", "check"], build)
    print((build / "test.log").read_text()[-2000:])
    print("Evidence: " + str(build / "verification.log"))


if __name__ == "__main__":
    main()
