# 部署层（singbox-ops）

`devconfig_gen` 是**纯函数引擎**：给一份 context，产出 server / client / links 配置字节，不碰网络、不写 `/etc`、不生成凭据。

同仓库的 `singbox_ops` 包负责另一半——所有副作用：

```text
singbox-ops（坞）
  ├── secrets     生成凭据 + 子域前缀
  ├── dns         Cloudflare A 记录
  ├── acme        acme.sh + Cloudflare DNS-01
  ├── state       可选 local JSON 备忘录
  ├── export      把产物写到目标路径
  └── runtime     packages / systemd / nftables-basic / warp watchdog
```

它通过**库调用**使用引擎，绝不注册为 Provider：

```python
from devconfig_gen.engine import generate_pipeline

result = generate_pipeline("singbox", context=assembled_context)
```

## 安装

```bash
pip install -e ".[yaml,ops]"
```

`ops` 额外依赖 `cryptography`，用于在没有 `sing-box` 二进制时生成 REALITY 密钥对。

## CLI

```bash
# 只组装 context（无副作用，方便审阅 / 手工修改）
singbox-ops context --plan examples/singbox-deploy.yaml --format yaml > context.yaml

# 干跑：打印每一步意图，不碰系统
singbox-ops deploy --plan examples/singbox-deploy.yaml --dry-run

# 真实部署
singbox-ops deploy --plan examples/singbox-deploy.yaml

# 重新生成凭据并重部署
singbox-ops redeploy --plan examples/singbox-deploy.yaml

# 反向清理：watchdog → firewall → systemd → DNS
singbox-ops destroy --plan examples/singbox-deploy.yaml
```

## Plan 参考

```yaml
domain_root: example.com        # 必填
server_ip: auto                 # auto | 显式 IPv4
protocols: [anytls, tuic, hysteria2]
tunnel_mode: proxy              # none | proxy | tun

subdomain_prefixes:             # 可选；缺省则每次部署随机生成
  reality: a1b2c3d4
  tuic: e5f6a7b8
  hy2: c9d0e1f2

adapters:
  secrets: singbox-subprocess   # singbox-subprocess | python-secrets | static
  dns: cloudflare
  acme: cloudflare-dns01
  state: local-json             # null 表示完全无状态
  runtime:
    packages: debian            # null 可关闭
    systemd: systemd
    firewall: nftables-basic
    watchdog: warp

outputs:
  server_config: /etc/sing-box/config.json
  client_config: /root/singbox-client.json
  links: /root/singbox-links.txt
```

`credentials_input` 指向一个 JSON/YAML 文件时，`secrets` 使用其中的
`credentials` / `subdomain_prefixes`（可复现部署）。

## 环境变量

| 变量 | 用途 |
|---|---|
| `CF_Token` | Cloudflare API Token（DNS + DNS-01） |
| `CF_Zone_ID` | Cloudflare Zone ID |

## 设计原则

- **零污染**：`singbox_ops` 与 `devconfig_gen` 命名空间隔离，引擎的零副作用契约不变。
- **适配器是普通类**：用 name → factory 字典映射，不用 setuptools entry points；全项目只有一套插件体系（Provider）。
- **可注入 Runner**：所有命令/文件操作走 `CommandRunner`；`--dry-run` 与测试都使用记录器，不碰真实系统。
- **幂等**：同一 plan 重复 deploy 不会重复创建 DNS 记录或证书。
- **对称生命周期**：每个 adapter 同时实现 `apply()` 与 `destroy()`。
- **密码不落 state**：state 只存非敏感元数据（记录 ID、前缀、输出路径）。

> **注意**：`sing-box` 服务端配置与证书包含敏感信息，请确保服务器权限正确
> （config `0600`、state `0600`、密钥 `0600`）。
