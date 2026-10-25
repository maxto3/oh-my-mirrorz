# oh-my-mirrorz

A script for speed testing the Debian mirrors listed at
<https://www.debian.org/mirror/list-full>. It can also set the fastest mirror
in the local APT sources.

## How to use

Make sure you have `curl` installed. Python 3.6 or newer is required. The
`--set-mirror` option also needs `pkexec` and a running polkit authentication
agent.

Run:

```
python3 oh-my-mirrorz.py
```

The script fetches the official Debian mirror list, downloads `ls-lR.gz` from
each package mirror (falling back to
`dists/stable/main/Contents-amd64.gz`), and prints a speed ranking. HTTP
redirects are followed.

Options:

```
-4, --ipv4          IPv4 only when speed testing
-6, --ipv6          IPv6 only when speed testing
-t, --time {3,5,10,30,60}
                    Duration of each download attempt (default: 5)
-c, --country COUNTRY
                    Only test mirrors in COUNTRY (case-insensitive, repeatable)
--list-countries    List available countries and exit
--set-mirror        Set the fastest tested mirror in APT sources (uses pkexec)
```

Examples:

```
python3 oh-my-mirrorz.py -c China
python3 oh-my-mirrorz.py -c "United States" -t 10
python3 oh-my-mirrorz.py -c China -c "Hong Kong" -4
python3 oh-my-mirrorz.py --list-countries
python3 oh-my-mirrorz.py -c China --set-mirror
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
are changed. Both APT source formats are detected:

- deb822: `/etc/apt/sources.list.d/*.sources`
- one-line: `/etc/apt/sources.list` and `/etc/apt/sources.list.d/*.list`

Only Debian archive entries are changed: the URI path must end in `/debian`
and the entry must be hosted under `debian.org` or signed with the Debian
archive keyring. `/debian-security` entries and third-party repositories are
left untouched. Each modified file is backed up as
`<file>.bak.YYYYMMDDHHMMSS`.

The fastest mirror is used over HTTPS when it supports HTTPS. Existing HTTPS
entries are never downgraded to HTTP; if the fastest mirror has no verified
HTTPS support, those entries are skipped. If the script is already running as
root, it writes the files directly instead of calling `pkexec`.

Refresh the package lists afterwards:

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

## Proxy

The mirror list is fetched with Python `urllib.request`, while the actual
downloads use `curl`. Set `HTTP_PROXY` / `HTTPS_PROXY` for the former, and
lowercase `http_proxy` / `https_proxy` for the latter. Setting both cases
covers both:

```
export http_proxy=http://127.0.0.1:8080
export https_proxy=http://127.0.0.1:8080
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
```
