#!/usr/bin/env python3
"""Publish this catalog using an account-free Cloudflare Quick Tunnel."""

import os
from pathlib import Path
import re
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.runtime/public-preview'
ORIGIN = STATE / 'origin.txt'
URL = STATE / 'url.txt'


def main():
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True)
    ORIGIN.unlink(missing_ok=True)
    URL.unlink(missing_ok=True)
    binary = Path(os.environ.get('CLOUDFLARED_BIN', str(Path.home() / '.local/bin/cloudflared')))
    if not binary.is_file():
        raise SystemExit('Install official cloudflared in ~/.local/bin or set CLOUDFLARED_BIN.')
    process = subprocess.Popen([
        str(binary), 'tunnel', '--no-autoupdate', '--protocol', 'http2',
        '--url', 'http://127.0.0.1:34402',
        '--http-host-header', 'public-preview.invalid',
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def stop(_signum, _frame):
        process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for line in process.stdout:
            print(line.rstrip(), flush=True)
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b', line)
            if match:
                origin = match.group(0)
                temporary = STATE / 'origin.tmp'
                temporary.write_text(origin + '\n')
                temporary.replace(ORIGIN)
                URL.write_text(origin + '/kit-catalog/\n')
                print('Catalog public URL: ' + origin + '/kit-catalog/', flush=True)
        return process.wait()
    finally:
        ORIGIN.unlink(missing_ok=True)
        URL.unlink(missing_ok=True)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    sys.exit(main())
