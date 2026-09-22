# 架构总览

本页是架构摘要。完整的设计决策与边界说明见仓库根目录
[ARCHITECTURE.md](https://github.com/henryliu443/devconfig_gen_singbox/blob/main/ARCHITECTURE.md)。

## 目标

把结构化输入文档（JSON/YAML）转换成经过校验、规范化的结构化配置产物
（JSON/YAML/纯文本），由可扩展的 Provider 驱动。引擎与具体领域无关，
schema、规范化与校验都属于 Provider。

本仓库是父仓库 `DevConfig-Gen` 的子仓库：引擎与 Provider 契约由父仓库拥有，
本仓库只新增 sing-box 领域 Provider。使用面收敛为 **CLI** 与 **Python API**。

## 分层

```text
CLI（providers / schema / generate / validate）
        |
        v
engine.py  —— build_request / generate_pipeline / generate_from_file
  |           diagnose_request / describe_provider
  |           （唯一共享流水线，包含多源 deep_merge）
  v
ProviderRegistry -> ConfigProvider（custom / json / env / singbox）
  |
  v
formats.py   （JSON/YAML 加载、序列化、检测、媒体类型、deep_merge、coerce_scalar）
validation.py（路径感知的 Diagnostic 辅助函数）
```

## 数据流

```text
输入文件 / 内存上下文
        |
        v
formats.load_*          解析 + 格式检测
        |
        v
formats.deep_merge      多文件从左到右深度合并
        |
        v
engine._set_nested      点路径覆盖（最后应用）
        |
        v
Provider.validate / diagnose   规范化 + 结构化诊断
        |
        v
Provider.generate       产物（数据结构或预渲染字符串）
        |
        v
engine._persist         序列化 + 可选写入 output_dir
        |
        v
JSON / YAML / .env / 纯文本
```

## 数据契约（`models.py`）

- `GenerationRequest`：不可变的 `context`（输入文档）与 `options`
  （如 `format`、`name`）；
- `Diagnostic`：`field`（点路径）、`message`（渲染文本）、`severity`；
- `GeneratedArtifact`：`name`、`content`（数据结构或字符串）、`media_type`；
- `GenerationResult`：Provider 名称与产物；
- `ProviderField` / `ProviderStep`：声明式元数据，支持可选 `i18n`；
- `ConfigProvider`：Provider 协议。

## 引擎（`engine.py`）

`generate()` 是唯一执行点：查找 Provider → `validate` → `generate` →
可选持久化。更高层函数（`generate_pipeline`、`generate_from_file`、
`validate_request`、`diagnose_request`、`describe_provider`）只构建请求并
委托；CLI 不包含任何生成逻辑。

`build_request()` 组装上下文：内存上下文 → 多个输入文件（左到右
`deep_merge`）→ 点路径 `overrides`。

持久化按 `media_type` 选择序列化器；字符串产物原样写入；产物名逃逸输出
目录会被拒绝。

## 领域 Provider（`providers/singbox/`）

`singbox` 是本仓库的领域 Provider，按 `PROVIDER_STANDARD.md` 分层：

```text
providers/singbox/
├── provider.py     分派 + 组装（不含变体字段名）
├── schema.py       Context Schema + 结构校验
├── models.py       领域数据类
├── plugins/        每个协议变体一个模块
│   ├── base.py     Plugin 接口 + 通用工具
│   ├── anytls.py
│   ├── tuic.py
│   └── hysteria2.py
├── route.py        DNS + Route 组装（读 data/rules.json）
├── links.py        分享链接聚合
└── data/rules.json 内嵌路由规则表
```

上游 sing-box 的字段变化只改对应 `plugins/<variant>.py`；`provider.py` /
`schema.py` / `route.py` 与产物契约保持稳定，不做版本追逐。

## 部署层（`singbox_ops/`）

`src/singbox_ops/` 是**独立顶层包**，负责所有副作用，不进入 `devconfig_gen`
的导入图。它通过库调用使用引擎：

```text
singbox-ops CLI（context / deploy / redeploy / destroy）
        |
        v
core.plan -> core.context_builder -> devconfig_gen.engine.generate_pipeline
        |                                      |
        v                                      v
adapter suite                          server / client / links 产物
  secrets · dns · acme · state · export · runtime
```

- **隔离**：引擎保持零副作用；新增部署能力 = 新增 adapter，不动引擎。
- **普通类适配器**：name → factory 字典，不用 entry points；全项目只有一套插件体系（Provider）。
- **可注入 Runner**：`--dry-run` 与测试使用记录器，不碰真实系统。
- **显式输入**：凭据由部署层生成，但引擎仍只收到显式 context。
- **可选 state**：只持久化非敏感元数据（记录 ID、前缀、输出路径）。

## 设计决策摘要

1. `models.py` 是唯一稳定的核心数据契约；
2. `registry.py` 是扩展缝：注册一个小写 `name` 的对象即可新增 Provider；
3. 引擎不直接导入任何具体 Provider，只通过注册表工作；
4. CLI 与 Python API 共享同一条代码路径，产物逐字节一致；
5. 导入包无副作用；只有显式传入 `output_dir` 才会写文件；
6. Provider 元数据（`diagnose`、`steps`、`describe_schema`）可选，最小
   Provider 只需 `name`、`validate`、`generate`；
7. 序列化确定：JSON/YAML 保留插入顺序；
8. 核心引擎不包含远程操作、系统修改、凭据处理或部署；唯一的文件写入是
   显式的 `output_dir`。这些副作用集中在独立的 `singbox_ops` 包中。

## 范围之外

`devconfig_gen` 引擎与 Provider 不执行部署、远端仓库操作、服务管理、凭据
存储，也不自动迁移机器状态。这些关注点属于独立的 `singbox_ops` 包——它是
引擎的**消费者**：组装 context、调用纯函数流水线、通过 adapter 执行副作用。
终端向导（`devconfig-gen init`）与本地 Web 工作台（`devconfig-gen ui`）同样是
纯函数流水线上的薄客户端，不给引擎引入副作用。
