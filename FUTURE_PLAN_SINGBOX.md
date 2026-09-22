# 接入计划：把 sing-box 项目的「JSON 生成前端」接进 DevConfig-Gen

> 状态：待执行（阶段 A 未开始）
> 目标项目：`Automated-sing-box-json-generator`（审查版本 `c10468c`，version 0.3.35）
> 铁标准来源：父仓库 `DevConfig-Gen` 的 `PROVIDER_STANDARD.md`（本文档的下游实现）
> 本文档为存档，执行过程中如有变更请同步更新。

---

## 〇、仓库关系与开发顺序（本次新增）

三仓库：

| 代号 | 仓库 | 角色 |
|---|---|---|
| **父仓库** | `DevConfig-Gen` | 铁标准/白皮书所在地；provider 框架先在父仓库落地 |
| **本工程** | `devconfig_gen_singbox` | 私有集成分支；singbox provider 在此实现 |
| **A 开头** | `Automated-sing-box-json-generator` | **即将合并/解耦并退役的旧上层；只读参考（reference only），不是开发目标** |

**开发顺序（铁定）：父仓库 DevConfig-Gen 先开发 → 回到本工程 → 最后 A-repo 仅做解耦/退役处理。**

> A-repo **不会**被作为开发地点；它只提供参考实现，最终被合并/解耦并退役。

### 发布节奏

1. **先在父仓库把铁标准与 provider 框架做实**：Pluggable 架构、Context 契约、Plugin 接口写入 `PROVIDER_STANDARD.md`。
2. **本工程跑通**：把 sing-box 的 JSON 生成能力以 provider 形式接入，测试全绿。
3. **A-repo 解耦**：等本工程稳定后，A-repo 才改为依赖 DevConfig-Gen，旧 `config.py`/`route_profile.py` 退役。

> 关键顺序：**父仓库定标准 → 本工程跑通 → A-repo 解耦**。阶段 A 不依赖 A-repo 的任何改动。

---

## 一、核心原则（铁标准，来自 PROVIDER_STANDARD.md）

1. **零副作用**：provider 不读环境变量、不写 state、不调用子进程生成凭据。所有值显式组装成 context 传入。
2. **Pluggable 隔离**：sing-box 协议细节（anytls/tuic/hysteria2 字段名、结构变化）由 `plugins/` 消化。上层不硬编码 sing-box JSON 结构。
3. **无版本递进**：对方 sing-box 每 ~50 天更新一次（0.3 → 0.4 → 1.0…），我们**不做 0.1/0.2/0.3 的追逐式版本对齐**；变化只影响对应 plugin 文件，不改动 context schema、provider 契约或产物契约。
4. **凭据即输入**：凭据与子域前缀全部显式输入，core 不生成、不存储 → 保住确定性与 AGENTS.md 红线。

---

## 二、已确认决策

| 决策点 | 结论 |
|---|---|
| 接入范围 | server 配置 + client 配置 + 分享链接（纯函数） |
| 凭据结构 | **Independent auth**：每个 protocol 独立 `auth` 块（结构清晰、扩展性好） |
| 规则数据 | **暂时内嵌** `data/rules.json`，零配置开箱；允许 `custom_rules` 覆盖 |
| 协议命名 | **不改名**，保留 `anytls` / `tuic` / `hysteria2`，降低认知成本 |
| WireGuard | **整体不要**：不搬 `wireguard.py`，`tunnel_mode` 只保留 `none`/`proxy`/`tun` |
| 代码形态 | 新子包 `src/devconfig_gen/providers/singbox/` |

---

## 三、Context Schema（输入契约）

```yaml
network:
  domain_root: "example.com"              # 必填
  subdomain_prefixes:                     # 必填
    reality: "a1b2"
    tuic: "c3d4"
    hy2: "e5f6"

  tunnel_mode: proxy                      # 必填；enum: none | proxy | tun

  protocols:                              # 必填；至少一个 enabled: true
    - type: anytls
      enabled: true
      port: 23244                         # 可选，默认由 plugin 定
      auth:
        password: "xxx"                   # 必填
      reality:
        decoy_server: "www.cloudflare.com"  # 可选，默认 www.cloudflare.com
        decoy_port: 443                     # 可选，默认 443
        private_key: "xxx"                  # 必填
        public_key: "yyy"                   # 必填（client outbound 用）
        short_id: "zzz"                     # 必填

    - type: tuic
      enabled: true
      port: 9443
      auth:
        uuid: "xxx"                       # 必填
        password: "yyy"                   # 必填
      tls:
        cert_path: "/path/to/cert"        # 必填（server inbound 用）
        key_path: "/path/to/key"          # 必填

    - type: hysteria2
      enabled: true
      port: 7443
      auth:
        password: "xxx"                   # 必填
        obfs_password: "yyy"              # 必填
      bandwidth:
        up_mbps: 500                      # 可选，默认 500(server)/50(client)
        down_mbps: 500                    # 可选，默认 500(server)/200(client)
      tls:
        cert_path: "/path/to/cert"
        key_path: "/path/to/key"
      masquerade: "https://www.cloudflare.com"  # 可选

  routing:
    rules_source: "embedded"              # 可选；embedded | custom
    geoip_cn: true                        # 可选，默认 true
    custom_rules: {}                      # 可选，覆盖或补充 rules.json

  dns:
    direct_servers: ["223.5.5.5", "119.29.29.29"]  # 可选
    remote_server: "1.1.1.1"                        # 可选

client:                                   # 仅 client 配置需要
  server_ip: "1.2.3.4"                    # 可选；TUN 排除路由用
  fingerprint: "chrome"                   # 可选

options:                                  # 产物选项
  target: both                            # server | client | both
  format: json                            # json | yaml
```

### 红线

- `subdomain_prefixes` 必须**显式传入**，禁止在 provider 内随机生成或读取 state。
- `auth` 块内所有字段必须**显式传入**，禁止在 provider 内调用 `sing-box generate` 子进程。
- 禁止读取 `os.environ` 作为默认值；环境变量若需支持，由外层读后显式写入 context。

---

## 四、Plugin 接口（Pluggable 核心）

每个协议一个 Python 模块，实现以下接口：

```python
class ProtocolPlugin(Protocol):
    protocol_type: str  # "anytls", "tuic", "hysteria2"

    def build_server_inbound(self, cfg: ProtocolConfig) -> dict: ...
    def build_client_outbound(self, cfg: ProtocolConfig) -> dict: ...
    def build_share_link(self, cfg: ProtocolConfig) -> str: ...
    def validate(self, cfg: ProtocolConfig) -> Sequence[str]: ...
```

**隔离承诺**：sing-box 版本更新（如 anytls inbound 字段改名）→ 只改 `plugins/xxx.py`，不动 `provider.py` / `schema.py` / `route.py`。

---

## 五、子包结构

```
src/devconfig_gen/providers/singbox/
├── __init__.py          # 导出 SingBoxProvider
├── provider.py          # ConfigProvider 契约：校验 / 分派 / 组装
├── schema.py            # Context Schema 定义 + 结构校验
├── models.py            # 内部数据类（ProtocolConfig / RoutingConfig …）
├── plugins/
│   ├── __init__.py      # 插件注册表
│   ├── base.py          # ProtocolPlugin Protocol + 通用工具
│   ├── anytls.py
│   ├── tuic.py
│   └── hysteria2.py
├── route.py             # DNS + Route 组装（读 rules.json）
├── links.py             # 分享链接聚合
└── data/
    └── rules.json       # 内嵌规则数据
```

---

## 六、产物契约（输出标准）

`generate()` 返回的 `GenerationResult.artifacts` 必须包含：

| 产物名 | 条件 | media_type |
|---|---|---|
| `sing-box.server.{fmt}` | `target != client` | `application/json` / `application/yaml` |
| `sing-box.client.{fmt}` | `target != server` | 同上 |
| `sing-box-links.txt` | `target != server`（可选） | `text/plain` |

`{fmt}` 由 `options.format` 决定：`json` 或 `yaml`。

---

## 七、校验与元数据

- `diagnose`/`validate` 用现有 `validation.py` 原语，诊断路径为 dotted path，如 `network.protocols.0.auth.password`。
- `steps` 声明式元数据（现有客户端无多选字段类型）：
  - `tunnel_mode` → 单选 choices（现有能力即可）；
  - 启用的协议 → wizard/studio 用逗号分隔 string，provider 内部归一化为 list。

---

## 八、注册与数据文件约定

- `registry.py`：import + `default_registry` 加一项（2 行改动，属预留扩展缝）。
- `rules.json` 是第一个带数据文件的 provider：用 `Path(__file__).parent / "data" / "rules.json"` 加载，并在 `ARCHITECTURE.md` 记录该约定。

---

## 九、测试（`tests/test_singbox_provider.py`）

- **Schema 校验**：缺字段、类型错误、未知 protocol type、非法 `tunnel_mode`。
- **Plugin 独立测试**：每个 plugin 的 server inbound / client outbound / share link 结构快照。
- **集成测试**：`target=server/client/both` 的 artifact 集合与命名。
- **确定性**：同输入连跑两次 byte-for-byte 一致；JSON/YAML 双格式。
- **全量**：`PYTHONPATH=src python3 -m unittest discover -s tests -v`。

---

## 十、阶段 B：A-repo 解耦（最后做，可选）

本工程跑通后，A-repo 两条路：

- **B1（零成本）**：什么都不动，接受两份拷贝并存。风险是 sing-box 升级时两边各自跟进。
- **B2（真解耦）**：A-repo 的 `deploy.py` 改为依赖 `devconfig-gen`，把 `credentials.py`/`state.py` 收集到的值**组装成 Context Schema**，调我们的 engine 拿配置；其 `config.py`/`route_profile.py` 内部整体退役。

> A 把底层做实，B 只是让旧上层改用新底层——A 不依赖 B，B 可随时做或不做。

### 对方侧改造要求（执行 B 时）

1. **退役** `config.py` 和 `route_profile.py` 中的硬编码 JSON 构建逻辑。
2. **保留 `credentials.py`**，但改为**组装 context** 而非直接生成配置。
3. **调用 DevConfig-Gen**：

   ```python
   from devconfig_gen.engine import generate_pipeline

   result = generate_pipeline(
       "singbox",
       context=assembled_context,
       output_dir="/etc/sing-box",
       output_format="json",
   )
   # result.artifacts 包含 server.json / client.json / links.txt
   ```

4. **不碰**：`installer/firewall/certs/cloudflare_dns/state/watchdog/doctor/benchmark/validate/uninstall` 等部署相关代码。

---

## 十一、不变承诺（向 A-repo 保证）

| 对方关切 | 承诺 |
|---|---|
| sing-box 升级时我们要大改吗？ | **不需要**。协议字段变化由对应 plugin 消化，context schema 与调用方式不变。 |
| 凭据生成逻辑要重写吗？ | **不需要**。继续用现有 `credentials.py`，只需把输出改为"组装 context"。 |
| rules.json 要维护两份吗？ | **不需要**。DevConfig-Gen 内嵌默认 rules，可用 `network.routing.custom_rules` 覆盖。 |
| 可以渐进迁移吗？ | **可以**。B2 可先加一条新分支，旧路径保留直到验证通过。 |

---

## 十二、执行顺序

1. **父仓库**：把铁标准写进 `PROVIDER_STANDARD.md`，并在 AGENTS.md 挂钩。
2. **本工程**：建子包骨架 → schema/plugins/route/links/provider → 注册 → 测试全绿。
3. **文档**：`ARCHITECTURE.md` 记录 provider 与 rules.json 约定；`CHANGELOG.md` 新条目；`examples/singbox.yaml` 示例输入。
4. **A-repo**：最后做 B2 解耦，或保持 B1。

---

## 十三、验收准则

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` 全绿；
- 同输入连跑两次输出 byte-for-byte 一致（JSON/YAML 双格式）；
- provider 输出与目标行为结构等价（golden 快照）；
- 父仓库验证通过后，再推本工程 dev；A-repo 逻辑理顺后再解耦。

---

## 附：进文档前待办

- [ ] 本计划内容与父仓库 `PROVIDER_STANDARD.md` 保持同步
- [ ] 本工程 `ARCHITECTURE.md` 增加 singbox provider 与 data 文件约定
- [ ] `README.md` 增加 singbox provider 输入示例
- [ ] A-repo 侧改为指向 DevConfig-Gen 官方文档的链接（阶段 B）
- [ ] 阶段 B 完成后做一次接口冻结审查（API Freeze Review）
