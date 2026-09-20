# Provider 参考与开发

Provider 是 DevConfig-Gen 的扩展点：它决定输入如何被校验、规范化并转换成产物。
引擎本身不包含任何领域逻辑，只通过注册表调用 Provider。

本仓库是父仓库 `DevConfig-Gen` 的子仓库，使用面只有 **CLI** 与 **Python API**；
Provider 元数据用于 `devconfig-gen schema` 与任何第三方客户端。

## Provider 契约

`devconfig_gen.models.ConfigProvider` 是一个结构化协议（`Protocol`），实现者
不需要继承任何基类。必需成员：

| 成员 | 说明 |
| --- | --- |
| `name: str` | 非空小写名称，注册表的键 |
| `validate(request) -> Sequence[str]` | 返回渲染后的错误消息；空序列表示通过 |
| `generate(request) -> GenerationResult` | 生成产物；出错时应抛出 `ValidationError` 或 `ValueError` |

可选成员（引擎会探测并按需降级，缺少它们时 Provider 依然完整可用）：

| 成员 | 作用 |
| --- | --- |
| `diagnose(request) -> Sequence[Diagnostic]` | 结构化诊断；未实现时 `diagnose_request` 把 `validate` 的消息包装为 `field=""` 的 `Diagnostic` |
| `describe_schema() -> Sequence[ProviderStep]` | 声明式步骤/字段；未实现时读取 `steps` 属性，再退回空元组 |
| `steps` | 类属性形式的步骤元数据 |

`generate` 的约定：先自行校验（`engine.generate` 也会先调用 `validate`），
失败时抛出 `ValidationError`；成功时返回
`GenerationResult(provider=self.name, artifacts=(...))`。

## 声明式元数据

`ProviderStep` 与 `ProviderField` 用于驱动 `schema` 命令和任何第三方客户端。
序列化规则（`as_dict()`）：

- `ProviderField`：`name`、`title`、`type`、`required`、`default`、
  `description`，可选 `choices`、`minimum`、`maximum`、`i18n`；
  `title` 为空时回退为 `name`，空 `i18n` 会被省略。
- `ProviderStep`：`id`、`title`、`description`、`fields`，可选 `i18n`。
- `i18n` 的结构为 `{"<locale>": {"title": ..., "description": ...}}`，内置
  Provider 提供 `zh` 翻译；规范英文文案始终保留在默认字段中。

`ProviderField.type` 是给客户端的渲染提示，常用取值：`string`、`integer`、
`boolean`、`mapping`、`document`、`tree`。`required`、`choices`、`minimum`、
`maximum`、`default` 是提示和约束元数据；是否真正强制由各 Provider 的
`validate` 决定。

## 内置 Provider

### custom

- 名称：`custom`
- 元数据：步骤 `document`（标题 “Custom document”），字段 `document`
  （`type="tree"`，`required=False`）
- 行为：无 schema、无字段校验（`validate` 永远返回空）；接受任意 JSON/YAML
  结构，包括映射、序列和标量根。
- 上下文解包：当上下文是映射且**唯一键**为 `document` 时，输出该键的值；
  否则原样输出整个上下文。
- 产物：默认 `custom.json` 或 `custom.yaml`，媒体类型
  `application/json` / `application/yaml`。

```python
from devconfig_gen import GenerationRequest, generate

generate("custom", GenerationRequest(context={"document": {"a": {"b": [1, 2]}}}))
# -> custom.json，内容 {"a": {"b": [1, 2]}}

generate("custom", GenerationRequest(context={"document": [1, 2, 3]}))
# -> custom.json，内容 [1, 2, 3]
```

### json

- 名称：`json`
- 元数据：步骤 `document`（标题 “Document”），字段 `document`
  （`type="document"`，`required=True`）
- 行为：透传/重新序列化，不做字段转换。
- 校验：解包后上下文必须是映射，否则返回
  `"document: expected a mapping at the root"`。
- 上下文解包：仅当唯一键 `document` 的值是**映射**时解包；若
  `document` 的值是列表等非映射，则保留 `document` 键。
- 产物：默认 `config.json` 或 `config.yaml`。

### env

- 名称：`env`
- 元数据：步骤 `variables`（标题 “Environment variables”），字段
  `variables`（`type="mapping"`，`required=True`）
- 行为：把嵌套映射扁平化为 `UPPER_SNAKE_CASE` 变量，输出 `.env` 文本
  （`media_type: text/plain`），默认文件名 `.env`，可用 `options["name"]`
  覆盖（例如 `.env.production`）。
- 忽略 `format` 选项：无论 `--format` 是什么，产物都是 `.env` 文本。

转换规则：

1. 上下文必须是映射。唯一键为 `variables` 且其值为映射时，使用该值作为
   变量根。
2. 空映射（包括 `{}` 与 `{"variables": {}}`）报错
   `variables must not be empty`；非映射报错
   `variables must be a mapping at the document root`。
3. 每个键段先做规范化：把 `[^A-Za-z0-9]+` 替换为 `_`，去掉首尾 `_`，
   再转大写。空键段报错 `<path> is not a valid variable name`。
4. 嵌套映射递归展开，路径用 `_` 连接；空嵌套映射生成空值变量（如 `A=`）。
5. 列表/元组：若包含映射则报错 `<path> must not contain mappings`；
   否则各项用逗号连接。标量转换：`None`→空串、`True`/`False`→
   `true`/`false`、数字→十进制文本、其他→`str()`。
6. 集合（`set`）等不支持的值类型报错 `<path> has an unsupported value type`。
7. 不同路径扁平化后撞名时报错
   `'<KEY>' collides with '<origin>' after normalization`。

### singbox

- 名称：`singbox`
- 本仓库的领域 Provider：把结构化 context 转换为 sing-box 的
  `server` / `client` 配置与分享链接，产物由 `options.target`
  （`server` / `client` / `both`）与 `options.format`（`json` / `yaml`）决定。
- 协议变体（`anytls` / `tuic` / `hysteria2`）的字段细节隔离在
  `providers/singbox/plugins/`，`provider.py` / `schema.py` / `route.py`
  不含任何变体字段名。
- 遵循 `PROVIDER_STANDARD.md`：零副作用、凭据即输入、无版本追逐。

## 内置 Provider 汇总

| Provider | 根要求 | 默认产物 | 媒体类型 | 字段校验 |
| --- | --- | --- | --- | --- |
| `custom` | 任意（映射/序列/标量） | `custom.json` / `custom.yaml` | `application/json` / `application/yaml` | 无 |
| `json` | 映射 | `config.json` / `config.yaml` | `application/json` / `application/yaml` | 根必须是映射 |
| `env` | 映射 | `.env` | `text/plain` | 非空映射；列表不得含映射等 |
| `singbox` | 映射（`network` 必填） | `sing-box.server.*` / `sing-box.client.*` / `sing-box-links.txt` | `application/json` / `application/yaml` / `text/plain` | Context Schema + 各 plugin |

## 编写自定义 Provider

最小实现只需要 `name`、`validate`、`generate`：

```python
from devconfig_gen import GeneratedArtifact, GenerationResult, ValidationError


class UpperProvider:
    name = "upper"

    def validate(self, request):
        if not isinstance(request.context, dict):
            return ("context must be a mapping",)
        return ()

    def generate(self, request):
        errors = self.validate(request)
        if errors:
            raise ValidationError(errors)
        return GenerationResult(
            provider=self.name,
            artifacts=(
                GeneratedArtifact(
                    name="upper.json",
                    content={str(k).upper(): v for k, v in request.context.items()},
                ),
            ),
        )
```

注册并调用：

```python
from devconfig_gen import GenerationRequest, ProviderRegistry, generate

registry = ProviderRegistry((UpperProvider(),))
result = generate("upper", GenerationRequest(context={"a": 1}), registry=registry)
```

注册规则：

- `name` 必须是非空字符串，且 `str(name).strip().lower() == name`
  （即已经全小写且无首尾空白），否则 `ProviderRegistry.register` 抛出
  `ValueError`；
- 同名重复注册抛出 `ValueError`；
- 自定义注册表可通过 `generate(..., registry=registry)` 传入。

### 使用内置 Provider 作为参考

- `src/devconfig_gen/providers/custom.py`：最简结构，演示 `tree` 元数据与
  上下文解包；
- `src/devconfig_gen/providers/json_provider.py`：演示 `document` 元数据与
  根类型校验；
- `src/devconfig_gen/providers/env_provider.py`：演示真实转换、`diagnose`
  结构化诊断、多字段校验与纯文本产物；
- `src/devconfig_gen/providers/singbox/`：领域 Provider 的完整分层示例。

## 元数据驱动的 CLI

- `devconfig-gen schema --provider <name>` 打印
  `[step.as_dict() for step in describe_provider(name)]`；
- 新增 Provider 后无需修改 CLI：注册到 `default_registry`（或传入自定义
  `registry`）即可被识别。
