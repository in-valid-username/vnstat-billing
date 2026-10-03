#!/usr/bin/env python3
"""Run with Python 3, Perl and PHP on Unix; only synthetic temporary data is used."""

import base64
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


EXAMPLES = Path(os.environ.get("EXAMPLE_DIR", Path(__file__).resolve().parents[1] / "examples"))
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a"
    "S1sAAAAASUVORK5CYII="
) + bytes(1100)
STUB = r'''
import base64
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if "--dbiflist" in args:
    print("\n".join(json.loads(os.environ["STUB_INTERFACES"])))
elif os.environ.get("STUB_FAIL") == "1":
    sys.exit(1)
elif "-o" in args:
    data = base64.b64decode(os.environ["STUB_PNG"])
    output = args[args.index("-o") + 1]
    if output == "-":
        sys.stdout.buffer.write(data)
    else:
        Path(output).write_bytes(data)
else:
    print(json.dumps({"args": args}))
'''


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))


class ExampleSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.perl = shutil.which(os.environ.get("EXAMPLE_PERL", "perl"))
        cls.php = shutil.which(os.environ.get("EXAMPLE_PHP", "php"))
        if not cls.perl or not cls.php:
            raise RuntimeError("Perl and PHP (with ctype) are required; set EXAMPLE_PERL/EXAMPLE_PHP.")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vnstat-example-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.log = self.root / "commands.jsonl"
        self.command = self.root / "fake-vnstat"
        self.command.write_text("#!" + sys.executable + "\n" + STUB, encoding="utf-8")
        self.command.chmod(0o755)
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "STUB_LOG": str(self.log),
            "STUB_INTERFACES": json.dumps(["eth0", "eth1"]),
            "STUB_PNG": base64.b64encode(PNG).decode("ascii"),
            "QUERY_STRING": "",
            "SCRIPT_NAME": "/vnstat.cgi",
        }

    def script(self, name, cache=False):
        source = (EXAMPLES / name).read_text(encoding="utf-8")
        source = source.replace("'/usr/bin/vnstat'", repr(str(self.command)))
        source = source.replace("'/usr/bin/vnstati'", repr(str(self.command)))
        source = source.replace('"/usr/bin/vnstat"', '"' + str(self.command) + '"')
        source = source.replace("my $servername = '';", "my $servername = 'server & <node> \"quoted\"';")
        source = source.replace("'/tmp/vnstatcgi'", repr(str(self.cache)))
        if cache:
            source = source.replace("my $cachetime = '0';", "my $cachetime = '1';")
        target = self.root / name
        target.write_text(source, encoding="utf-8")
        return target

    def run_script(self, name, query="", path=None, cache=False):
        self.env["QUERY_STRING"] = query
        if path is not None:
            self.env["PATH_INFO"] = path
        target = self.script(name, cache=cache)
        if name.endswith(".php"):
            harness = "parse_str(getenv('QUERY_STRING'), $_GET); include $argv[1];"
            args = [self.php, "-r", harness, str(target)]
        else:
            args = [self.perl, str(target)]
        return subprocess.run(args, cwd=self.root, env=self.env, capture_output=True, timeout=10)

    def commands(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_safe_html(self, data):
        parser = Tags()
        parser.feed(data.decode("utf-8"))
        for tag, attrs in parser.tags:
            self.assertNotIn(tag, ("script", "svg"))
            self.assertFalse(any(key.startswith("on") for key, _ in attrs), attrs)

    def assert_no_image_command(self):
        self.assertFalse(any("-o" in args for args in self.commands()))

    def assert_plain_response(self, result):
        self.assertTrue(b"text/plain" in result.stdout, result.stdout[:150])

    def test_image_interface_is_not_shell_code(self):
        interface = "$(touch${IFS}p)"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        result = self.run_script("vnstat.cgi", "0-s")
        self.assertFalse((self.root / "p").exists(), "interface executed shell code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1][1], interface)

    def test_json_interface_is_not_shell_code(self):
        interface = "$(touch${IFS}p)"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        result = self.run_script("vnstat-json.cgi", "interface=0")
        self.assertFalse((self.root / "p").exists(), "interface executed shell code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1], ["--json", "-i", interface])

    def test_json_path_interface_is_literal(self):
        interface = "eth;touch${IFS}p"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        result = self.run_script("vnstat-json.cgi", path="/" + interface)
        self.assertFalse((self.root / "p").exists(), "PATH_INFO interface executed shell code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1], ["--json", "-i", interface])

    def test_php_interface_is_not_shell_code(self):
        interface = "$(touch${IFS}p)"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        result = self.run_script("vnstat-json.php", "interface=0")
        self.assertFalse((self.root / "p").exists(), "interface executed shell code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1], ["--json", "-i", interface])

    def test_php_quotes_are_literal(self):
        interface = "eth'\";touch${IFS}p"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        result = self.run_script("vnstat-json.php", "interface=0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1], ["--json", "-i", interface])
        self.assertFalse((self.root / "p").exists())

    def test_php_padded_index_selects_same_interface(self):
        result = self.run_script("vnstat-json.php", "interface=0001")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands()[-1], ["--json", "-i", "eth1"])

    def test_perl_interface_quotes_are_literal(self):
        interface = "eth'\";touch${IFS}p"
        self.env["STUB_INTERFACES"] = json.dumps([interface])
        for name, query in (("vnstat.cgi", "0-s"), ("vnstat-json.cgi", "interface=0")):
            with self.subTest(name=name):
                result = self.run_script(name, query)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = self.commands()[-1]
                self.assertEqual(args[args.index("-i") + 1], interface)
                self.assertFalse((self.root / "p").exists())

    def test_single_image_rejects_attribute_injection(self):
        result = self.run_script("vnstat.cgi", 's-0-d" onerror="alert(1)')
        self.assert_plain_response(result)
        self.assert_safe_html(result.stdout)
        self.assert_no_image_command()

    def test_single_image_rejects_newline_suffix(self):
        result = self.run_script("vnstat.cgi", 's-0-d\n"><script>alert(1)</script>')
        self.assert_plain_response(result)
        self.assert_no_image_command()

    def test_html_escapes_names_and_script_path(self):
        interface = 'eth0"><script>alert(1)</script>'
        uri = '/vnstat.cgi/" onerror="alert(1)&x'
        self.env["STUB_INTERFACES"] = json.dumps([interface, "eth1"])
        self.env["REQUEST_URI"] = uri
        for query in ("", "0-f", "s-0-d-l"):
            with self.subTest(query=query):
                result = self.run_script("vnstat.cgi", query)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_safe_html(result.stdout)
                self.assertIn(html.escape(interface).encode(), result.stdout)
                self.assertIn(html.escape(uri).encode(), result.stdout)
                self.assertIn(b"server &amp; &lt;node&gt; &quot;quoted&quot;", result.stdout)

    def test_existing_image_modes_keep_arguments(self):
        modes = {
            "s": ["-s"], "hs": ["-hs"], "hsh": ["-hs", "0"], "hs5": ["-hs", "1"],
            "vs": ["-vs"], "vsh": ["-vs", "0"], "vs5": ["-vs", "1"],
            "d": ["-d", "30"], "d-l": ["-d", "60"], "m": ["-m", "12"],
            "m-l": ["-m", "24"], "t": ["-t", "10"], "t-l": ["-t", "20"],
            "h": ["-h", "48"], "hg": ["-hg"], "5": ["-5", "60"],
            "5g": ["-5g", "422", "250"], "y": ["-y", "5"], "y-l": ["-y", "0"],
            "95rx": ["--95th", "0"], "95tx": ["--95th", "1"], "95total": ["--95th", "2"],
        }
        for mode, args in modes.items():
            with self.subTest(mode=mode):
                result = self.run_script("vnstat.cgi", "0-" + mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.split(b"\n\n", 1)[1], PNG)
                self.assertEqual(self.commands()[-1], ["-i", "eth0", "-c", "0"] + args +
                                 ["--small", "--invert-colors", "0", "-o", "-"])

    def test_json_all_and_selected_interfaces(self):
        for name in ("vnstat-json.cgi", "vnstat-json.php"):
            for query, args in (("", ["--json"]), ("interface=1", ["--json", "-i", "eth1"])):
                with self.subTest(name=name, query=query):
                    result = self.run_script(name, query)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.commands()[-1], args)

    def test_single_image_pages_keep_supported_modes(self):
        for mode in ("5g", "5", "hsh", "hs5", "hs", "hg", "h", "d-l", "d", "m-l", "m", "y-l", "y", "t-l", "t"):
            with self.subTest(mode=mode):
                result = self.run_script("vnstat.cgi", "s-0-" + mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b"Content-Type: text/html", result.stdout)
                self.assertIn(('src="vnstat.cgi?0-' + mode + '"').encode(), result.stdout)
                self.assert_safe_html(result.stdout)

    def test_cached_image_creates_private_directory(self):
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o700)
        self.assertEqual(result.stdout.split(b"\n\n", 1)[1], PNG)

    def test_cache_directory_symlink_cannot_redirect_writes(self):
        other = self.root / "other"
        other.mkdir()
        self.cache.symlink_to(other, target_is_directory=True)
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assertEqual(list(other.iterdir()), [])
        self.assert_no_image_command()
        self.assert_plain_response(result)

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "foreign ownership requires root")
    def test_foreign_owned_cache_cannot_redirect_writes(self):
        self.cache.mkdir()
        os.chown(self.cache, 65534, 65534)
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assert_no_image_command()
        self.assert_plain_response(result)

    def test_writable_cache_directory_is_rejected(self):
        self.cache.mkdir()
        self.cache.chmod(0o777)
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assert_no_image_command()
        self.assert_plain_response(result)

    def test_cache_file_symlink_cannot_overwrite_target(self):
        self.cache.mkdir(mode=0o700)
        victim = self.root / "victim"
        victim.write_bytes(b"unchanged")
        (self.cache / "vnstat_0.png").symlink_to(victim)
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assertEqual(victim.read_bytes(), b"unchanged")
        self.assert_no_image_command()
        self.assert_plain_response(result)

    def test_cache_file_hardlink_cannot_overwrite_target(self):
        self.cache.mkdir(mode=0o700)
        victim = self.root / "victim"
        victim.write_bytes(b"unchanged")
        os.link(victim, self.cache / "vnstat_0.png")
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assertEqual(victim.read_bytes(), b"unchanged")
        self.assert_no_image_command()
        self.assert_plain_response(result)

    def test_old_private_cache_directory_is_tightened(self):
        self.cache.mkdir(mode=0o755)
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o700)
        self.assertEqual(result.stdout.split(b"\n\n", 1)[1], PNG)

    def test_failed_image_command_does_not_serve_old_cache(self):
        self.cache.mkdir(mode=0o700)
        (self.cache / "vnstat_0.png").write_bytes(PNG)
        self.env["STUB_FAIL"] = "1"
        result = self.run_script("vnstat.cgi", "0-s", cache=True)
        self.assert_plain_response(result)
        self.assertNotIn(PNG, result.stdout)


if __name__ == "__main__":
    if os.name != "posix":
        sys.exit("These CGI security tests require Unix process and filesystem semantics.")
    unittest.main(verbosity=2)
