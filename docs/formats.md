# 格式支持与产物

DevConfig-Gen 的输入格式是 JSON 和 YAML；产物格式是 JSON、YAML 或纯文本
（内置 `env` Provider 输出 `.env`）。核心引擎不定义其他格式。

## 格式标识与别名

| 规范名 | 别名 | 媒体类型 |
| --- | --- | --- |
| `json` | `application/json` | `application/json` |
| `yaml` | `yml`、`application/yaml`、`application/x-yaml` | `application/yaml` |

相关函数：`formats.normalize_format`、`formats.media_type_for`、
`formats.format_from_media_type`。未知格式或媒体类型抛出 `FormatError`。

## 格式检测与选择

- `formats.detect_format(path=..., text=...)`：
  先看扩展名（`.json` / `.yaml` / `.yml`）；再看文本（去掉 BOM 和空白后以
  `{` 或 `[` 开头视为 JSON，否则 YAML）；只有路径时默认 YAML；都没有时默认 JSON。
- `formats.loads(text, fmt=None)`：显式 `fmt` 优先，否则按文本检测。
- `formats.load_file(path, fmt=None)`：显式 `fmt` 优先，否则结合扩展名和内容检测。
- `formats.load_data(source, fmt=None)`：`os.PathLike` 一律当文件；字符串不含
  换行且指向已存在的文件时当路径，否则当文档文本。
- `formats.resolve_format(explicit, name=..., path=..., default="json")`：
  用于产物命名；优先级为显式格式 → 文件名后缀 → 路径 → 默认值。

CLI 中：

- `generate --format` 是**输出格式**；
- `validate --format` 是**输入格式覆盖**（例如无后缀文件按 YAML 解析）。

## JSON

- 加载：标准库 `json.loads`；失败抛出 `FormatError("invalid JSON: ...")`。
- 序列化：`json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False)`
  并追加一个换行符。
- 保留插入顺序，非 ASCII 字符原样输出。

## YAML

YAML 由两层实现支撑：

1. 安装了 PyYAML（`pip install "devconfig_gen_singbox[yaml]"`）时：
   - 解析使用 `yaml.safe_load`；
   - 序列化使用 `yaml.safe_dump(default_flow_style=False, sort_keys=False, allow_unicode=True)`；
   - 获得完整 YAML 语义。
2. 未安装 PyYAML 时，使用包内自带的子集解析器/序列化器，零依赖。

`formats.HAS_PYYAML` 表示当前环境是否使用 PyYAML。两种后端都保留插入顺序，
但在同一份数据上产生的字节可能不同；同一环境内的输出是确定性的。

### 内置子集解析器支持范围

支持：

- 缩进（空格）嵌套的映射与序列，`- item` 列表，列表项内嵌映射；
- 标量：字符串、整数、浮点数（含指数）、布尔（`true`/`True`/`TRUE` 等）、
  空值（空串、`~`、`null`/`Null`/`NULL`）、`.inf`/`.nan`；
- 单引号与双引号字符串（双引号遵循 JSON 转义规则）；
- 单行流式集合 `[a, b]`、`{x: 1, y: [2, 3]}`，可嵌套；
- `#` 注释与空行（`#` 需位于行首或前面是空白）；
- 块标量 `|`、`>` 及修剪模式 `|-`、`|+`、`>-`、`>+`；
- 开头的文档标记 `---` / `...`。

不支持或行为受限：

- 锚点/别名（`&`/`*`）、自定义标签（`!tag`）、合并键（`<<`）：不会报错，
  但会被当作普通字符串；
- 多文档：首个文档之后出现 `---` 会报错；
- 顶层流式集合或顶层裸标量作为 YAML 文档：报
  `invalid mapping entry`（顶层块序列 `- 1` 可以；顶层 JSON 数组可以；
  安装 PyYAML 后不受此限制）；
- 跨多行的流式集合：报 `unterminated flow ...`；
- Tab 缩进：不会按缩进处理，也不保证报错，可能被静默解析成错误结构
  ——请始终使用空格；
- 块标量内的 `#` 行会被当作注释丢弃，无法保留。

### 内置子集序列化器行为

- 块风格输出，每级 2 空格缩进，末尾一个换行；
- 空映射输出 `{}`，空列表输出 `[]`；
- 必要时对字符串加双引号：空串、首尾空白、包含控制字符或 `\n`/`\r`/`\t`、
  形如数字、与保留字冲突（`null`、`true`、`false`、`yes`、`no`、`on`、
  `off`、`~`）、或不匹配安全字符集；
- 非字符串映射键先 `str()` 再序列化；元组按序列输出；
- 不支持的类型（如 `set`、`bytes`）抛出 `FormatError`。

## 类型推断（coerce_scalar）

`formats.coerce_scalar(value)` 仅对字符串生效：尝试用 `json.loads` 解释，
成功则返回对应 JSON 值（`"9090"`→`9090`、`"true"`→`True`、`"null"`→`None`、
`"1.5"`→`1.5`、`'"quoted"'`→`"quoted"`）；失败或空串则原样返回
（`"production"`、`"1.2.0"` 保持字符串）。CLI `--set` 使用该函数。

## 产物与持久化

产物由 `GeneratedArtifact(name, content, media_type)` 表示。`engine.generate`
只有在传入 `output_dir` 时才写文件：

1. 创建 `output_dir`（以及产物名中的子目录）；
2. 拒绝绝对路径或包含 `..` 的产物名：
   `artifact name escapes output directory: '...'`；
3. `content` 为字符串时**原样写入**（`env` 的 `.env` 文本走这条路径）；
4. 否则按 `media_type` 选择序列化器：
   - `application/json` → JSON；
   - `application/yaml` → YAML；
   - 其他媒体类型抛出
     `cannot persist media type '...' for '...'`。

产物命名规则（由 Provider 决定默认名，`--name` / `options["name"]` 可覆盖）：

| Provider | 默认名 | 格式解析 |
| --- | --- | --- |
| `custom` | `custom.json` / `custom.yaml` | `--format` → `--name` 后缀 → JSON |
| `json` | `config.json` / `config.yaml` | `--format` → `--name` 后缀 → JSON |
| `env` | `.env` | 忽略格式，始终为文本 |

示例：

```bash
# 显式格式
devconfig_gen_singbox generate --provider custom --input examples/custom.yaml \
  --output-dir out --format json        # out/custom.json

# 由文件名推断格式
devconfig_gen_singbox generate --provider custom --input examples/custom.yaml \
  --output-dir out --name renamed.yaml  # out/renamed.yaml（YAML 内容）

# 显式格式优先于文件名
devconfig_gen_singbox generate --provider custom --input examples/custom.yaml \
  --output-dir out --format json --name renamed.yaml
# out/renamed.yaml，但内容是 JSON
```

## 确定性

- JSON 与 YAML 都保留映射的插入顺序（`sort_keys=False`）；
- 产物末尾都有换行；
- 同一输入、同一 Provider、同一后端环境下，重复运行输出逐字节一致；
- 是否安装 PyYAML 会切换 YAML 后端，因此不同环境之间 YAML 字节可能有差异。
