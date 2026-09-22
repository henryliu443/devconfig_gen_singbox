# devconfig_gen_singbox

> **A sing-box domain implementation built on top of DevConfig-Gen.**
> **构建在 `DevConfig-Gen` 之上的 sing-box 领域实现（child / fork）。**

[![Version](https://img.shields.io/badge/version-2.1.2-blue.svg)](CHANGELOG.md)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-136%20passing-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey.svg)

**`DevConfig-Gen` 是一个以有限领域 Scope 为边界的确定性配置转换引擎。**
**DevConfig-Gen is a deterministic configuration transformation engine built around bounded domain scopes.**

本仓库定义其中一个 scope：有限的 **`singbox` 领域** —— 它的领域模型、校验规则、
协议转换、配置变体与分享链接表示。`DevConfig-Gen` 提供中立的执行引擎与稳定的
Provider 契约；本仓库提供 sing-box 专属的领域实现。

```text
DevConfig-Gen
  中立引擎 · Provider 契约 · 执行流水线
        │
        ▼
devconfig_gen_singbox
  sing-box 领域 · 校验 · 转换 · server/client 变体
        │
        ▼
下游配置 / downstream configurations
```

**父仓库拥有引擎，子仓库拥有领域。**
**The parent owns the engine. The child owns the domain.**

## 快速开始 / Quick Start

```bash
git clone https://github.com/henryliu443/devconfig_gen_singbox.git
cd devconfig_gen_singbox
pip install -e ".[yaml]"
devconfig_gen_singbox generate --provider singbox --input examples/singbox.yaml --output-dir dist
```

未安装时亦可直接通过源码运行：

```bash
git clone https://github.com/henryliu443/devconfig_gen_singbox.git
cd devconfig_gen_singbox
PYTHONPATH=src python3 -m devconfig_gen.cli generate --provider singbox --input examples/singbox.yaml --output-dir dist
```

## 本仓库是什么 / What this repository is

> **Provider 是有限领域的实现，而不只是格式适配器。**
> **A Provider is a bounded domain implementation, not merely a format adapter.**

通用配置工具可以把一份文档过一遍 schema。领域 Provider 做得更多：它承载某一个
系统的**知识**——概念、关系、约束、变体与产物——并把结构化 context 转换成经过
校验、确定性的、系统专属的配置。

本仓库**不是**「万能配置生成器」。它刻意选择一个 scope，并在其中把整条链路做完整：

```text
知识 → 约束 → 转换 → 校验 → 产物
knowledge → constraints → transformation → validation → artifacts
```

## 领域 Scope：sing-box / Domain Scope: sing-box

本仓库在 DevConfig-Gen 之上实现 **`singbox`** 领域 scope。

```text
结构化 context
        │
        ▼
sing-box 领域模型
        │
        ▼
校验 validation
        │
        ▼
领域转换 transformation
        │
        ▼
server / client 配置
        │
        ▼
分享链接 share links
```

领域本身：

```text
SingBox Domain
├── 协议 protocols           (anytls / tuic / hysteria2)
├── 认证 authentication      (每个协议独立的 auth)
├── TLS / Reality            (证书路径、REALITY 密钥对、decoy 握手)
├── server / client 变体
├── 路由 routing             (DNS 分流、route 规则、geo rule set)
├── 网络/域名语义            (hosts、子域前缀)
├── 凭据处理                 (凭据即显式输入)
├── 分享链接表示
└── 产物生成                 (server / client / links)
```

领域实现位于：

```text
src/devconfig_gen/providers/singbox/
├── provider.py      # 分派 + 组装（不含任何变体字段名）
├── schema.py        # Context Schema + 结构校验
├── models.py        # 领域数据结构
├── plugins/         # 每个协议变体一个模块
│   ├── anytls.py
│   ├── tuic.py
│   └── hysteria2.py
├── route.py         # DNS + Route 组装（读 data/rules.json）
├── links.py         # 分享链接聚合
└── data/rules.json  # 内嵌路由规则表
```

## 父/子架构 / Parent / Child Architecture

```text
DevConfig-Gen                         (父仓库 · 主)
│  中立引擎
│  Provider 契约
│  执行流水线
│
└── devconfig_gen_singbox             (子仓库 · 兵)
       │  sing-box 领域知识
       │  领域校验
       │  协议转换
       │  server / client 变体
       │  分享链接生成
       │
       └── downstream (Automated-sing-box-json-generator —— 只读参考，退役中)
```

**父仓库拥有中立引擎与 Provider 契约；子仓库拥有领域。**
**The parent owns the neutral engine and the provider contract; the child owns the domain.**

- 权威方向为 **parent → child → downstream**。
- 核心改动先在父仓库落地，再通过 `upstream` remote 合入本仓库。
- 本仓库**绝不分叉或重写中立核心**（`engine` / `formats` / `validation`），只新增
  `providers/singbox/`。

## 领域模型与转换 / Domain Model & Transformations

输入 context 按语义分区：`network`（协议 / 路由 / DNS）、`client`（客户端特有）、
`options`（产物选项）。`schema.py` 负责归一化，`provider.py` 与各 plugin 负责校验，
plugin 负责把每个协议转换为它在 sing-box 中的表示。

```yaml
network:
  domain_root: example.com
  subdomain_prefixes: {reality: a1b2c3d4, tuic: e5f6a7b8, hy2: c9d0e1f2}
  tunnel_mode: proxy            # none | proxy | tun
  protocols:
    - type: anytls              # anytls | tuic | hysteria2
      enabled: true
      port: 23244
      auth: {password: replace-me}
      reality: {private_key: ..., public_key: ..., short_id: ...}
    - type: tuic
      enabled: true
      port: 9443
      auth: {uuid: ..., password: ...}
      tls: {cert_path: /etc/.../tuic.crt, key_path: /etc/.../tuic.key}
    - type: hysteria2
      enabled: true
      port: 7443
      auth: {password: ..., obfs_password: ...}
      tls: {cert_path: /etc/.../hy2.crt, key_path: /etc/.../hy2.key}
  routing: {rules_source: embedded, geoip_cn: true}   # custom_rules 可覆盖/补充
  dns: {direct_servers: [223.5.5.5, 119.29.29.29], remote_server: 1.1.1.1}
client:
  server_ip: 203.0.113.10       # TUN 排除路由
  fingerprint: chrome
options:
  target: both                  # server | client | both
  format: json                  # json | yaml
```

**隔离契约。** 每个协议的字段名与结构只存在于 `plugins/<variant>.py`。上游 sing-box
变化时只改**一个 plugin 文件**；`schema.py` / `provider.py` / `route.py` 与产物契约
保持不动，不做版本追逐。

**独立 auth。** 每个协议各自携带 `auth`（及变体）块——凭据全部是显式输入，不生成、
不存储、不读环境变量。

## 生成产物 / Generated Artifacts

| 产物 | 条件 | media type |
| --- | --- | --- |
| `sing-box.server.{json,yaml}` | `target != client` | `application/json` / `application/yaml` |
| `sing-box.client.{json,yaml}` | `target != server` | `application/json` / `application/yaml` |
| `sing-box-links.txt` | `target != server` | `text/plain` |

`{fmt}` 由 `options.format` 决定，产物集合由 `options.target` 决定。

## 输入示例 / Input Example

```bash
devconfig_gen_singbox generate --provider singbox --input examples/singbox.yaml --output-dir dist
devconfig_gen_singbox validate --provider singbox --input examples/singbox.yaml
devconfig_gen_singbox schema   --provider singbox
```

完整 context 见 [`examples/singbox.yaml`](examples/singbox.yaml)。

## 校验与确定性 / Validation & Determinism

- **路径感知诊断**：每个问题都以 dotted path 报告，例如
  `network.protocols.0.auth.password`，并一次性收集全部问题。
- **确定性输出**：JSON/YAML 均保持语义插入顺序；同一输入在多次运行、以及
  CLI 与 Python API 两端都产出 byte-for-byte 一致的产物。
- **零副作用**：Provider 不读环境变量、不写 state、不调子进程；凭据与子域前缀
  全部显式输入。

## 部署层 / Operations Layer（`singbox-ops`）

生成与部署被刻意分开：`devconfig_gen` 只做纯函数配置生成；同仓库的
`singbox_ops` 包负责所有副作用（DNS、证书、安装、systemd、防火墙、watchdog），
并通过**库调用**使用引擎，绝不注册为 provider。

```bash
pip install -e ".[yaml,ops]"

# 只组装 context（无副作用，方便审阅）
singbox-ops context --plan examples/singbox-deploy.yaml > context.yaml

# 干跑：打印将执行的每一步，不碰系统
singbox-ops deploy --plan examples/singbox-deploy.yaml --dry-run

# 真实部署 / 反向清理
singbox-ops deploy  --plan examples/singbox-deploy.yaml
singbox-ops destroy --plan examples/singbox-deploy.yaml
```

- **适配器**：`secrets`（sing-box 子进程 + 纯 Python 兜底）、`dns`（Cloudflare）、
  `acme`（acme.sh + Cloudflare DNS-01）、`state`（可选 local JSON）、
  `export`（本地文件）、`runtime`（packages / systemd / nftables-basic / warp）。
- **可注入 runner**：所有副作用走 `CommandRunner`；`--dry-run` 使用记录器，
  测试全部 mock，不需要真实 VPS。
- **零污染**：`singbox_ops` 与 `devconfig_gen` 命名空间隔离，
  引擎的零副作用契约保持不变。

详见 [`ARCHITECTURE.md`](ARCHITECTURE.md#operations-layer-singbox_ops) 与
[`examples/singbox-deploy.yaml`](examples/singbox-deploy.yaml)。

## 继承自 DevConfig-Gen 的引擎 / Inherited DevConfig-Gen Engine

> 本仓库从 DevConfig-Gen 继承以下基础设施：

- 确定性生成流水线（`engine.generate` / `generate_pipeline`）
- 结构化校验与诊断（`Diagnostic` / `ValidationError`）
- JSON/YAML 序列化（标准库 + 可选 PyYAML，内置子集解析器兜底）
- 多源合并与 dotted-path 覆盖（`deep_merge`、`--set`）
- CLI、**终端向导**（`devconfig_gen_singbox init`）、**本地 Web 工作台**
  （`devconfig_gen_singbox ui`）与 Python API

同时也继承中立的 Provider `custom` / `json` / `env`。本仓库在其之上新增领域
Provider `singbox`：

```bash
devconfig_gen_singbox providers
# custom / env / json / singbox
```

> **这些能力是基础设施。sing-box 领域始终由本子仓库负责。**
> **These capabilities are infrastructure. The sing-box domain remains the responsibility of this child repository.**

## 命令行与 Python API / CLI & Python API

```bash
# 生成 / 校验 / 查看 schema
devconfig_gen_singbox generate --provider singbox --input examples/singbox.yaml --output-dir dist --format yaml
devconfig_gen_singbox validate --provider singbox --input examples/singbox.yaml --json
devconfig_gen_singbox schema   --provider singbox

# 交互式终端向导（所有 provider 通用，含 singbox）
devconfig_gen_singbox init --provider singbox --output-dir dist

# 本地 Web 工作台（零构建，标准库 http.server）
devconfig_gen_singbox ui --port 8848
```

```python
from devconfig_gen import GenerationRequest, generate, generate_pipeline

result = generate(
    "singbox",
    GenerationRequest(
        context={
            "network": {
                "domain_root": "example.com",
                "subdomain_prefixes": {"reality": "a1b2", "tuic": "c3d4", "hy2": "e5f6"},
                "tunnel_mode": "proxy",
                "protocols": [
                    {
                        "type": "anytls",
                        "enabled": True,
                        "auth": {"password": "..."},
                        "reality": {"private_key": "...", "public_key": "...", "short_id": "..."},
                    }
                ],
            },
            "options": {"target": "server"},
        },
    ),
)
print([a.name for a in result.artifacts])   # ['sing-box.server.json']

generate_pipeline(
    "singbox",
    input_path="examples/singbox.yaml",
    output_dir="dist",
    output_format="yaml",
)
```

## 文档 / Documentation

| 主题 | 本地 | 在线 |
| --- | --- | --- |
| 快速开始 | [`docs/getting-started.md`](docs/getting-started.md) | [getting-started](https://henryliu443.github.io/DevConfig-Gen/docs/getting-started/) |
| CLI 参考 | [`docs/cli.md`](docs/cli.md) | [cli](https://henryliu443.github.io/DevConfig-Gen/docs/cli/) |
| 输入合并与覆盖 | [`docs/input-and-merge.md`](docs/input-and-merge.md) | [input-and-merge](https://henryliu443.github.io/DevConfig-Gen/docs/input-and-merge/) |
| 格式支持与产物 | [`docs/formats.md`](docs/formats.md) | [formats](https://henryliu443.github.io/DevConfig-Gen/docs/formats/) |
| 校验与诊断 | [`docs/validation.md`](docs/validation.md) | [validation](https://henryliu443.github.io/DevConfig-Gen/docs/validation/) |
| Provider 开发 | [`docs/providers.md`](docs/providers.md) | [providers](https://henryliu443.github.io/DevConfig-Gen/docs/providers/) |
| Python API | [`docs/python-api.md`](docs/python-api.md) | [python-api](https://henryliu443.github.io/DevConfig-Gen/docs/python-api/) |
| 终端向导 | [`docs/wizard.md`](docs/wizard.md) | [wizard](https://henryliu443.github.io/DevConfig-Gen/docs/wizard/) |
| Web 工作台 | [`docs/web-ui.md`](docs/web-ui.md) | [web-ui](https://henryliu443.github.io/DevConfig-Gen/docs/web-ui/) |
| 架构总览 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | — |
| Provider 铁标准 | [`PROVIDER_STANDARD.md`](PROVIDER_STANDARD.md) | — |

## 开发与测试 / Development & Testing

```bash
pip install -e ".[yaml]"
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 可重复烟雾：全量单测 + API/CLI 逐字节一致
python3 scripts/smoke_rounds.py 8
```

## 仓库关系 / Repository Relationship

- 本仓库是 **子仓库（child / fork）**：`devconfig_gen_singbox`。
- **父仓库（parent / upstream）** 为
  [`DevConfig-Gen`](https://github.com/henryliu443/DevConfig-Gen)，拥有中立核心与
  [`PROVIDER_STANDARD.md`](PROVIDER_STANDARD.md)。
- 领域 Provider（如 `providers/singbox/`）只存在于**本仓库**，**不回填父仓库**。

权威方向为 **parent → child → downstream**。核心改动先在父仓库落地，再经 `upstream`
remote 合入本仓库；不得分叉或改写中立核心。

## 许可证 / License

Apache-2.0。详见 [`LICENSE`](LICENSE)。
