# 校验与诊断

校验由 Provider 负责，引擎只负责调用和汇总。所有问题会一次性收集，而不是
遇到第一个错误就停止。Provider 契约见
[Provider 参考与开发](providers.md#provider-契约)。

## Diagnostic

```python
from devconfig_gen import Diagnostic

d = Diagnostic("app.port", "port must be between 1 and 65535, got 99999")
str(d)        # "port must be between 1 and 65535, got 99999"
d.severity    # "error"（默认）；也可以是 "warning"
d.as_dict()   # {"field": "app.port", "message": "...", "severity": "error"}
```

- `field`：出问题值的点路径（如 `app.port`）；未知路径时为 `""`；
- `message`：已渲染的用户可读文本；
- `severity`：`"error"` 或 `"warning"`。

## validate 与 diagnose

Provider 必须实现 `validate(request) -> Sequence[str]`，返回渲染后的消息。
推荐同时实现 `diagnose(request) -> Sequence[Diagnostic]` 以获得结构化字段
路径；未实现时引擎自动把 `validate` 的消息包装为 `field=""` 的
`Diagnostic`：

```python
from devconfig_gen import diagnose_request, validate_request

validate_request("env", context={})    # ("variables must not be empty",)
diagnose_request("env", context={})    # (Diagnostic(field="variables", ...),)
```

两者都不生成产物、不写文件。

## 引擎的失败方式

- `engine.generate` 先调用 `validate`；只要有错误，就把消息用 `"; "` 拼接后
  抛出 `ValueError`；
- Provider 的 `generate` 通常也会自行校验，失败时抛出
  `ValidationError`（`ValueError` 的子类，见下）；
- 因此调用方只需捕获 `ValueError` 即可处理两类失败。

## CLI 行为

```bash
devconfig_gen_singbox validate --provider env --input broken.yaml
# stderr: invalid: variables must not be empty
# 退出码 1
```

- 默认只向 stderr 打印 `error` 级别的消息；通过时 stdout 输出
  `<输入路径列表>: valid`；
- `--json` 改为向 stdout 打印全部诊断（含 warning）的 JSON 数组；
- 退出码只看 `error`：有 error 为 `1`，否则 `0`；
- 加载、解析、未知 Provider 等错误不属于诊断，直接 `error: ...` 到 stderr，
  退出码 `2`。

内置 Provider 当前只会产生 `error` 级诊断；`warning` 是数据模型支持的级别，
第三方 Provider 可以使用。

## 校验辅助函数

`devconfig_gen.validation` 提供一组路径感知的原语。每个函数把
`Diagnostic` 追加到传入的 `errors` 列表，并返回规范化后的值（失败返回
`None`），从而一次收集全部问题。消息使用路径的叶子名，`field` 保留完整
点路径。

| 函数 | 行为 |
| --- | --- |
| `expect_mapping(value, path, errors)` | 必须是映射，否则 `<leaf> must be a mapping, got ...` |
| `expect_string(value, path, errors, *, allow_empty=False)` | 必须是字符串；去除首尾空白；默认不允许空串 |
| `expect_integer(value, path, errors, *, minimum=None, maximum=None)` | 必须是整数（`bool` 被拒绝）；支持单边或双边范围 |
| `expect_enum(value, path, errors, *, allowed, case_insensitive=True)` | 必须命中选项；默认忽略大小写并返回规范选项 |
| `expect_string_mapping(value, path, errors)` | 值为标量的映射；值规范化为字符串（`None`→`""`）；嵌套容器报错 |

辅助判断：`is_mapping`、`is_integer`（排除 `bool`）。

```python
from devconfig_gen import validation

errors = []
validation.expect_integer(99999, "app.port", errors, minimum=1, maximum=65535)
# errors == [Diagnostic("app.port", "port must be between 1 and 65535, got 99999")]
```

## ValidationError

```python
from devconfig_gen import Diagnostic, ValidationError

err = ValidationError([Diagnostic("a", "a is bad"), "b: two"])
err.errors       # ("a is bad", "b: two")
err.diagnostics  # (Diagnostic("a", "a is bad"), Diagnostic("", "b: two"))
str(err)         # "a is bad; b: two"
```

`ValidationError` 接受 `Diagnostic` 或字符串序列，并把字符串包装为
`field=""` 的诊断。它继承 `ValueError`，因此 `engine.generate` 与 CLI 的
错误处理路径一致。

## 内置 Provider 的诊断示例

```python
from devconfig_gen import diagnose_request

# env：空变量映射
diagnose_request("env", context={})
# [Diagnostic(field="variables", message="variables must not be empty")]

# env：列表包含映射
diagnose_request("env", context={"b": [{"x": 1}]})
# [Diagnostic(field="b", message="b must not contain mappings")]

# json：根不是映射
diagnose_request("json", context=[1, 2, 3])
# [Diagnostic(field="", message="document: expected a mapping at the root")]

# custom：永远通过
diagnose_request("custom", context={"anything": [1, 2]})
# ()
```

更多内容见 [Python API](python-api.md) 与 [Provider 参考与开发](providers.md)。
