# 输入合并与覆盖

DevConfig-Gen 支持从多个来源组装同一条请求上下文：内存上下文、多个输入
文件，以及最后的点路径覆盖。CLI 与 Python API 使用同一套规则，因此两条路径
产生的产物逐字节一致。

## 数据来源与优先级

上下文按以下顺序组装，后者覆盖前者：

1. 内存中的 `context`（Python API；CLI 从第一个 `--input` 开始）；
2. 每个输入文件，按出现顺序从左到右依次合并；
3. `overrides`（CLI `--set KEY=VALUE`，Python API `overrides=`），最后应用。

对应实现：`engine.build_request` → `formats.deep_merge` →
`engine._set_nested`。相关 CLI 细节见 [CLI 命令参考](cli.md)。

## 深度合并规则（deep_merge）

`formats.deep_merge(base, overlay)` 的语义：

- 当基底和覆盖层都是映射时：递归合并，嵌套键取并集；
- 其他情况：覆盖层的值整体替换基底（标量、列表，以及用标量替换映射等）；
- 不修改任何入参对象（返回新字典）。

```python
from devconfig_gen import deep_merge

deep_merge(
    {"app": {"name": "a", "port": 80, "labels": {"team": "core", "tier": "api"}}},
    {"app": {"port": 8080, "labels": {"tier": "edge"}}},
)
# {"app": {"name": "a", "port": 8080, "labels": {"team": "core", "tier": "edge"}}}

deep_merge({"a": {"b": 1}}, {"a": 2})   # {"a": 2}
deep_merge({"a": [1]}, {"a": [2, 3]})   # {"a": [2, 3]}
```

输入文件的格式各自独立检测：同一个命令里可以混用 `.yaml`、`.yml` 和
`.json`（检测规则见[格式支持与产物](formats.md#格式检测与选择)）。

## 覆盖（overrides）

点路径覆盖在合并之后应用，用来做命令行级别的最终定值：

```bash
devconfig-gen generate --provider custom \
  --input configs/base.yaml \
  --input configs/prod.json \
  --set app.port=9090 \
  --set app.environment=production \
  --output-dir dist --format yaml
```

规则：

- 键使用 `.` 分隔的路径（如 `app.port`），中间层级不存在时自动创建字典；
- 如果中间层级已存在但不是字典，会被替换为字典
  （`{"app": 5}` + `app.port=1` → `{"app": {"port": 1}}`）；
- CLI 的值经 `formats.coerce_scalar` 推断 JSON 类型：
  `true`/`false` → 布尔，`42` → 整数，`1.5` → 浮点，`null` → 空，
  `"text"` → 字符串，其余保持文本；
- Python API 的 `overrides` **不做类型推断**，按传入的 Python 值原样设置；
- CLI 中 `--set` 缺少 `=` 或键为空会报错并返回退出码 `2`。

```python
from devconfig_gen import build_request

request = build_request(
    context={"app": {"name": "web", "port": 80}},
    overrides={"app.port": 8080, "app.environment": "production"},
)
request.context
# {"app": {"name": "web", "port": 8080, "environment": "production"}}
```

## 非映射文档的处理

`build_request` 逐文件合并时，如果某个文件加载结果不是映射，它会整体替换
当前上下文，而不是合并：

```python
build_request(input_path=["base.yaml", "list.json"])
# list.json 为 [1, 2, 3] 时，最终 context == [1, 2, 3]
```

随后如果有 `overrides`，且当前上下文不是 `dict`，上下文会被重置为 `{}`
再写入覆盖值。`custom` Provider 接受列表或标量根；`json` 与 `env` 要求根为
映射（见 [Provider 参考与开发](providers.md)）。

## CLI 与 Python API 等价性

CLI 的 `generate` 调用 `engine.generate_pipeline`，其行为等价于：

```python
from devconfig_gen import generate_pipeline

result = generate_pipeline(
    "custom",
    input_path=["configs/base.yaml", "configs/prod.json"],
    overrides={"app.port": 9090, "app.environment": "production"},
    output_format="yaml",
    output_dir="dist",
)
```

测试 `tests/test_api_parity.py` 断言 CLI 与 Python API 生成的 JSON/YAML 产物
逐字节一致；该断言是测试套件的一部分。
