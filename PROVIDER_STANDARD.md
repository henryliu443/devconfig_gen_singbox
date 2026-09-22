# DevConfig-Gen Provider 标准（铁标准 / 白皮书）

> 状态：**生效中（DevConfig-Gen 自身的规范）**
> 适用范围：所有"转换型"（rich domain）Provider，例如 sing-box、未来的任何领域 Provider。
> 定位：**这是 DevConfig-Gen 自己的标准，不是给任何下游使用方的要求。**
> 下游仓库（如 sing-box 集成分支、`Automated-sing-box-json-generator`）是实现与消费者，本文件是它们的上游依据。

---

## 〇、这份文档解决什么问题

DevConfig-Gen 的核心是"provider 中立的引擎 + 可插拔的 Provider"。当 Provider 开始承载**真实领域转换**（而不是透传）时，如果任由每个 Provider 自由发挥，会出现三个问题：

1. **领域细节渗透进契约**：某个上游工具的字段改名、结构升级，导致 Provider 的输入 schema、产物名、调用方式全部抖动。
2. **版本追逐**：上游每 ~50 天更新一次，我们被迫做 0.1 → 0.2 → 0.3 的逐版本对齐。
3. **副作用回潮**：为了"方便"，Provider 开始读环境变量、写 state、调子进程生成凭据——破坏确定性与 AGENTS.md 红线。

本文件给出**一套稳定的标准**，让领域变化被隔离在可插拔的 plugin 层，而契约层保持不动。

---

## 〇.5、新增内容归属（父仓库 vs 下游）

> **父仓库只承载 provider 中立的"标准与核心"，任何领域细节一律留在下游。**

| 内容 | 归属 | 说明 |
|---|---|---|
| `PROVIDER_STANDARD.md`（本文件） | **父仓库新增** | provider 中立的标准/白皮书 |
| 核心可复用的 plugin 基协议、schema 校验辅助 | **父仓库新增（仅当确实中立）** | 只有不绑定任何领域时才进 core；否则留在下游 |
| `AGENTS.md` 钩子 | **父仓库新增** | 指向本文件 |
| 具体 provider 子包（如 `providers/singbox/`） | **下游新增** | 领域实现，不进父仓库 |
| 变体 plugins、`data/*.json`、派生输出 | **下游新增** | 领域细节，不进父仓库 |
| 领域字段名、协议结构、上游规则数据 | **绝不进父仓库** | — |
| 凭据生成、读环境变量、写 state、调子进程 | **绝不进任何仓库的 provider** | 违反核心原则 |

**判断准则**：一段内容若去掉领域名后仍成立 → 可进父仓库；否则留在下游。

---

## 一、核心原则（不可协商）

| # | 原则 | 含义 |
|---|---|---|
| 1 | **零副作用** | Provider 不读环境变量、不写 state、不调用子进程生成凭据。所有值显式组装成 context 传入。 |
| 2 | **Pluggable 隔离** | 领域细节（协议字段名、结构变化）由 `plugins/` 消化；契约层（schema/provider/route）不随上游版本跳动。 |
| 3 | **无版本递进** | 不做与上游逐版本对齐的 0.1/0.2/0.3 追逐；上游变化只改对应 plugin 文件。 |
| 4 | **凭据即输入** | 凭据、密钥、子域前缀等敏感/随机值全部显式输入，core 不生成、不存储。 |
| 5 | **确定性** | 同输入连跑两次，输出 byte-for-byte 一致；JSON/YAML 均保持语义插入顺序。 |

---

## 二、Provider 契约（引擎层，已存在）

`devconfig_gen.models.ConfigProvider` 是结构化协议，实现者无需继承基类。必需成员：

| 成员 | 说明 |
| --- | --- |
| `name: str` | 非空小写名称，注册表的键 |
| `validate(request) -> Sequence[str]` | 返回渲染后的错误消息；空序列表示通过 |
| `generate(request) -> GenerationResult` | 生成产物；失败抛 `ValidationError` |

可选成员：`diagnose(request)`、`describe_schema()`、`steps`。详见 `docs/providers.md`。

### 数据契约（`models.py`，稳定）

- `GenerationRequest`：不可变 `context`（输入）+ `options`（`format` / `name` / 领域选项）。
- `GenerationResult`：`provider` + `artifacts`（多产物）。
- `GeneratedArtifact`：`name`、`content`（数据结构或预渲染字符串）、`media_type`。
- `Diagnostic`：`field`（dotted path）、`message`、`severity`。

> **这些是唯一稳定的核心契约。任何领域 Provider 都不得要求修改它们。**

---

## 三、转换型 Provider 的分层标准

透传型 Provider（`custom` / `json`）不需要本节。转换型 Provider **必须**按下列分层组织：

```
providers/<domain>/
├── __init__.py          # 导出 <Domain>Provider
├── provider.py          # 只做：校验 / 分派 / 组装（不含领域字段细节）
├── schema.py            # Context Schema 定义 + 结构校验
├── models.py            # 领域内部数据类
├── plugins/
│   ├── __init__.py      # 插件注册表
│   ├── base.py          # Plugin 接口 + 通用工具
│   └── <variant>.py     # 每个变体一个模块（如 anytls/tuic/hysteria2）
├── route.py             # 通用路由/策略组装（读内嵌数据文件）
├── links.py             # 派生输出（如分享链接）聚合
└── data/
    └── *.json           # 内嵌数据（规则表等），用 Path(__file__).parent 加载
```

### 分层职责（硬性）

| 层 | 允许 | 禁止 |
|---|---|---|
| `provider.py` | 遍历变体、调用 plugin、组装产物 | 硬编码某个变体的字段名/结构 |
| `schema.py` | 定义输入结构、结构级校验 | 依赖上游版本细节 |
| `plugins/<variant>.py` | 承载该变体的全部领域细节 | 读取全局状态、副作用 |
| `route.py` | 通用策略组装、加载 `data/*.json` | 绑定某个变体 |
| `data/*.json` | 纯数据 | 代码逻辑 |

### Plugin 接口（Pluggable 核心）

每个变体一个模块，实现：

```python
class VariantPlugin(Protocol):
    variant_type: str

    def build_server_side(self, cfg: VariantConfig) -> dict: ...
    def build_client_side(self, cfg: VariantConfig) -> dict: ...
    def build_derived_output(self, cfg: VariantConfig) -> str: ...
    def validate(self, cfg: VariantConfig) -> Sequence[str]: ...
```

> 接口名可按领域调整，但**必须**满足：新增/修改一个变体 = 只动一个 plugin 文件 + 注册表一行，契约层零改动。

---

## 四、Context Schema 约定

### 结构约定

- 顶层按语义分区：`network`（网络/路由/协议）、`client`（客户端特有）、`options`（产物选项）。
- 变体列表统一放在 `network.protocols`（或领域等价位置），每项含 `type`、`enabled`，以及**独立的 `auth` 块**。
- **Independent auth**：每个变体自己的凭据放在自己的 `auth`（及变体特有）块内，不共用扁平凭据池。理由：结构清晰、扩展性好、避免跨变体字段撞名。
- 敏感值（密钥、密码、uuid、子域前缀）**必须显式传入**。

### 红线

- 禁止 Provider 内随机生成子域前缀或读 state。
- 禁止 Provider 内调用上游二进制（如 `sing-box generate`）生成凭据。
- 禁止用 `os.environ` 作为默认值；需要环境变量时由外层读取后显式写入 context。

### 校验约定

- 结构校验在 `schema.py`，业务校验在 `provider.py` 与各 plugin。
- 诊断路径用 dotted path，定位到具体字段（如 `network.protocols.0.auth.password`）。
- 一次收集全部问题（`validation.py` 原语），不在首个错误处中断。

---

## 五、产物契约约定

- 产物由 `options.target` 之类开关决定集合（如 `server` / `client` / `both`）。
- 产物命名稳定、可预测，格式后缀由 `options.format` 决定（`json` / `yaml`）。
- 预渲染文本产物（如链接列表）用 `text/plain`，走 engine 的 verbatim 写盘路径。
- 多产物由 `GenerationResult.artifacts` 直接承载，**不新增核心数据结构**。

---

## 六、确定性要求

- JSON/YAML 输出保持语义插入顺序（与现有引擎一致）。
- 无时间戳、无随机、无环境依赖进入产物内容。
- 测试必须包含"同输入连跑两次 byte-for-byte 一致"。

---

## 七、测试要求

每个转换型 Provider 至少覆盖：

1. **Schema 校验**：缺字段、类型错误、未知变体类型、非法枚举。
2. **Plugin 独立测试**：每个 plugin 的各构建方法输出结构快照。
3. **集成测试**：各 `target` 取值下的产物集合与命名。
4. **确定性**：双格式（JSON/YAML）连跑一致。
5. **全量**：`PYTHONPATH=src python3 -m unittest discover -s tests -v` 全绿。

---

## 八、演进规则（关键）

> **上游变化 ≠ 我们的版本变化。**

- 上游工具升级（字段改名、新增/删除变体、结构调整）→ **只改对应 `plugins/<variant>.py`**。
- `provider.py` / `schema.py` / `route.py` / 产物契约 / 调用方式 **保持稳定**。
- 不引入与上游对齐的版本号递进。
- 破坏性契约变更必须走显式评审（API Freeze Review），并在 CHANGELOG 记录。

---

## 九、参考实现（位于下游，非本仓库）

首个完整实现 `providers/singbox/` **位于私有集成分支（下游），不属于本仓库**，仅作本标准的示例参考：

- `plugins/anytls.py`、`plugins/tuic.py`、`plugins/hysteria2.py` 的隔离写法；
- `data/rules.json` 的内嵌数据约定；
- Independent auth 的 Context Schema；
- 多产物（server / client / links）的契约。

> 这些内容**不得**回填进父仓库；父仓库只保留本文件定义的中立标准。

---

## 十、与下游的关系

下游仓库（如 `Automated-sing-box-json-generator`）是**消费者**：

- 它们把已收集的值**组装成符合本标准的 Context Schema**，调用 `generate_pipeline`。
- 它们**不实现** plugin；plugin 属于 DevConfig-Gen。
- 它们**不承担**版本追逐；领域变化由本仓库的 plugin 层吸收。

> `Automated-sing-box-json-generator` 已进入 **merged/decoupled → retired** 流程：
> 它是**只读参考（reference only）**，**不是开发目标**。所有新开发在
> parent（`DevConfig-Gen`）与其 child（`devconfig_gen_singbox`）进行。

> 本文件是 DevConfig-Gen 的自我约束。下游只需遵循 Context Schema 与产物契约，无需理解 plugin 内部实现。

---

## 十一、WebUI Widget 扩展（可选能力）

> WebUI 的字段渲染是**查表驱动**的：内置 `string` / `integer` / `boolean` /
> `mapping` / `document` / `tree` 六种类型各有默认 Widget。这是全链路里唯一
> 曾经硬编码、现已开放的扩展点。**Provider 仍是唯一扩展点**，不引入第二套
> 体系。

Provider 可实现**可选**方法 `web_ui_widgets()`，返回
`{field_type: js_factory_source}`，把新字段类型接入 WebUI：

```python
class MyProvider:
    name = "mydomain"

    def web_ui_widgets(self):
        return {"node-editor": "(ctx) => { /* ... return HTMLElement */ }"}
```

约定（硬性）：

- 工厂源码必须是**同源** `/api/widgets` 返回的字符串，前端注册进同一张
  Widget 表；求值失败或非函数时**回退**到该类型的内置 Widget（未知类型回退
  `string`）。
- 工厂接收单个 `ctx`（`field` / `fid` / `grp` / `provider` / `existing` /
  `setValue` / `setFormData` / `getFormData` / `rerender`），返回 DOM 元素。
- 切换 Provider 时先恢复默认 Widget 表，再注册当前 Provider 的 Widget。
- **未实现 `web_ui_widgets()` 的 Provider 行为完全不变。** 这是纯增量能力，
  不进入 `ConfigProvider` 必需契约（`name` / `validate` / `generate`）。
- Widget 代码由 Provider 作者负责；父仓库只定义机制，**具体领域 Widget 留在
  下游**（如 sing-box 的节点编辑器）。

> 修改 Widget 协议或 `ctx` 字段时，必须同步更新本节与 `ARCHITECTURE.md`、
> `docs/web-ui.md`。

---

> **维护要求**：修改 Provider 契约、Context Schema 约定、Plugin 接口或产物契约时，必须同步更新本文件。
