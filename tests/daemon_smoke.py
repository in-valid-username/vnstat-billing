#!/usr/bin/env python3
"""Exercise real counters in an isolated Linux VM network namespace.

Run as root via unshare --net; never run directly on a production host.
Requires iproute2, util-linux, Python 3 and both fork/upstream build directories.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--upstream-build", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("root in an isolated VM network namespace is required")
    if Path("/proc/self/ns/net").readlink() == Path("/proc/1/ns/net").readlink():
        parser.error("refusing the host network namespace; use unshare --net")
    build, upstream = args.build.resolve(), args.upstream_build.resolve()
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TZ="America/New_York", LC_ALL="C")
    processes = []
    with tempfile.TemporaryDirectory(prefix="vnstat-smoke-") as tmp:
        root = Path(tmp)
        config, oldconfig = root / "vnstat.conf", root / "upstream.conf"
        base = (f'DatabaseDir "{root}"\nUseUTC 1\nUseLogging 0\n'
                'UpdateInterval 2\nPollInterval 2\nSaveInterval 1\n'
                'OfflineSaveInterval 1\nTimeSyncWait 0\nBandwidthDetection 0\n'
                'MaxBandwidth 1000\nMonthRotate 7\n')
        oldconfig.write_text(base)
        config.write_text(base + 'MonthRotateHour 18\nMonthRotateMinute 25\n')
        log = (evidence / "commands.log").open("w")

        def run(command, capture=False):
            log.write("$ " + " ".join(map(str, command)) + "\n")
            log.flush()
            return subprocess.run(list(map(str, command)), env=env, check=True,
                                  stdout=subprocess.PIPE if capture else log,
                                  stderr=log, timeout=30).stdout

        def cli(binary, cfg, *extra):
            return run([binary, "--config", cfg, "-i", "billing0", *extra], True)

        def stop(process):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

        def totals():
            with sqlite3.connect(root / "vnstat.db") as db:
                return db.execute("SELECT rxtotal, txtotal FROM interface WHERE name='billing0'").fetchone()

        def daemon():
            process = subprocess.Popen([str(build / "vnstatd"), "--config", str(config),
                                        "--nodaemon", "--noadd", "--noremove"],
                                       env=env, stdout=log, stderr=log)
            processes.append(process)
            time.sleep(4)
            if process.poll() is not None:
                raise RuntimeError("daemon exited before traffic collection")
            return process

        def traffic():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                for _ in range(300):
                    payload = b"v" * 1200
                    sock.sendto(payload, ("172.31.254.2", 59001))
                    answer, _ = sock.recvfrom(2048)
                    if answer != payload:
                        raise RuntimeError("unexpected UDP echo")
                    time.sleep(0.005)
            time.sleep(5)

        try:
            peer = subprocess.Popen(["unshare", "--net", "sleep", "180"], stdout=log, stderr=log)
            processes.append(peer)
            time.sleep(0.3)
            run(["ip", "link", "add", "billing0", "type", "veth", "peer", "name", "billing1"])
            run(["ip", "link", "set", "billing1", "netns", peer.pid])
            run(["ip", "addr", "add", "172.31.254.1/30", "dev", "billing0"])
            run(["ip", "link", "set", "billing0", "up"])
            run(["nsenter", "-t", peer.pid, "-n", "ip", "addr", "add", "172.31.254.2/30", "dev", "billing1"])
            run(["nsenter", "-t", peer.pid, "-n", "ip", "link", "set", "billing1", "up"])
            echo_code = ("import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
                         "s.bind(('172.31.254.2',59001))\nwhile True:\n"
                         " data,addr=s.recvfrom(2048)\n s.sendto(data,addr)\n")
            receiver = subprocess.Popen(["nsenter", "-t", str(peer.pid), "-n", "python3", "-c", echo_code],
                                        stdout=log, stderr=log)
            processes.append(receiver)
            run([upstream / "vnstatd", "--config", oldconfig, "--initdb", "--noadd"])
            cli(upstream / "vnstat", oldconfig, "--add")
            with sqlite3.connect(root / "vnstat.db") as db:
                schema_before = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
            before = totals()
            first = daemon()
            traffic()
            first.send_signal(signal.SIGHUP)
            time.sleep(3)
            traffic()
            stop(first)
            after_reload = totals()
            second = daemon()
            traffic()
            stop(second)
            after_restart = totals()
            if not all(b < a < r for b, a, r in zip(before, after_reload, after_restart)):
                raise AssertionError((before, after_reload, after_restart))
            if min(after_reload) < 700000 or min(after_restart) < 1050000:
                raise AssertionError("missing sampled traffic after reload/restart")
            data = json.loads(cli(build / "vnstat", config, "--json"))
            xml = cli(build / "vnstat", config, "--xml")
            ET.fromstring(xml)
            (evidence / "output.json").write_text(json.dumps(data, indent=2) + "\n")
            (evidence / "output.xml").write_bytes(xml)
            png = evidence / "summary.png"
            run([build / "vnstati", "--config", config, "-i", "billing0", "-s", "-o", png])
            if png.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" or png.stat().st_size < 500:
                raise AssertionError("invalid summary image")
            legacy = json.loads(cli(upstream / "vnstat", oldconfig, "--json"))
            if data["interfaces"][0]["traffic"]["total"] != legacy["interfaces"][0]["traffic"]["total"]:
                raise AssertionError("upstream cannot read matching totals")
            with sqlite3.connect(root / "vnstat.db") as db:
                schema_after = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
                integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            if schema_before != schema_after or integrity != "ok":
                raise AssertionError("database compatibility/integrity failure")
            results = dict(before=before, after_reload=after_reload, after_restart=after_restart,
                           schema_unchanged=True, integrity=integrity, upstream_totals_match=True,
                           json_parsed=True, xml_parsed=True, image_bytes=png.stat().st_size,
                           useutc=1, process_timezone=env["TZ"], network="isolated veth UDP echo")
            (evidence / "results.json").write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps(results, indent=2))
        finally:
            for process in reversed(processes):
                stop(process)
            log.close()


if __name__ == "__main__":
    main()
