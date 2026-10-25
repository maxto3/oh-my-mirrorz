#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: expandtab ts=4 sts=4 sw=4

import subprocess
import urllib.request
import urllib.parse
import re
import html
import os
import sys
import shutil
import tempfile
import time
import argparse

VERSION = ''
CURL_VERSION = ''
UA_URL = ''

DEBIAN_MIRROR_LIST = 'https://www.debian.org/mirror/list-full'
DEBIAN_TEST_FILES = (
    'ls-lR.gz',
    'dists/stable/main/Contents-amd64.gz',
)


def user_agent(product):
    return 'oh-my-mirrorz/%s (+https://github.com/mirrorz-org/oh-my-mirrorz) %s %s' % (VERSION, UA_URL, product)


def check_curl():
    global CURL_VERSION
    try:
        res = subprocess.run(['curl', '--version'], stdout=subprocess.PIPE)
        out = res.stdout.decode('utf-8')
        CURL_VERSION = out.split()[1]
        print(out)
        return 0
    except:
        print("No curl found!")
        return -1


def fetch_debian_mirrors():
    request = urllib.request.Request(DEBIAN_MIRROR_LIST, headers={
        'User-Agent': user_agent('urllib/' + urllib.request.__version__)
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode('utf-8', errors='replace')

    sections = re.split(r'<h3><a name="[A-Z]+">([^<]+)</a></h3>', page)
    mirrors = []
    seen = set()
    for country, body in zip(sections[1::2], sections[2::2]):
        for match in re.finditer(r'Packages over HTTP:\s*<tt><a[^>]*href="([^"]+)"', body):
            url = html.unescape(match.group(1))
            if url in seen:
                continue
            seen.add(url)
            mirrors.append({
                'country': html.unescape(country),
                'url': url,
            })
    return mirrors


def country_counts(mirrors):
    counts = {}
    for mirror in mirrors:
        counts[mirror['country']] = counts.get(mirror['country'], 0) + 1
    return counts


def select_mirrors(mirrors, countries):
    if not countries:
        return mirrors

    available = {mirror['country'].casefold(): mirror['country'] for mirror in mirrors}
    wanted = set()
    unknown = []
    for country in countries:
        key = country.strip().casefold()
        if key not in available:
            unknown.append(country)
            continue
        wanted.add(key)
    if unknown:
        raise ValueError(', '.join(unknown))
    return [mirror for mirror in mirrors if mirror['country'].casefold() in wanted]


def validate_mirror_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('invalid mirror URL: %s' % url)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('unsupported mirror URL: %s' % url)
    if '..' in parts.path.split('/'):
        raise ValueError('unsupported mirror URL: %s' % url)
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise ValueError('invalid character in mirror URL: %s' % url)
    return url


def is_debian_host(host):
    host = (host or '').lower()
    return host == 'debian.org' or host.endswith('.debian.org')


def is_debian_signed(text):
    return bool(re.search(r'(?im)^\s*Signed-By\s*:.*debian-archive-keyring', text))


def is_debian_archive_uri(uri, allow_custom_host=False):
    try:
        parts = urllib.parse.urlsplit(uri)
    except ValueError:
        return False
    if parts.username or parts.password or parts.query or parts.fragment:
        return False
    if not (allow_custom_host or is_debian_host(parts.hostname)):
        return False
    path = parts.path.rstrip('/')
    return parts.scheme in ('http', 'https') and (path == '/debian' or path.endswith('/debian'))


def replace_uri(uri, new_base):
    old = urllib.parse.urlsplit(uri)
    new = urllib.parse.urlsplit(new_base)
    if old.scheme == 'https' and new.scheme != 'https':
        return None
    path = new.path or '/'
    if old.path.endswith('/') and not path.endswith('/'):
        path += '/'
    elif not old.path.endswith('/') and path != '/' and path.endswith('/'):
        path = path[:-1]
    return urllib.parse.urlunsplit((new.scheme, new.netloc, path, '', ''))


def rewrite_uri_list(value, new_base, allow_custom_host=False):
    tokens = value.split()
    out = []
    changed = skipped = found = 0
    for token in tokens:
        if not is_debian_archive_uri(token, allow_custom_host):
            out.append(token)
            continue
        found += 1
        replaced = replace_uri(token, new_base)
        if replaced is None:
            skipped += 1
            out.append(token)
            continue
        if replaced != token:
            changed += 1
        out.append(replaced)
    prefix = ' ' if value[:1].isspace() else ''
    return prefix + ' '.join(out), changed, skipped, found


def split_eol(line):
    if line.endswith('\r\n'):
        return line[:-2], '\r\n'
    if line.endswith('\n'):
        return line[:-1], '\n'
    return line, ''


def rewrite_deb822_stanza(lines, new_base):
    allow_custom_host = is_debian_signed(''.join(lines))
    out = []
    changed = skipped = found = 0
    in_uris = False
    for line in lines:
        content, eol = split_eol(line)
        stripped = content.lstrip()
        if in_uris and content[:1] in (' ', '\t') and stripped and not stripped.startswith('#'):
            indent = content[:len(content) - len(stripped)]
            value, c, s, f = rewrite_uri_list(stripped, new_base, allow_custom_host)
            content = indent + value
            changed += c
            skipped += s
            found += f
        elif re.match(r'(?i)^\s*URIs\s*:', content):
            field, value = content.split(':', 1)
            new_value, c, s, f = rewrite_uri_list(value, new_base, allow_custom_host)
            content = field + ':' + new_value
            changed += c
            skipped += s
            found += f
            in_uris = True
        else:
            in_uris = False
        out.append(content + eol)
    return ''.join(out), changed, skipped, found


def rewrite_deb822(text, new_base):
    out = []
    changed = skipped = found = 0
    stanza = []
    for line in text.splitlines(keepends=True):
        if line.strip() == '':
            new_stanza, c, s, f = rewrite_deb822_stanza(stanza, new_base)
            out.append(new_stanza)
            out.append(line)
            changed += c
            skipped += s
            found += f
            stanza = []
        else:
            stanza.append(line)
    new_stanza, c, s, f = rewrite_deb822_stanza(stanza, new_base)
    out.append(new_stanza)
    changed += c
    skipped += s
    found += f
    return ''.join(out), changed, skipped, found


def rewrite_one_line(text, new_base):
    out = []
    changed = skipped = found = 0
    for line in text.splitlines(keepends=True):
        content, eol = split_eol(line)
        match = re.match(r'^(\s*)(deb(?:-src)?\s+(?:\[[^\]]*\]\s+)?)(\S+)(.*)$', content)
        line_allows_custom = 'debian-archive-keyring' in content
        if match and is_debian_archive_uri(match.group(3), line_allows_custom):
            found += 1
            replaced = replace_uri(match.group(3), new_base)
            if replaced is None:
                skipped += 1
            elif replaced != match.group(3):
                content = match.group(1) + match.group(2) + replaced + match.group(4)
                changed += 1
        out.append(content + eol)
    return ''.join(out), changed, skipped, found


def source_files(root='/'):
    apt = os.path.join(root, 'etc', 'apt')
    files = []
    legacy = os.path.join(apt, 'sources.list')
    if os.path.isfile(legacy):
        files.append(legacy)
    parts = os.path.join(apt, 'sources.list.d')
    if os.path.isdir(parts):
        for name in sorted(os.listdir(parts)):
            if name.endswith('.sources') or name.endswith('.list'):
                path = os.path.join(parts, name)
                if os.path.isfile(path):
                    files.append(path)
    return files


def write_source(path, content):
    directory = os.path.dirname(path)
    mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix='.oh-my-mirrorz-', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply_mirror(new_base, root='/'):
    try:
        validate_mirror_url(new_base)
    except ValueError as e:
        print('!', e)
        return 1

    try:
        files = source_files(root)
    except OSError as e:
        print('! Failed to list APT source files:', e)
        return 1
    if not files:
        print('! No APT source files found under', os.path.join(root, 'etc', 'apt'))
        return 1
    total_changed = total_skipped = total_found = 0
    updates = []
    for path in files:
        try:
            with open(path, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
                text = f.read()
        except OSError as e:
            print('! Failed to read', path, ':', e)
            return 1
        if path.endswith('.sources'):
            new_text, changed, skipped, found = rewrite_deb822(text, new_base)
        else:
            new_text, changed, skipped, found = rewrite_one_line(text, new_base)
        total_changed += changed
        total_skipped += skipped
        total_found += found
        if changed:
            updates.append((path, new_text, changed))

    if total_found == 0:
        print('! No Debian archive entries (URI path /debian) found in APT sources.')
        return 1
    if total_changed == 0:
        if total_skipped:
            print('! Refusing to downgrade %d HTTPS entries to HTTP; APT sources were not changed.' % total_skipped)
            return 1
        print('APT sources already use', new_base)
        return 0
    if total_skipped:
        print('! Skipped %d HTTPS entries because %s has no verified HTTPS support.' % (total_skipped, new_base))

    stamp = time.strftime('%Y%m%d%H%M%S')
    applied = []
    try:
        for path, content, count in updates:
            backup = '%s.bak.%s' % (path, stamp)
            suffix = 1
            while os.path.exists(backup):
                backup = '%s.bak.%s.%d' % (path, stamp, suffix)
                suffix += 1
            shutil.copy2(path, backup)
            write_source(path, content)
            applied.append((path, backup))
            print('Updated', path, '(%d entries)' % count)
            print('Backup:', backup)
    except OSError as e:
        print('! Failed to update APT sources:', e)
        for path, backup in reversed(applied):
            try:
                shutil.copy2(backup, path)
                print('Restored', path, 'from', backup)
            except OSError as restore_error:
                print('! Failed to restore', path, ':', restore_error)
        return 1

    print()
    print("Run 'sudo apt update' to refresh package lists.")
    return 0


def https_available(mirror_url, args):
    parts = urllib.parse.urlsplit(mirror_url)
    if parts.scheme == 'https':
        return True
    base = urllib.parse.urlunsplit(('https', parts.netloc, parts.path, '', ''))
    if not base.endswith('/'):
        base += '/'
    url = urllib.parse.urljoin(base, 'ls-lR.gz')
    opt = ['-q', '-s', '-L', '-o', os.devnull, '-m', '5', '-r', '0-0',
           '--max-filesize', '1048576', '-w', '%{http_code} %{url_effective}']
    if args.ipv4:
        opt.append('-4')
    elif args.ipv6:
        opt.append('-6')
    result = subprocess.run(['curl'] + opt + [
        '-A', user_agent('curl/%s' % CURL_VERSION), url], stdout=subprocess.PIPE)
    fields = result.stdout.decode('utf-8', errors='replace').split()
    if len(fields) != 2:
        return False
    return fields[0] in ('200', '206') and fields[1].startswith('https://')


def set_mirror(mirror_url, args):
    try:
        validate_mirror_url(mirror_url)
    except ValueError as e:
        print('!', e)
        return 1

    if not mirror_url.endswith('/'):
        mirror_url += '/'
    if https_available(mirror_url, args):
        parts = urllib.parse.urlsplit(mirror_url)
        mirror_url = urllib.parse.urlunsplit(('https', parts.netloc, parts.path, '', ''))
    print('Setting Debian archive mirror to:', mirror_url)

    if os.geteuid() == 0:
        return apply_mirror(mirror_url)

    pkexec = shutil.which('pkexec')
    if not pkexec:
        print('! pkexec not found; install polkit or run this script as root.')
        return 1
    python = sys.executable or shutil.which('python3')
    if not python:
        print('! Cannot find python3 to run with pkexec.')
        return 1
    script = os.path.realpath(__file__)
    print('Requesting root privileges with pkexec...')
    result = subprocess.run([pkexec, os.path.abspath(python), script, '--apply-mirror', mirror_url])
    if result.returncode == 126:
        print('! pkexec was cancelled or not authorized; APT sources were not changed.')
        return 1
    if result.returncode == 127:
        print('! pkexec could not run the helper; APT sources were not changed.')
        return 1
    if result.returncode != 0:
        print('! Failed to set the mirror (exit %d); APT sources were not changed.' % result.returncode)
        return 1
    return 0


def speed_test(url, args):
    opt = ['-q', '-s', '-S', '-L']
    if args.ipv4:
        opt.append('-4')
    elif args.ipv6:
        opt.append('-6')
    res = subprocess.run(['curl'] + opt + [
        '-o', os.devnull, '-w', '%{http_code} %{speed_download}',
        '-m' + str(args.time),
        '-A', user_agent('curl/%s' % CURL_VERSION), url], stdout=subprocess.PIPE)
    fields = res.stdout.decode('utf-8', errors='replace').split()
    if len(fields) != 2:
        return 0, 0.0
    return int(fields[0]), float(fields[1])


def human_readable_speed(speed):
    scale = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s']
    i = 0
    while (speed > 1024.0):
        i += 1
        speed /= 1024.0
    return f'{speed:.2f} {scale[i]}'


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-4", "--ipv4", help="IPv4 only when speed testing", action="store_true")
    group.add_argument("-6", "--ipv6", help="IPv6 only when speed testing", action="store_true")
    parser.add_argument("-t", "--time", type=int, default=5, choices=[3, 5, 10, 30, 60], help="Duration of each download attempt (default: %(default)d)")
    parser.add_argument("-c", "--country", action="append", metavar="COUNTRY", help="Only test mirrors in COUNTRY (case-insensitive, repeatable, e.g. China or 'United States'); see --list-countries")
    parser.add_argument("--list-countries", action="store_true", help="Print available country names with mirror counts and exit")
    parser.add_argument("--set-mirror", action="store_true", help="After testing, set the fastest mirror in APT sources (uses pkexec; only Debian archive entries)")
    parser.add_argument("--apply-mirror", metavar="URL", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.apply_mirror:
        if os.geteuid() != 0:
            print('! --apply-mirror must be run as root.')
            return 1
        return apply_mirror(args.apply_mirror)

    if not args.list_countries:
        if check_curl() != 0:
            return 1

    try:
        mirrors = fetch_debian_mirrors()
    except Exception as e:
        print('! Failed to load', DEBIAN_MIRROR_LIST, ':', e)
        return 1

    if not mirrors:
        print('! No Debian mirrors found in', DEBIAN_MIRROR_LIST)
        return 1

    if args.list_countries:
        counts = country_counts(mirrors)
        print('Available countries (case-insensitive, mirror count in parentheses):')
        for country in sorted(counts):
            print('  %s (%d)' % (country, counts[country]))
        return 0

    try:
        mirrors = select_mirrors(mirrors, args.country)
    except ValueError as e:
        print('! Unknown country:', e)
        print('Use --list-countries to see available countries.')
        return 1

    print('Loaded', len(mirrors), 'Debian mirrors from', DEBIAN_MIRROR_LIST)
    print() # one empty line to separate metadata and speedtest

    res = {}
    for mirror in mirrors:
        host = urllib.parse.urlsplit(mirror['url']).hostname or mirror['url']
        tested = False
        for path in DEBIAN_TEST_FILES:
            url = urllib.parse.urljoin(mirror['url'], path)
            print('Speed testing', host, url, '... ', end='', flush=True)
            code, speed = speed_test(url, args)
            if code == 200:
                print(human_readable_speed(speed))
                res[host] = {'url': mirror['url'], 'speed': speed}
                tested = True
                break
            print('HTTP Code', code, 'Speed', human_readable_speed(speed))
        if not tested:
            res[host] = {'url': mirror['url'], 'speed': 0}
            print('! All test files failed for', host, '(%s)' % mirror['country'])

    print() # one empty line to separate speedtest and result

    print('RANK', 'ABBR', 'SPEED', sep='\t\t')
    for i, (k, v) in enumerate(sorted(res.items(), key = lambda x: x[1]['speed'], reverse=True)):
        print(f'{i:02d}:', k, human_readable_speed(v['speed']), sep='\t\t')

    if args.set_mirror:
        print()
        successful = [(host, data) for host, data in res.items() if data['speed'] > 0]
        if not successful:
            print('! No mirror passed the speed test; APT sources were not changed.')
            return 1
        host, data = max(successful, key = lambda item: item[1]['speed'])
        print('Fastest mirror:', host, '(%s)' % human_readable_speed(data['speed']))
        return set_mirror(data['url'], args)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
