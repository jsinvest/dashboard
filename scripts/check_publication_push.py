"""Local pre-push gate: inspect committed bytes, not unrelated working files."""
import pathlib
import subprocess
import sys


def check(local, remote):
    source = subprocess.check_output(['git', 'show', local + ':scripts/publication_privacy.py'])
    module = {'__name__': 'privacy_gate', '__file__': 'publication_privacy.py'}
    exec(compile(source, 'publication_privacy.py', 'exec'), module)
    revision = remote + '..' + local if remote.strip('0') else local + '^!'
    emails = subprocess.check_output(['git', 'log', revision, '--format=%ae%n%ce']).decode().splitlines()
    if any(email and not email.lower().endswith('@users.noreply.github.com') for email in emails):
        raise ValueError('New commit metadata contains a non-private email. Use the GitHub noreply address.')
    rows = subprocess.check_output(['git', 'ls-tree', '-r', '-z', local]).decode().split('\0')
    process = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    found = []
    try:
        for row in rows:
            if not row:
                continue
            meta, name = row.split('\t', 1)
            if pathlib.PurePosixPath(name).suffix.lower() not in module['TEXT_SUFFIXES'] | {'.zip'}:
                continue
            oid = meta.split()[2]
            process.stdin.write((oid + '\n').encode()); process.stdin.flush()
            size = int(process.stdout.readline().split()[2])
            data = process.stdout.read(size); process.stdout.read(1)
            found.extend(module['leaks'](name, data))
    finally:
        process.stdin.close(); process.wait()
    if found:
        raise ValueError('Private source paths remain in committed public files: ' + ', '.join(found[:12]))


if __name__ == '__main__':
    try:
        for row in sys.stdin:
            fields = row.split()
            if len(fields) == 4 and fields[1].strip('0'):
                check(fields[1], fields[3])
        print('Publication privacy gate passed.')
    except Exception as error:
        print('Publication blocked: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
