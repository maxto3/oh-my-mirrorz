# oh-my-mirrorz

[English](README.md) | 简体中文

用于测试 <https://www.debian.org/mirror/list-full> 中 Debian 镜像站速度的脚本，
也可以选择把测速最快的镜像写入本机 APT 软件源。

## 运行要求

- `curl`
- Python 3.6 或更高版本
- `pkexec` 和正在运行的 polkit 认证代理，仅在使用 `--set-mirror` 时需要

在 Debian 上安装依赖：

```bash
sudo apt install curl python3
```

## 使用方法

```bash
python3 oh-my-mirrorz.py
```

脚本会获取 Debian 官方镜像列表（当前约 340 个镜像、66 个国家），从每个软件包
镜像下载 `ls-lR.gz`，失败时回退到
`dists/stable/main/Contents-amd64.gz`。下载内容直接丢弃到 `/dev/null`，
最终输出速度排名。脚本会跟随 HTTP 重定向。

不使用 `--set-mirror` 时，脚本只读取镜像列表并执行下载，不会修改系统。

### 选项

```text
-4, --ipv4          测速时仅使用 IPv4
-6, --ipv6          测速时仅使用 IPv6
-t, --time {3,5,10,30,60}
                    每次下载尝试的时长（默认：5 秒）
-c, --country COUNTRY
                    仅测试 COUNTRY 中的镜像（大小写不敏感，可重复指定，
                    例如 China 或 "United States"）
--list-countries    打印可用国家及各国镜像数量后退出
--set-mirror        测试完成后把最快镜像写入 APT 源
                    （使用 pkexec；仅修改 Debian 归档条目）
```

### 国家过滤

```bash
python3 oh-my-mirrorz.py -c China
python3 oh-my-mirrorz.py -c "United States" -t 10
python3 oh-my-mirrorz.py -c China -c "Hong Kong" -4
python3 oh-my-mirrorz.py --list-countries
```

国家名必须与 `--list-countries` 打印的名称一致（大小写不敏感），因此
`-c US` 无效，应使用 `-c "United States"`。名称包含空格时请加引号。

测试全部镜像可能需要较长时间，可按 `Ctrl+C` 停止。

## 设置最快镜像

```bash
python3 oh-my-mirrorz.py -c China --set-mirror
```

测速完成后，脚本会选择测速成功且速度最快的镜像，并通过 `pkexec` 请求管理员
授权。取消授权不会修改任何文件。如果没有镜像通过测速，脚本不会弹出提权提示，
也不会修改软件源。

脚本会自动识别两种 APT 源格式：

- deb822：`/etc/apt/sources.list.d/*.sources`
- 单行格式：`/etc/apt/sources.list` 和 `/etc/apt/sources.list.d/*.list`

只会修改 Debian 归档条目：URI 路径必须以 `/debian` 结尾，并且条目位于
`debian.org` 下或由 Debian 归档密钥环签名。`/debian-security` 条目和第三方
软件源保持不变。`deb` 与 `deb-src` 条目都会更新。

每个被修改的文件都会在写入前备份为
`<文件名>.bak.YYYYMMDDHHMMSS`。如果后续文件写入失败，本次运行中已经修改的
文件会从备份恢复。

最快镜像支持 HTTPS 时会使用 HTTPS。现有 HTTPS 条目绝不会降级为 HTTP；
如果最快镜像没有经过验证的 HTTPS 支持，这些条目会被跳过。如果脚本本身以
root 运行，则直接写入文件，不调用 `pkexec`。

脚本不会自动运行 `apt update`。之后请刷新软件包列表：

```bash
sudo apt update
```

## 故障排查

`HTTP Code 0` 表示 `curl` 没有收到 HTTP 响应：DNS 失败、没有可用的 IPv6
路由、代理问题或超时。它不代表测试文件不存在。请去掉 `-6`（或改用 `-4`）
重试，并检查 `http_proxy` / `https_proxy`。

`HTTP Code 404` 或 `403` 表示服务器有响应，但测试文件不可用。脚本要求每个
镜像至少提供 `ls-lR.gz` 或 `dists/stable/main/Contents-amd64.gz`；两者都
失败时，该镜像以 `0 B/s` 排在末尾。

如果 `--set-mirror` 提示找不到 Debian 归档条目，说明源条目未被识别为 Debian
归档。请检查 URI 路径（`/debian`）以及 `Signed-By` / `signed-by` 设置。

## 代理

镜像列表通过 Python `urllib.request` 获取，实际下载使用 `curl`。前者读取
大写的 `HTTP_PROXY` / `HTTPS_PROXY`，后者读取小写的 `http_proxy` /
`https_proxy`。同时设置两种写法即可覆盖：

```bash
export http_proxy=http://127.0.0.1:8080
export https_proxy=http://127.0.0.1:8080
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
```
