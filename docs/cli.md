# CLI 命令参考

CLI 是 DevConfig-Gen 的主要使用面。所有命令都是无状态、脚本友好的：输入由
参数和文件决定，产物写到显式目录，结果通过退出码和可选的 JSON 输出表达。

当前版本为 **2.0.0**；`devconfig-gen --version` 会打印包内
`devconfig_gen.__version__`，例如：

```text
$ devconfig-gen --version
devconfig-gen 2.0.0
```

两种调用方式等价：

```bash
devconfig-gen <command> [options]                    # 已安装
PYTHONPATH=src python3 -m devconfig_gen.cli <command> [options]   # 源码运行
```

## 命令总览

按推荐使用顺序：

| 顺序 | 命令 | 用途 |
| --- | --- | --- |
| 1 | [`providers`](#providers) | 发现有哪些 Provider |
| 2 | [`schema`](#schema) | 查看 Provider 需要哪些字段（机器可读） |
| 3 | [`generate`](#generate) | 生成配置产物（主命令） |
| 4 | [`validate`](#validate) | 只校验输入，不写文件 |

全局选项：

| 选项 | 说明 |
| --- | --- |
| `-h, --help` | 查看帮助；也可用于子命令（`devconfig-gen generate --help`） |
| `--version` | 打印 `devconfig-gen <version>`（读取包内 `__version__`，当前为 `2.0.0`） |

子命令是必填项：不带命令直接运行会由 argparse 报错并返回退出码 `2`。

## 通用约定

### 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | `validate` 发现 `error` 级诊断 |
| `2` | 用法/输入错误：缺少子命令、未知 Provider、文件不存在或不可读、解析失败、`--set` 语法错误、产物名越界；`generate` 的校验失败也归入此码 |

脚本里可以直接用退出码做门禁：

```bash
if devconfig-gen validate --provider custom --input configs/app.yaml; then
  devconfig-gen generate --provider custom --input configs/app.yaml --output-dir dist
fi
```

### 错误输出

除 `validate` 的校验失败外，所有失败都以单行 `error: <message>` 写到
**stderr**，例如：

```text
error: unknown provider 'missing'; available: custom, env, json, singbox
error: cannot read .: [Errno 21] Is a directory: '.'
error: --set expects KEY=VALUE, got 'bad'
error: artifact name escapes output directory: '../escape.json'
```

### 机器可读输出

两个命令提供 JSON 输出，适合被脚本或其他程序消费：

- `devconfig-gen validate --json`：诊断数组（见 [validate](#validate)）；
- `devconfig-gen schema --provider <name>`：步骤/字段元数据数组。

## providers

列出所有已注册 Provider，按名称排序，每行一个：

```text
$ devconfig-gen providers
custom
env
json
singbox
```

该命令没有其他参数，正常结束时返回退出码 `0`。

## schema

以 JSON 数组打印 Provider 的声明式步骤/字段（`ProviderStep.as_dict()`），
可用于自动生成表单、文档或客户端。

```text
usage: devconfig-gen schema [-h] [--provider PROVIDER]
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--provider` | `json` | Provider 名称 |

```bash
devconfig-gen schema --provider env
```

输出结构（字段顺序固定）：

```json
[
  {
    "id": "variables",
    "title": "Environment variables",
    "description": "Nested keys are joined with '_' and upper-cased.",
    "fields": [
      {
        "name": "variables",
        "title": "Variables",
        "type": "mapping",
        "required": true,
        "default": null,
        "description": "Variables; nested keys become UPPER_SNAKE_CASE names.",
        "i18n": { "zh": { "title": "变量", "description": "..." } }
      }
    ],
    "i18n": { "zh": { "title": "环境变量", "description": "..." } }
  }
]
```

注意：输出由 `json.dumps(..., indent=2)` 生成，非 ASCII 字符（如内置中文
`i18n`）会以 `\uXXXX` 转义。未知 Provider 返回退出码 `2`。

## generate

主命令：加载并合并输入，交给 Provider 校验和生成，把产物写入输出目录。

```text
usage: devconfig-gen generate [-h] [--provider PROVIDER] --input INPUT
                              --output-dir OUTPUT_DIR [--format {json,yaml}]
                              [--name NAME] [--set KEY=VALUE]
```

| 参数 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--provider` | 否 | `json` | Provider 名称 |
| `--input` | **是** | — | JSON/YAML 输入文件；可重复，按出现顺序从左到右深度合并 |
| `--output-dir` | **是** | — | 产物输出目录；不存在时自动创建 |
| `--format` | 否 | 见下 | **输出**格式 `json` 或 `yaml` |
| `--name` | 否 | 由 Provider 决定 | 输出文件名，可包含子目录 |
| `--set` | 否 | — | 点路径覆盖 `KEY=VALUE`；可重复，最后应用 |

### 输入组装顺序

`generate` 内部等价于 `engine.generate_pipeline`，上下文按以下顺序组装：

1. 每个 `--input` 文件按命令行顺序依次加载并深度合并（映射递归合并，标量/
   列表整体替换）；
2. `--set` 覆盖最后应用。

```bash
devconfig-gen generate --provider custom \
  --input configs/base.yaml \
  --input configs/prod.json \
  --set app.port=9090 \
  --output-dir dist --format yaml
```

合并规则详见[输入合并与覆盖](input-and-merge.md)。

### --input 细节

- 每个文件独立检测格式：按扩展名（`.json` / `.yaml` / `.yml`）与内容判断，
  因此一次命令可以混用 `.yaml`、`.yml`、`.json`；
- `--input` 必须是文件；目录会报 `cannot read ...: Is a directory`；
- 同一个文件可以传多次，会重复合并；
- 没有内置的 `-` 标准输入约定，但可以使用操作系统的 `/dev/stdin` 或进程
  替换（见 [CLI 配方](cli-cookbook.md#从标准输入或管道读取)）。

### --set 细节

`--set` 是命令行侧最后的定值手段，语法为 `KEY=VALUE`：

| 规则 | 说明 |
| --- | --- |
| 点路径 | `KEY` 用 `.` 分层，如 `app.port`；中间层级不存在时自动创建字典 |
| 覆盖中间层 | 若中间层已存在但不是字典，会被替换为字典：`{"app": 5}` + `app.port=1` → `{"app": {"port": 1}}` |
| 数组不支持下标 | `--set a.0=x` 不会修改列表，而是把 `a` 替换成 `{"0": "x"}` |
| 值类型推断 | 值经 `coerce_scalar` 处理：`true`/`false`→布尔，`42`→整数，`1.5`→浮点，`null`→空，`"text"`→字符串，其余保持文本 |
| 列表/对象值 | 值本身是合法 JSON 时可用：`--set 'list=[1,2,3]'`、`--set 'obj={"x":1}'` |
| 值中的 `=` | 只按第一个 `=` 分割：`--set 'url=http://x?a=b'` → `http://x?a=b` |
| 键空白 | 键会去除首尾空白（`--set ' a =1'` 等价于 `a=1`）；非 JSON 值的空白原样保留（`--set 'b= x'` → `" x"`） |
| 非法输入 | 缺少 `=` 或键为空 → stderr `error: --set expects ...`，退出码 `2` |

类型推断示例：

```bash
--set flag=true          # true（布尔）
--set count=42           # 42（整数）
--set ratio=1.5          # 1.5（浮点）
--set nothing=null       # null
--set label=web          # "web"
--set version=1.2.0      # "1.2.0"（非 JSON，保持字符串）
--set empty=             # ""（空字符串）
--set 'quoted="hi"'      # "hi"（去掉 JSON 引号）
```

注意：Python API 的 `overrides` 不做类型推断（见
[输入合并与覆盖](input-and-merge.md#覆盖overrides)）；类型推断只发生在
CLI 解析 `--set` 时。

### 输出格式与产物命名

格式解析优先级：

1. `--format json|yaml`；
2. `--name` 的文件后缀（`.json` / `.yaml` / `.yml`）；
3. Provider 默认（`custom`/`json` 为 JSON；`env` 忽略格式）。

| Provider | 默认产物 | 媒体类型 | `--name` 示例 |
| --- | --- | --- | --- |
| `custom` | `custom.json` / `custom.yaml` | `application/json` / `application/yaml` | `--name my-config.yaml` |
| `json` | `config.json` / `config.yaml` | 同上 | `--name config.prod.json` |
| `env` | `.env` | `text/plain` | `--name .env.production` |
| `singbox` | `sing-box.server.*` / `sing-box.client.*` / `sing-box-links.txt` | `application/json` / `application/yaml` / `text/plain` | 由 `options.target` 决定，不受 `--name` 影响 |

- `--name` 允许子目录（自动创建）：`--name sub/deep/custom.yaml`；
- 产物名不允许绝对路径或包含 `..`，否则报
  `artifact name escapes output directory` 并返回 `2`；
- 显式 `--format` 优先于 `--name` 后缀：`--format json --name x.yaml` 会写出
  一个内容为 JSON 的 `x.yaml`。

### 输出消息

每个产物输出一行：

```text
generated dist/custom.yaml
```

路径是 `--output-dir` 与产物名的简单拼接（不解析为绝对路径）。

### 示例集

```bash
# 1. 最简：custom 透传
devconfig-gen generate --provider custom --input examples/custom.yaml \
  --output-dir generated --format yaml

# 2. 显式 JSON 输出
devconfig-gen generate --provider custom --input examples/custom.json \
  --output-dir generated --format json

# 3. 后缀决定格式
devconfig-gen generate --provider custom --input examples/custom.yaml \
  --output-dir generated --name renamed.yaml

# 4. 多输入分层 + 覆盖
devconfig-gen generate --provider custom \
  --input configs/base.yaml --input configs/prod.json \
  --set app.port=9090 --set app.environment=production \
  --output-dir dist --format yaml

# 5. 生成 .env
devconfig-gen generate --provider env --input examples/vars.yaml --output-dir dist

# 6. 自定义 .env 名称
devconfig-gen generate --provider env --input examples/vars.yaml \
  --output-dir dist --name .env.production

# 7. 写入子目录
devconfig-gen generate --provider custom --input examples/custom.yaml \
  --output-dir dist --name envs/prod/custom.yaml

# 8. sing-box 领域 Provider（server / client / links）
devconfig-gen generate --provider singbox --input examples/singbox.yaml \
  --output-dir dist --format yaml
```

## validate

只校验、不生成、不写文件。

```text
usage: devconfig-gen validate [-h] [--provider PROVIDER] --input INPUT
                              [--format {json,yaml}] [--set KEY=VALUE]
                              [--json]
```

| 参数 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--provider` | 否 | `json` | Provider 名称 |
| `--input` | **是** | — | 输入文件；可重复，合并规则与 `generate` 相同 |
| `--format` | 否 | 自动 | **输入**格式覆盖；会强制所有 `--input` 按该格式解析（例如无后缀文件按 YAML 解析） |
| `--set` | 否 | — | 校验前应用的点路径覆盖，规则与 `generate` 相同 |
| `--json` | 否 | 关 | 以 JSON 数组打印全部诊断 |

行为：

- 通过：stdout 输出 `<输入路径列表>: valid`，退出码 `0`；
- 失败：默认向 stderr 逐条输出 `invalid: <message>`，退出码 `1`；
- `--json`：向 stdout 输出诊断数组（含 `warning`），退出码仍按 `error` 判定；
- 加载/解析/未知 Provider：stderr `error: ...`，退出码 `2`。

```bash
$ devconfig-gen validate --provider custom --input examples/custom.yaml
examples/custom.yaml: valid

$ devconfig-gen validate --provider env --input broken.yaml
invalid: variables must not be empty        # stderr，退出码 1

$ devconfig-gen validate --provider custom --input examples/custom.yaml --json
[]                                          # 通过时也是合法 JSON

$ devconfig-gen validate --provider env --input broken.yaml --json
[
  {
    "field": "variables",
    "message": "variables must not be empty",
    "severity": "error"
  }
]
```

`broken.yaml` 的内容是空变量映射，例如：

```yaml
variables: {}
```

`--json` 的诊断对象字段固定为 `field`、`message`、`severity`（即
`Diagnostic.as_dict()`），适合配合 `jq`：

```bash
devconfig-gen validate --provider env --input broken.yaml --json \
  | jq -r '.[] | "\(.field): \(.message)"'
```

`--format` 作为输入覆盖的典型用法：

```bash
printf 'app:\n  port: 1234\n' > config.txt
devconfig-gen validate --provider custom --input config.txt --format yaml
```

## 脚本化与自动化

CLI 面向脚本设计的三个契约：

1. **退出码稳定**：`0` 成功、`1` 校验失败、`2` 用法/输入错误；
2. **JSON 输出稳定**：`validate --json` 输出诊断数组，`schema` 输出步骤数组；
3. **输出确定**：相同输入与环境下产物逐字节一致，适合提交或 diff。

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1) 先用 schema 确认 Provider 字段
devconfig-gen schema --provider env > /tmp/env-schema.json

# 2) 校验所有输入，失败即退出（退出码 1 会被 set -e 捕获）
devconfig-gen validate --provider env --input configs/vars.yaml

# 3) 生成到输出目录
devconfig-gen generate --provider env --input configs/vars.yaml \
  --output-dir dist --name .env.production
```

更多配方（分层配置、管道输入、多环境批量生成、与 `jq` 协作等）见
[CLI 配方](cli-cookbook.md)。

## 限制与注意事项

- **没有 `-` 标准输入约定**：请使用 `/dev/stdin` 或进程替换；
- **`--set` 不支持数组下标**：列表路径会被替换为字典；
- **`--input` 只接受文件**：目录会报错；
- **`env` Provider 忽略 `--format`**：产物始终是 `.env` 文本；
- **`generate --format` 是输出格式，`validate --format` 是输入覆盖**；
- 未安装 PyYAML 时，YAML 由内置子集解析器处理，顶层流式集合/裸标量文档等
  不受支持，详见[格式支持与产物](formats.md#内置子集解析器支持范围)。
