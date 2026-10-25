# oh-my-mirrorz

English | [简体中文](README.zh_CN.md)

A script for speed testing the Debian mirrors listed at
<https://www.debian.org/mirror/list-full>. It can optionally set the fastest
tested mirror in the local APT sources.

## Requirements

- `curl`
- Python 3.6 or newer
- `pkexec` and a running polkit authentication agent, only for `--set-mirror`

On Debian:

```bash
sudo apt install curl python3
```

## Usage

```bash
python3 oh-my-mirrorz.py
```

The script fetches the official Debian mirror list (currently about 340 mirrors
in 66 countries), downloads `ls-lR.gz` from each package mirror, and falls back
to `dists/stable/main/Contents-amd64.gz`. Downloads are discarded to
`/dev/null`, and the results are printed as a speed ranking. HTTP redirects are
followed.

Without `--set-mirror`, the script only reads the mirror list and performs
downloads; it does not modify the system.

### Options

```text
-4, --ipv4          IPv4 only when speed testing
-6, --ipv6          IPv6 only when speed testing
-t, --time {3,5,10,30,60}
                    Duration of each download attempt (default: 5)
-c, --country COUNTRY
                    Only test mirrors in COUNTRY (case-insensitive,
                    repeatable, e.g. China or "United States")
--list-countries    Print available country names with mirror counts and exit
--set-mirror        After testing, set the fastest mirror in APT sources
                    (uses pkexec; only Debian archive entries)
```

### Country filter

```bash
python3 oh-my-mirrorz.py -c China
python3 oh-my-mirrorz.py -c "United States" -t 10
python3 oh-my-mirrorz.py -c China -c "Hong Kong" -4
python3 oh-my-mirrorz.py --list-countries
```

Country names must match the names printed by `--list-countries` (case does
not matter), so `-c US` is not valid; use `-c "United States"`. Quote names
containing spaces.

Testing every mirror can take a while; press `Ctrl+C` to stop.

## Set the fastest mirror

```bash
python3 oh-my-mirrorz.py -c China --set-mirror
```

After the speed test, the fastest successful mirror is selected and `pkexec`
asks for administrator authentication. If authorization is cancelled, no files
are changed. If no mirror passes the test, no privilege prompt is shown and the
sources are left unchanged.

Both APT source formats are detected:

- deb822: `/etc/apt/sources.list.d/*.sources`
- one-line: `/etc/apt/sources.list` and `/etc/apt/sources.list.d/*.list`

Only Debian archive entries are changed: the URI path must end in `/debian`
and the entry must be hosted under `debian.org` or signed with the Debian
archive keyring. `/debian-security` entries and third-party repositories are
left untouched. `deb` and `deb-src` entries are both updated.

Each modified file is backed up as `<file>.bak.YYYYMMDDHHMMSS` before the new
content is written. If a later file cannot be written, files already changed in
that run are restored from their backups.

The fastest mirror is used over HTTPS when it supports HTTPS. Existing HTTPS
entries are never downgraded to HTTP; if the fastest mirror has no verified
HTTPS support, those entries are skipped. If the script is already running as
root, it writes the files directly instead of calling `pkexec`.

The script does not run `apt update`. Refresh the package lists afterwards:

```bash
sudo apt update
```

## Troubleshooting

`HTTP Code 0` means `curl` did not receive an HTTP response: DNS failure, no
working IPv6 route, a proxy problem, or a timeout. It does not mean the test
file is missing. Try again without `-6` (or with `-4`), and check
`http_proxy` / `https_proxy`.

`HTTP Code 404` or `403` means the server responded but the test file is
unavailable. The script requires each mirror to serve `ls-lR.gz` or
`dists/stable/main/Contents-amd64.gz`; when both fail, the mirror is ranked at
`0 B/s`.

If `--set-mirror` reports that no Debian archive entries were found, the source
entries were not recognized as Debian archives. Check the URI path (`/debian`)
and the `Signed-By` / `signed-by` setting.

## Proxy

The mirror list is fetched with Python `urllib.request`, while the actual
downloads use `curl`. Set `HTTP_PROXY` / `HTTPS_PROXY` for the former, and
lowercase `http_proxy` / `https_proxy` for the latter. Setting both cases
covers both:

```bash
export http_proxy=http://127.0.0.1:8080
export https_proxy=http://127.0.0.1:8080
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
```
