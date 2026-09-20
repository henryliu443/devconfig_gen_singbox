# Python API

`import devconfig_gen` 不会启动任何服务，也不会写文件；只有显式传入
`output_dir` 时才会产生文件输出。

## 包级导出

```python
from devconfig_gen import (
    # 数据契约
    ConfigProvider, Diagnostic, GeneratedArtifact, GenerationRequest,
    GenerationResult, ProviderField, ProviderStep,
    # 引擎
    build_request, generate, generate_from_file, generate_pipeline,
    validate_request, diagnose_request, describe_provider,
    # 格式
    FormatError, coerce_scalar, deep_merge, dumps, dump_data, dump_file,
    load_data, load_file, loads,
    # 注册表与校验
    ProviderRegistry, default_registry, ValidationError,
)
```

## 引擎函数

所有入口最终都会调用 `engine.generate`，因此 CLI 与 Python API 共享完全相同的
校验、生成与持久化路径。

### generate

```python
generate(provider, request, registry=None, output_dir=None) -> GenerationResult
```

- 查找 Provider；
- 调用 `provider.validate(request)`，若有错误则以 `"; "` 拼接后抛出
  `ValueError`；
- 调用 `provider.generate(request)`；
- 若提供 `output_dir`，把产物写入该目录。

```python
from devconfig_gen import GenerationRequest, generate

result = generate(
    "custom",
    GenerationRequest(
        context={"document": {"app": {"name": "web", "port": 8080}}},
        options={"format": "yaml"},
    ),
)
artifact = result.artifacts[0]
print(artifact.name, artifact.media_type)   # custom.yaml application/yaml
```

### build_request

```python
build_request(*, context=None, input_path=None, options=None,
              input_format=None, overrides=None) -> GenerationRequest
```

- `context` 为内存中的初始上下文（映射时作为合并基底）；
- `input_path` 可以是单个路径、路径字符串或路径序列；每个文件加载后与当前
  上下文深度合并，顺序从左到右；
- 若某次加载的结果不是映射，它会整体替换当前上下文；
- `overrides` 为点路径字典，最后应用；若上下文不是 `dict` 则重置为 `{}`。

### generate_pipeline

```python
generate_pipeline(provider, *, context=None, input_path=None, options=None,
                  output_dir=None, output_format=None, input_format=None,
                  registry=None, overrides=None) -> GenerationResult
```

`output_format` 会写入 `options["format"]`。这是 CLI `generate` 使用的入口。

### generate_from_file

```python
generate_from_file(provider, input_path, *, output_dir=None,
                   output_format=None, options=None, registry=None)
```

`generate_pipeline` 的单文件便捷封装。

### validate_request / diagnose_request

```python
validate_request(provider, *, context=None, input_path=None, options=None,
                 input_format=None, overrides=None, registry=None) -> Sequence[str]

diagnose_request(provider, *, context=None, input_path=None, options=None,
                 input_format=None, overrides=None, registry=None) -> Sequence[Diagnostic]
```

`validate_request` 返回渲染后的错误消息字符串；`diagnose_request` 优先调用
Provider 的 `diagnose`，否则把 `validate` 的消息包装成 `field=""` 的
`Diagnostic`。两者都只构建请求并校验，不生成、不写文件。

```python
from devconfig_gen import diagnose_request

for d in diagnose_request("env", context={}):
    print(d.field, "->", d.message, f"({d.severity})")
# variables -> variables must not be empty (error)
```

### describe_provider

```python
describe_provider(provider, registry=None) -> Sequence[ProviderStep]
```

优先调用 Provider 的 `describe_schema()`，否则读取 `steps` 属性，都没有时
返回空元组。

## 数据契约（models）

| 类型 | 字段 | 说明 |
| --- | --- | --- |
| `GenerationRequest` | `context`、`options` | 不可变；映射按只读处理 |
| `Diagnostic` | `field`、`message`、`severity` | `severity` 为 `"error"`/`"warning"`；`str()` 返回 message；`as_dict()` 输出 JSON 就绪字典 |
| `GeneratedArtifact` | `name`、`content`、`media_type` | `content` 可为数据结构或预渲染字符串；默认 `application/json` |
| `GenerationResult` | `provider`、`artifacts`、`diagnostics` | Provider 生成结果 |
| `ProviderField` | `name`、`type`、`required`、`default`、`description`、`choices`、`minimum`、`maximum`、`title`、`i18n` | `title` 为空时 `as_dict()` 回退为 `name`；`i18n` 为空时省略 |
| `ProviderStep` | `id`、`title`、`description`、`fields`、`i18n` | 步骤元数据 |
| `ConfigProvider` | `name`、`generate`、`validate` | 结构化协议；`diagnose`、`describe_schema`/`steps` 可选 |

`ProviderField.type` 的约定取值（客户端渲染提示）：
`string`、`integer`、`boolean`、`mapping`、`document`、`tree`。详见
[Provider 参考与开发](providers.md)。

## 格式 API（formats）

```python
from devconfig_gen import formats

data = formats.loads('{"a": 1}')          # 自动检测 JSON/YAML
formats.loads("a: 1", "yaml")
formats.load_file("config.yaml")
formats.load_data("a: 1")                  # 文本或路径
text = formats.dumps(data, "json")        # JSON：2 空格缩进 + 末尾换行
formats.dump_file(data, "out/config.yaml")
formats.detect_format(path="a.json")      # "json"
formats.resolve_format(None, name="a.yml")  # "yaml"
formats.media_type_for("yaml")            # "application/yaml"
formats.format_from_media_type("application/yaml")  # "yaml"
formats.deep_merge({"a": {"b": 1}}, {"a": {"c": 2}})
formats.coerce_scalar("9090")             # 9090
```

关键语义：

- `dumps(data, fmt)`：JSON 使用 `indent=2, sort_keys=False, ensure_ascii=False`
  并追加换行；YAML 在安装 PyYAML 时用 `safe_dump`（保留插入顺序、允许
  Unicode），否则用内置序列化器；
- `loads(text, fmt=None)`：`fmt` 省略时先看内容特征（`{`/`[` 开头视为 JSON，
  否则 YAML）；
- `load_file`：显式格式 > 扩展名 > 内容检测；
- `load_data`：`os.PathLike` 一律当文件；字符串不含换行且指向存在的文件时
  当路径，否则当文档文本；
- `coerce_scalar`：仅字符串参与推断，空字符串保持原样，非 JSON 文本保持
  原样（例如 `"1.2.0"`、`"production"`）；
- `deep_merge`：映射递归合并，标量/列表整体替换，不修改入参；
- `FormatError` 表示解析/序列化失败，`YamlError` 是其子类。

## 注册表（registry）

```python
from devconfig_gen import ProviderRegistry
from devconfig_gen.providers import CustomProvider, EnvProvider, JsonProvider, SingBoxProvider

registry = ProviderRegistry((CustomProvider(), JsonProvider(), EnvProvider(), SingBoxProvider()))
registry.names()            # ('custom', 'env', 'json', 'singbox')
registry.get("singbox")
registry.register(MyProvider())
```

- 名称必须为非空、已经小写的字符串（`str(provider.name).strip().lower()`
  必须与 `provider.name` 完全一致），否则 `ValueError`；
- 重复注册同名 Provider 抛出 `ValueError`；
- `get` 会去除首尾空白并转小写；未知名称抛出 `ValueError`，错误信息包含
  可用名称列表；
- `default_registry` 已注册 `custom`、`json`、`env`、`singbox`。

## 校验 API（validation）

```python
from devconfig_gen import Diagnostic, ValidationError, validation

errors = []
value = validation.expect_integer(99999, "app.port", errors, minimum=1, maximum=65535)
# value is None; errors[0] == Diagnostic("app.port", "port must be between 1 and 65535, got 99999")
```

可用辅助函数：`expect_mapping`、`expect_string`、`expect_integer`、
`expect_enum`、`expect_string_mapping`，以及 `is_mapping`、`is_integer`。
每个 `expect_*` 把 `Diagnostic` 追加到传入的列表并返回规范化后的值（失败
返回 `None`），从而一次收集全部问题。消息使用字段路径的叶子名，`field`
保留完整点路径。`ValidationError` 接受 `Diagnostic` 或字符串序列，`errors`
属性为消息元组，`str()` 以 `"; "` 连接。

## 自定义 Provider 示例

```python
from devconfig_gen import (
    Diagnostic, GeneratedArtifact, GenerationRequest, GenerationResult,
    ProviderField, ProviderRegistry, ProviderStep, ValidationError, generate,
)


class GreetingProvider:
    name = "greeting"

    steps = (
        ProviderStep(
            id="input",
            title="Greeting input",
            fields=(
                ProviderField("who", type="string", required=True, title="Who"),
            ),
        ),
    )

    def describe_schema(self):
        return self.steps

    def diagnose(self, request):
        if not request.context.get("who"):
            return (Diagnostic("who", "missing required field: 'who'"),)
        return ()

    def validate(self, request):
        return tuple(item.message for item in self.diagnose(request))

    def generate(self, request):
        diagnostics = self.diagnose(request)
        if diagnostics:
            raise ValidationError(diagnostics)
        return GenerationResult(
            provider=self.name,
            artifacts=(
                GeneratedArtifact(
                    name="greeting.json",
                    content={"message": f"hello {request.context['who']}"},
                    media_type="application/json",
                ),
            ),
        )


registry = ProviderRegistry((GreetingProvider(),))
result = generate(
    "greeting",
    GenerationRequest(context={"who": "world"}),
    registry=registry,
)
```

更多 Provider 约定与内置实现细节见 [Provider 参考与开发](providers.md)。
