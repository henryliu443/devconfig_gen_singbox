# DevConfig-Gen_SingBox 文档

本仓库是父仓库 `DevConfig-Gen` 的**子仓库（child / fork）**：父仓库拥有中立的执行
引擎与稳定的 Provider 契约，本仓库只在其之上承载 **sing-box 领域 Provider**
（`providers/singbox/`）。权威方向为 **parent → child → downstream**。

本仓库只保留稳定的 **CLI** 与 **Python API** 两个使用面（不再提供终端向导与
Web 工作台）。安装与第一个产物请从 [安装与快速开始](getting-started.md) 开始。

## 领域 Scope：sing-box

本仓库实现 `singbox` 领域 scope：把结构化 context 转换为 sing-box 的
server / client 配置与分享链接。领域细节（协议字段名、结构）隔离在
`providers/singbox/plugins/<variant>.py`，上游 sing-box 变化只改一个 plugin 文件。

```bash
devconfig-gen generate --provider singbox --input examples/singbox.yaml --output-dir dist
devconfig-gen validate --provider singbox --input examples/singbox.yaml
devconfig-gen schema   --provider singbox
```

## 推荐阅读顺序（CLI 优先）

1. [安装与快速开始](getting-started.md) — 环境要求、第一个产物、退出码；
2. [CLI 命令参考](cli.md) — `providers` / `schema` / `generate` / `validate`；
3. [CLI 配方](cli-cookbook.md) — 分层配置、管道输入、批量生成等可复制命令；
4. [输入合并与覆盖](input-and-merge.md) — 多源合并与覆盖语义；
5. [格式支持与产物](formats.md) — JSON/YAML 边界、序列化、产物命名与持久化；
6. [校验与诊断](validation.md) — `Diagnostic` 与退出码的编程约定。

需要编程集成时看 [Python API](python-api.md)；需要扩展时看
[Provider 参考与开发](providers.md)。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [安装与快速开始](getting-started.md) | 环境要求、安装方式、最小可运行示例 |
| [CLI 命令参考](cli.md) | `providers` / `schema` / `generate` / `validate` 全部参数、行为与示例 |
| [CLI 配方](cli-cookbook.md) | 面向脚本的常用命令组合与注意事项 |
| [输入合并与覆盖](input-and-merge.md) | 多输入文件、`deep_merge` 规则、`--set` 覆盖与类型推断 |
| [格式支持与产物](formats.md) | JSON/YAML 支持边界、格式检测、序列化、产物命名与持久化 |
| [校验与诊断](validation.md) | `Diagnostic`、`diagnose`/`validate` 的区别、校验辅助函数 |
| [Provider 参考与开发](providers.md) | 内置 Provider 的准确行为、元数据模型、自定义 Provider 指南 |
| [Python API](python-api.md) | 包级导出、engine、formats、registry、models、validation |
| [开发与测试](development.md) | 项目结构、测试、CI、文档维护 |
| [架构总览](architecture.md) | 分层、数据流、扩展点；完整设计决策见仓库根目录 [ARCHITECTURE.md](https://github.com/henryliu443/devconfig_gen_singbox/blob/main/ARCHITECTURE.md) |

## 能力清单

### 核心引擎与契约

- Provider 协议：`name`、`validate`、`generate` 为必需，`diagnose`、
  `describe_schema`/`steps` 可选（`models.py`、`engine.py`）。
- 单入口流水线：CLI 与 Python API 都调用 `devconfig_gen.engine.generate`
  （`engine.py`）。
- 数据契约：`GenerationRequest`、`GenerationResult`、`GeneratedArtifact`、
  `Diagnostic`、`ProviderField`、`ProviderStep`（`models.py`）。
- Provider 注册表：名称必须为非空小写字符串，重复注册或未知名称抛出
  `ValueError`（`registry.py`）。

### 命令行

- 四个子命令：`providers`（发现）、`schema`（元数据）、`generate`（生成）、
  `validate`（校验）（`cli.py`）。
- 脚本友好的稳定契约：退出码 `0`/`1`/`2`；`validate --json` 输出诊断数组；
  `schema` 输出步骤数组；产物确定性可 diff。
- 多输入 `--input`（可重复、从左到右深度合并）与点路径 `--set` 覆盖，
  值按 JSON 字面量推断类型（`cli.py`、`engine.build_request`）。
- 输出格式解析：`--format` → `--name` 后缀 → Provider 默认；产物名支持子目录，
  拒绝绝对路径与 `..`。

### 内置 Provider

- `custom`：无 schema，接受任意 JSON/YAML 结构（映射、序列或标量根），原样输出。
- `json`：透传/重新序列化；产物默认名为 `config.json` / `config.yaml`。
- `env`：把嵌套映射扁平化为 `UPPER_SNAKE_CASE` 变量，输出 `.env` 纯文本。
- `singbox`：本仓库的领域 Provider，生成 server / client 配置与分享链接。

### Python API

- `generate`、`generate_pipeline`、`generate_from_file`、`validate_request`、
  `diagnose_request`、`describe_provider`、`build_request`（`engine.py`）。

## 模块地图

```text
src/devconfig_gen/
├── __init__.py       包导出（仅 CLI / Python API 面）
├── models.py         稳定数据契约：请求/结果/产物/诊断/字段/步骤
├── engine.py         唯一执行流水线：构建请求、校验、生成、持久化
├── formats.py        JSON/YAML 加载与序列化、格式检测、深度合并、类型推断
├── validation.py     路径感知的校验辅助函数与 ValidationError
├── registry.py       ProviderRegistry 与内置 Provider 注册
├── cli.py            命令行入口（仅参数解析与调用 engine）
└── providers/
    ├── custom.py          custom Provider
    ├── json_provider.py   json Provider
    ├── env_provider.py    env Provider
    └── singbox/           sing-box 领域 Provider（本仓库新增）
```

## 版本

当前版本 `2.0.0`（`pyproject.toml`、`devconfig_gen.__version__` 与
`devconfig-gen --version` 保持一致）。
