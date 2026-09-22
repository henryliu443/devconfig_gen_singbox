# 交互式终端向导（init）

`devconfig_gen_singbox init` 提供纯终端的引导式配置流程，适合无头服务器、SSH 会话
或终端优先的工作流。它完全由 Provider 的声明式 `steps` 驱动，不包含任何
生成逻辑，也不依赖 Web 工作台或浏览器。

```text
usage: devconfig_gen_singbox init [-h] [--provider PROVIDER] [--input INPUT]
                          [--output-dir OUTPUT_DIR] [--format {json,yaml}]
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--provider` | `custom` | 向导使用的 Provider |
| `--input` | 无 | 预填向导的现有配置文件（根需为映射） |
| `--output-dir` | `.` | 产物输出目录 |
| `--format` | 无 | 指定 `json`/`yaml` 后跳过输出格式提问 |

## 流程

1. 校验 Provider 是否存在；不存在时打印 `Error: unknown provider ...` 并返回
   `1`；
2. 读取 Provider 的 `steps`；没有声明式步骤时提示并返回 `1`；
3. 如果传入 `--input`，加载该文件并把其中的映射合并进当前答案（非映射会
   警告并忽略；读取失败会警告但不中断）；
4. 逐步骤、逐字段提示输入；
5. 调用 `diagnose_request` 校验。若存在 error，打印错误并询问是否带着已有
   答案重新运行（`[Y/n]`，默认是）；回答 `n` 则中止并返回 `1`；
6. 校验通过后选择输出格式（`1: YAML [default]`，`2: JSON`），除非
   `--format` 已指定；
7. 通过 `engine.generate` 写出产物，并打印每个产物的绝对路径。

向导界面文案（步骤标题、字段提示）使用 Provider 元数据中的规范英文
`title`/`description`；内置 Provider 的 `i18n` 中文翻译供 Web 工作台使用，
向导本身不渲染 `i18n`。

## 字段提示类型

| `ProviderField.type` | 提示方式 |
| --- | --- |
| `string` | 文本输入；空输入使用默认值；`required` 且无默认值时不允许为空；有 `choices` 时列出编号选项，可输入编号或选项名（不区分大小写） |
| `integer` | 整数输入；显示 `min`/`max` 提示；非法输入或越界会重新提示 |
| `boolean` | `[Y/n]` 或 `[y/N]`；接受 `y/yes/true/1` 与 `n/no/false/0` |
| `mapping` / `dict` | 逐行输入 `key=value`，空行结束；已有值会显示并保留 |
| `document` / `tree` | 先询问 JSON/YAML 文件路径；路径有效则加载文件内容，否则回退到 `key=value` 映射输入 |

其他类型按 `string` 处理。

注意：`key=value` 输入（以及 `document`/`tree` 的回退输入）中的值始终按
**字符串**保存。例如输入 `port=8080` 会生成 `port: "8080"`。需要保留
整数、布尔等类型时，请先用 `--input` 传入文件，或在 Web 工作台中编辑。

## 示例会话

```text
$ devconfig_gen_singbox init --provider custom --output-dir generated
========================================================
  DevConfig-Gen Interactive Wizard: 'custom'
  Answer the prompts below. Press Enter to use defaults.
========================================================

--- [1/1] Custom document ---
  Build any nested JSON/YAML structure; add, remove, or clear nodes at any level.
? document (load document file or enter entries):
    Path to JSON/YAML file (or press enter for key=value input): 
? document (enter key=value pairs, press enter on empty line to finish):
    key=val (or empty to finish): name=web
    key=val (or empty to finish): 
Validating configuration...
[✓] All validations passed!

Select output format (1: YAML [default], 2: JSON): 1
Writing configuration to 'generated'...
[✓] Generated artifact: /path/to/generated/custom.yaml
```

使用 `--input examples/custom.yaml` 可直接预填并保留文件中的类型：

```text
? document (load document file or enter entries):
    Path to JSON/YAML file (or press enter for key=value input): examples/custom.yaml
    [✓] Loaded document from examples/custom.yaml
```

## 校验失败后的重试

```text
[!] Validation found errors:
  - app.path: app.path must start with '/'
Re-run the wizard to correct these? [Y/n]: y

Re-running wizard with your previous answers pre-filled...
```

重试会保留所有已输入答案（包括已加载的文档），只需修正有问题的字段。
如果输入流提前结束（EOF），向导打印
`[!] Input ended before '<field>' was provided. Aborting.` 并返回 `1`。

## 退出码

| 退出码 | 场景 |
| --- | --- |
| `0` | 成功生成产物 |
| `1` | 未知 Provider、无声明式步骤、用户中止、输入结束、生成失败 |

## Python 入口

```python
from devconfig_gen import run_interactive_wizard

code = run_interactive_wizard(
    "custom",
    input_path="examples/custom.yaml",
    output_dir="generated",
    output_format="yaml",
)
```

函数还接受 `context=`（初始答案）、`registry=`（自定义注册表）、
`reader=`/`writer=`（用于测试的文本流）。返回值即退出码。
