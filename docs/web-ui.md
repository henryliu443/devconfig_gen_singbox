# Web 工作台与 HTTP API（ui）

`devconfig-gen ui` 启动一个零构建、零前端依赖的本地单页应用：HTML/CSS/JS
全部内嵌在 `src/devconfig_gen/web_ui.py` 中，由 Python 标准库
`ThreadingHTTPServer` 提供，不需要 npm / node_modules。

```bash
devconfig-gen ui
devconfig-gen ui --host 127.0.0.1 --port 8848 --workspace ~/projects/my-app --no-browser
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 监听地址 |
| `--port` | `8848` | 监听端口 |
| `--no-browser` | 否 | 不自动打开浏览器 |
| `--workspace` | 当前工作目录 | 允许 `/api/export` 写入的根目录 |

启动后终端打印本地地址、导出工作空间和停止方式；按 `Ctrl+C` 停止并返回
`0`。浏览器默认打开 `http://127.0.0.1:8848`。

## 界面功能

工作台是一个左右双栏的单页应用：左侧按 Provider 的声明式 `steps` 编辑，
右侧实时预览序列化产物。自 1.1.0 起，字段渲染完全查表驱动，界面也做了
一次视觉刷新（更大的圆角卡片、胶囊按钮、更柔和的阴影与间距）。

- **中英双语**：右上角 `中 / EN` 一键切换，偏好保存在
  `localStorage["dcg_lang"]`；步骤/字段文案优先使用 Provider 的 `i18n`
  翻译（内置 Provider 提供中文）。
- **亮 / 暗主题**：页面根据 `prefers-color-scheme` 自动切换配色，也可由
  系统主题即时驱动，无需手动设置。
- **分步表单向导**：按 Provider 的 `steps` 渲染步骤导航，逐字段编辑；
  `上一步` / `下一步` 在步骤间移动，最后一步的按钮显示为 `完成 ✓`。
- **实时预览**：左侧编辑，右侧实时显示序列化后的产物；输入防抖 150ms。
- **内联校验**：预览区底部显示“配置有效”或“N 个校验问题”，并把诊断
  挂到对应字段上。
- **表驱动的字段 Widget**：内置六种字段类型各对应一个默认 Widget——
  `string`（文本输入）、`integer`（数字输入）、`boolean`（复选框）、
  `mapping`（键值对表格）、`document`（拖拽/内联文本编辑器）、`tree`
  （递归树编辑器）。`choices` 字段渲染为下拉选择框。
- **树编辑器（`tree`）**：结构模式支持任意层级增删字段/项、切换类型
  string/number/boolean/object/array/null、嵌套（`往里`）与批量添加；
  文本模式可直接输入 JSON/YAML。批量添加是根节点工具栏里的 `批量添加`
  开关，展开后出现输入栏，`Enter` 或 `确认` 提交，`✕` 取消；逗号（中英文）
  分隔多个 `key` 或 `key=value`，值会自动识别 number/boolean/null。
- **文档编辑器（`document`）**：拖拽/点击上传 `.json`/`.yaml`/`.yml` 文件，
  或直接编辑文本（载入示例、格式化、清空）。
- **导入文件**：顶部按钮上传文档，通过 `/api/parse` 反向解析并回填表单。
- **加载预设**：为 `custom`/`json`/`env` 提供内置示例数据。
- **全部清空**：重置当前 Provider 的表单内容。
- **草稿保存**：每次编辑写入 `localStorage["devconfig_draft_<provider>"]`，
  切换 Provider 或刷新后自动恢复。若草稿是空上下文（`{}` 或仅含一个空
  `document`），会被视为“无草稿”，从而回退显示 Provider 的起始示例数据，
  不会被陈旧的清空状态遮住。
- **保存到磁盘**：弹出目标目录输入框，通过 `/api/export` 写入并返回保存
  的文件列表。
- **复制**：把预览内容复制到剪贴板。
- **快捷键**：`Cmd/Ctrl + Enter` 下一步（最后一步显示完成提示），
  `Cmd/Ctrl + S` 保存到磁盘。
- **输出格式开关**：YAML / JSON。XML 按钮是预留入口，点击只弹出
  “即将支持”提示，不会切换格式。
- **汉堡侧边栏**：左上角 `☰`（三条线）打开侧边栏，提供 GitHub 仓库、
  文档站点、问题反馈与邮箱的快捷链接；点击遮罩、`✕` 或按 `Esc` 收起，
  链接均以新标签页打开。

## 安全边界

Web 工作台按“仅本机”设计：

- **仅回环**：`Host` 头不是 `127.0.0.1`、`localhost`、`::1`（或空）的请求
  直接返回 `403 {"error": "forbidden host"}`，用于缓解 DNS rebinding；
- **导出沙箱**：`/api/export` 的目标目录必须等于或位于 `workspace_root`
  （默认当前目录）之内，否则返回 `400`；
- **不缓存页面**：`/` 与 `/index.html` 返回 `Cache-Control: no-store, ...`，
  JSON 接口返回 `Cache-Control: no-store`；
- **无外部资源**：页面不引用任何 CDN 或远程资源。

## HTTP API

所有接口仅接受本机请求。请求体必须是 UTF-8 编码的 JSON 对象；错误统一返回
`{"error": "<message>"}` 和 `400`（未知路由返回 `404`）。

### GET /api/providers

返回当前注册表中的 Provider 名称列表。

```json
{ "providers": ["custom", "env", "json"] }
```

### GET /api/schema

返回 `[step.as_dict() ...]`。默认 Provider 为 `custom`；未知 Provider 返回
`400`。

```bash
curl 'http://127.0.0.1:8848/api/schema?provider=env'
```

### GET /api/widgets

返回 Provider 通过可选方法 `web_ui_widgets()` 声明的自定义 WebUI Widget。
默认 Provider 为 `custom`；未知 Provider 返回 `400`。未声明 Widget 的
Provider 返回空对象（行为与之前完全一致）。

```json
{
  "provider": "singbox",
  "widgets": {
    "node-editor": "(ctx) => { const el = document.createElement('div'); /* ... */ return el; }"
  }
}
```

前端在加载 schema 前先调用该接口，把返回的工厂函数注册进同一张 Widget 表；
求值失败或返回非函数时回退到该字段类型的内置 Widget。

### POST /api/validate

请求：

```json
{ "provider": "env", "context": {} }
```

响应：

```json
{
  "valid": false,
  "diagnostics": [
    { "field": "variables", "message": "variables must not be empty", "severity": "error" }
  ]
}
```

`provider` 默认 `custom`，`context` 默认 `{}`；未知 Provider 返回 `400`。

### POST /api/generate

请求：

```json
{ "provider": "custom", "context": { "document": { "app": { "name": "web" } } }, "format": "yaml" }
```

响应：

```json
{
  "artifacts": [
    {
      "name": "custom.yaml",
      "content": "app:\n  name: web\n",
      "media_type": "application/yaml"
    }
  ]
}
```

- `format` 默认 `yaml`；字符串产物（如 `.env`）原样返回，结构化产物按媒体
  类型序列化为字符串；
- 校验失败返回 `400`；
- 该接口不写文件，仅返回内容用于预览。

### POST /api/export

与 `/api/generate` 相同的请求字段，外加 `output_dir`：

```json
{
  "provider": "custom",
  "context": { "document": { "a": 1 } },
  "format": "json",
  "output_dir": "."
}
```

成功响应：

```json
{ "success": true, "saved": ["/abs/path/custom.json"] }
```

`output_dir` 相对 `workspace_root` 解析；越界返回 `400`。

### POST /api/parse

把 JSON/YAML 文本解析为上下文，用于文件上传和文本模式编辑：

```json
{ "content": "app:\n  name: parsed-svc\n" }
```

```json
{ "context": { "app": { "name": "parsed-svc" } } }
```

`content` 必须是字符串；解析失败返回 `400`。

## Provider 自定义 Widget

字段渲染是查表驱动的：内置 `string` / `integer` / `boolean` / `mapping` /
`document` / `tree` 六种类型各对应一个默认 Widget，注册在
`DEFAULT_WIDGET_FACTORIES`，启动时由 `registerDefaultWidgets()` 写入
`WidgetRegistry`。Provider 可实现可选方法 `web_ui_widgets()`，把某个
`field.type` 映射到一段 JavaScript 工厂源码，从而在不改动前端文件的前提下
引入全新字段类型（或覆盖内置类型）。

```python
class MyProvider:
    name = "mydomain"

    def web_ui_widgets(self):
        return {
            "node-editor": (
                "(ctx) => {"
                "  const el = document.createElement('div');"
                "  el.className = 'node-editor';"
                "  return el;"
                "}"
            )
        }
```

### 工厂上下文 `ctx`

工厂接收一个 `ctx` 参数，返回一个 DOM 元素（即该字段的 `.form-group`
内容）：

- `ctx.field`：当前 `ProviderField`（含 `name`、`type`、`default`、
  `choices`、`i18n` 等）；
- `ctx.fid`：字段名转义后的 id 片段；`ctx.grp`：容器元素；
- `ctx.provider`：当前 Provider 名称；
- `ctx.existing`：字段当前值；
- `ctx.setValue(v)` / `ctx.setFormData(next)`：写回并触发草稿保存与实时预览；
- `ctx.getFormData()` / `ctx.rerender()`：读取整份表单 / 重绘当前步骤。

### 回退与隔离

- 只接受同源 `/api/widgets` 返回的代码；Widget 代码由 Provider 作者负责，
  加载失败会在控制台报错并回退到内置 Widget；
- 某个 `field.type` 未注册任何 Widget 时，统一回退到 `string` 的默认 Widget；
- 切换 Provider 时会先恢复默认 Widget 表（`resetWidgets()`），再注册新
  Provider 的 Widget；
- 未实现 `web_ui_widgets()` 的 Provider 行为完全不变。

`WebUIWidgets` 协议（`devconfig_gen.models`，并已从包根导出）仅作文档性
声明，不强制继承。

## Python 入口

```python
from devconfig_gen import run_web_ui

run_web_ui(
    host="127.0.0.1",
    port=8848,
    open_browser=False,
    workspace_root=".",
)
```

`run_web_ui` 阻塞运行，直到 `Ctrl+C`；`registry` 参数可注入自定义
`ProviderRegistry`。测试可以直接实例化
`devconfig_gen.web_ui.WebUIRequestHandler`，通过类属性 `registry` 和
`workspace_root` 注入自定义注册表与沙箱目录（`tests/test_web_ui.py` 即采用
这种方式）。
