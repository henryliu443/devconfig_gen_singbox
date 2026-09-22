# 安装与快速开始

## 环境要求

- Python 3.8 或更高版本（CI 覆盖 3.8–3.14，Linux 与 macOS）；
- 运行时零第三方依赖；
- 可选：安装 PyYAML 以获得完整 YAML 支持。未安装时使用内置 YAML 子集
  解析器/序列化器（支持边界见[格式支持与产物](formats.md)）。

## 安装

### 方式一：从仓库安装（开发模式）

```bash
git clone https://github.com/henryliu443/devconfig_gen_singbox.git
cd devconfig_gen_singbox
pip install -e ".[yaml]"     # 可选：安装 PyYAML
```

安装后可直接使用 `devconfig_gen_singbox` 命令。

### 方式二：从 PyPI 安装

发布工作流会在推送 `v*` 标签时构建并发布到 PyPI：

```bash
pip install devconfig_gen_singbox            # 运行时零依赖
pip install "devconfig_gen_singbox[yaml]"    # 可选 PyYAML
```

### 方式三：不安装，直接运行

```bash
PYTHONPATH=src python3 -m devconfig_gen.cli --help
```

下文示例使用已安装的 `devconfig_gen_singbox`；未安装时把该命令替换为
`PYTHONPATH=src python3 -m devconfig_gen.cli` 即可。

## 验证安装

```bash
devconfig_gen_singbox --version   # devconfig_gen_singbox 2.1.8
devconfig_gen_singbox providers      # 输出四行：custom、env、json、singbox
```

当前版本为 **2.1.8**。使用面包括稳定的 **CLI**、**Python API**、**终端向导**
（`devconfig_gen_singbox init`）与**本地 Web 工作台**（`devconfig_gen_singbox ui`），并在父仓库的
中立核心之上新增 `singbox` 领域 Provider。

## 第一个产物（3 分钟）

仓库自带示例输入 `examples/custom.yaml`：

```yaml
app:
  name: checkout-api
  version: "2.4.0"
  port: 8080
  environment: production
  replicas: 3
  labels:
    team: payments
    tier: backend
  health_check:
    path: /healthz
    interval_seconds: 15
    timeout_seconds: 5
```

生成 YAML 配置：

```bash
devconfig_gen_singbox generate \
  --provider custom \
  --input examples/custom.yaml \
  --output-dir generated \
  --format yaml
# 终端输出：generated generated/custom.yaml
```

只校验、不写文件：

```bash
devconfig_gen_singbox validate --provider custom --input examples/custom.yaml
# 终端输出：examples/custom.yaml: valid
```

生成 `.env`：

```bash
devconfig_gen_singbox generate --provider env --input examples/vars.yaml --output-dir generated
# 终端输出：generated generated/.env
cat generated/.env
# DATABASE_HOST=localhost
# DATABASE_PORT=5432
# DATABASE_NAME=appdb
# DEBUG=true
# LOG_LEVEL=info
```

查看 Provider 的声明式字段/步骤（JSON）：

```bash
devconfig_gen_singbox schema --provider env
```

多输入合并与覆盖：

```bash
devconfig_gen_singbox generate \
  --provider custom \
  --input configs/base.yaml \
  --input configs/prod.json \
  --set app.port=9090 \
  --output-dir generated --format yaml
```

## sing-box 领域 Provider

```bash
devconfig_gen_singbox validate --provider singbox --input examples/singbox.yaml
devconfig_gen_singbox generate --provider singbox --input examples/singbox.yaml \
  --output-dir generated --format yaml
# generated/sing-box.server.yaml
# generated/sing-box.client.yaml
# generated/sing-box-links.txt
```

产物集合由 context 中的 `options.target`（`server` / `client` / `both`）决定。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功（`generate` 写出产物、`validate` 通过） |
| `1` | 校验失败 |
| `2` | 输入或用法错误（未知 Provider、文件不存在、格式错误、`--set` 语法错误、产物名越界） |

## 下一步

CLI 是主要使用面，建议按此顺序继续：

- [CLI 命令参考](cli.md) — 每个命令、参数、`--input`/`--set` 与退出码；
- [CLI 配方](cli-cookbook.md) — 分层配置、管道输入、批量生成、CI 门禁；
- [输入合并与覆盖](input-and-merge.md) — 多源合并语义；
- [格式支持与产物](formats.md) — JSON/YAML 边界与产物命名。

编程集成与扩展：

- [Python API](python-api.md)
- [Provider 参考与开发](providers.md)
