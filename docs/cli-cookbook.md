# CLI 配方

面向脚本和自动化的可复制命令。以下配方在 macOS/Linux 的 `bash`/`zsh` 下
验证通过；源码运行时把 `devconfig_gen_singbox` 换成
`PYTHONPATH=src python3 -m devconfig_gen.cli` 即可。

## 分层配置：base + 环境覆盖

```bash
devconfig_gen_singbox generate --provider custom \
  --input configs/base.yaml \
  --input configs/prod.yaml \
  --output-dir dist --format yaml
```

`configs/base.yaml`：

```yaml
app:
  name: checkout
  port: 80
  labels:
    team: payments
```

`configs/prod.yaml`：

```yaml
app:
  port: 9090
```

结果 `dist/custom.yaml`：嵌套映射合并，标量覆盖，未提及的键保留：

```yaml
app:
  name: checkout
  port: 9090
  labels:
    team: payments
```

`--input` 可混用格式，格式按扩展名与内容独立检测：

```bash
devconfig_gen_singbox generate --provider custom \
  --input configs/base.yaml \
  --input configs/prod.json \
  --output-dir dist --name merged.yaml
```

## 用 --set 注入环境相关值

```bash
for env in dev staging prod; do
  devconfig_gen_singbox generate --provider custom \
    --input configs/base.yaml \
    --set app.environment=$env \
    --output-dir dist/$env --name app.yaml
done
```

结果：

```text
dist/dev/app.yaml
dist/staging/app.yaml
dist/prod/app.yaml
```

`dist/prod/app.yaml`：

```yaml
app:
  name: checkout
  port: 80
  labels:
    team: payments
  environment: prod
```

复杂值用单引号包住，避免 shell 展开：

```bash
devconfig_gen_singbox generate --provider custom --input configs/base.yaml \
  --set 'list=[1,2,3]' \
  --set 'obj={"x":1}' \
  --set 'url=http://x?a=b' \
  --output-dir dist --format json
```

## 多环境批量生成

用 shell 循环为每个环境生成独立目录，并用 `--set` 打上环境标记：

```bash
for env in dev staging prod; do
  devconfig_gen_singbox generate --provider custom \
    --input configs/base.yaml \
    --set app.environment=$env \
    --set "build.label=$env-$(date +%Y%m%d)" \
    --output-dir "dist/$env" --name app.yaml
done
```

`--output-dir` 与 `--name` 都支持子目录，因此也可以单条命令写入嵌套路径：

```bash
devconfig_gen_singbox generate --provider custom \
  --input configs/base.yaml \
  --output-dir dist --name envs/prod/app.yaml
```

## 从标准输入或管道读取

CLI 没有内置的 `-` 约定，但 Unix 上可以使用 `/dev/stdin`：

```bash
printf 'app:\n  name: piped\n' | devconfig_gen_singbox validate --provider custom --input /dev/stdin
# /dev/stdin: valid
```

或用进程替换（bash/zsh）：

```bash
devconfig_gen_singbox validate --provider custom --input <(printf 'app:\n  name: proc-sub\n')
```

用 `jq` 动态构造输入：

```bash
jq -n '{app:{name:"jq-app",port:8080}}' \
  | devconfig_gen_singbox validate --provider custom --input /dev/stdin
```

由于 `/dev/stdin` 与 `/dev/fd/*` 没有可识别的扩展名，格式由内容推断：
以 `{` 或 `[` 开头按 JSON 解析，否则按 YAML 解析。

## JSON 与 YAML 互转

```bash
# JSON -> YAML
devconfig_gen_singbox generate --provider custom \
  --input configs/base.json --output-dir converted --name config.yaml

# YAML -> JSON
devconfig_gen_singbox generate --provider custom \
  --input configs/base.yaml --output-dir converted --name config.json
```

输出格式由 `--name` 后缀决定，也可以显式 `--format yaml|json`；显式
`--format` 优先于后缀。

## 生成 .env

```bash
devconfig_gen_singbox generate --provider env \
  --input configs/vars.yaml --output-dir dist --name .env.production
```

```yaml
# configs/vars.yaml
database:
  host: localhost
  port: 5432
  name: appdb
debug: true
```

```env
# dist/.env.production
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=appdb
DEBUG=true
```

注意 `env` Provider 忽略 `--format`，产物始终是 `.env` 文本。

## 在 CI 中做校验门禁

```bash
#!/usr/bin/env bash
set -euo pipefail

# 校验失败时退出码为 1，set -e 会中止脚本
devconfig_gen_singbox validate --provider env --input configs/vars.yaml

# 只在通过后生成
devconfig_gen_singbox generate --provider env --input configs/vars.yaml \
  --output-dir dist --name .env
```

需要机器可读结果时：

```bash
devconfig_gen_singbox validate --provider env --input broken.yaml --json \
  | jq -r '.[] | "\(.field): \(.message)"'
# variables: variables must not be empty
```

注意 `validate --json` 在存在 error 时仍返回退出码 `1`；在 `set -e` 脚本里
要么先捕获退出码，要么用 `|| true` 允许读取输出：

```bash
diagnostics=$(devconfig_gen_singbox validate --provider env --input broken.yaml --json || true)
echo "$diagnostics" | jq -r '.[] | .message'
```

## 用 schema 驱动外部客户端

```bash
devconfig_gen_singbox schema --provider env \
  | jq -r '.[] | .id as $id | .fields[] | "\($id).\(.name): \(.type) required=\(.required)"'
# variables.variables: mapping required=true
```

`schema` 的输出就是 `ProviderStep.as_dict()`，可直接用于生成表单或校验规则。

## 确定性输出与 diff

同一输入、同一环境下，重复生成的结果逐字节一致：

```bash
devconfig_gen_singbox generate --provider custom --input configs/base.yaml \
  --output-dir det1 --format json
devconfig_gen_singbox generate --provider custom --input configs/base.yaml \
  --output-dir det2 --format json
cmp det1/custom.json det2/custom.json && echo "identical"
```

因此产物可以直接提交到版本库，或用 `git diff --exit-code` 检查漂移：

```bash
devconfig_gen_singbox generate --provider custom --input configs/base.yaml \
  --output-dir generated --format json
git diff --exit-code -- generated/custom.json
```

测试套件包含 CLI 与 Python API 产物逐字节一致的断言
（`tests/test_api_parity.py`），可作为该契约的回归保障。

## 常用组合

```bash
# 1) 先看 Provider 需要什么
devconfig_gen_singbox providers
devconfig_gen_singbox schema --provider custom

# 2) 校验所有候选输入
devconfig_gen_singbox validate --provider custom \
  --input configs/base.yaml --input configs/prod.yaml

# 3) 覆盖并生成
devconfig_gen_singbox generate --provider custom \
  --input configs/base.yaml --input configs/prod.yaml \
  --set app.port=9090 \
  --output-dir dist --name prod.yaml
```

## 注意事项

- `--set` 值含 `$`、`!`、空格、`{}` 时务必用单引号，防止 shell 展开或历史
  展开；
- `--set` 不支持数组下标：`a.0=x` 会把 `a` 变成 `{"0": "x"}`，而不是修改
  列表第一项；
- `generate --format` 是输出格式；`validate --format` 是输入格式覆盖；
- `--input` 只接受文件，目录会报 `cannot read ...: Is a directory`；
- 未安装 PyYAML 时，YAML 输入受内置子集解析器限制（顶层流式集合/裸标量、
  Tab 缩进等），详见[格式支持与产物](formats.md)。
