# 开发与测试

## 项目结构

```text
devconfig_gen_singbox/
├── src/devconfig_gen/          核心包（见 docs/index.md 模块地图）
│   ├── providers/              custom / json / env 内置 Provider
│   │   └── singbox/            sing-box 领域 Provider（本仓库新增）
│   └── py.typed                类型标记
├── tests/                      unittest 测试套件
├── examples/                   示例输入（custom.* / vars.yaml / singbox.yaml）
├── docs/                       本技术文档（MkDocs 源）
├── mkdocs.yml                  MkDocs + Material 站点配置
├── ARCHITECTURE.md             架构与设计决策
├── PROVIDER_STANDARD.md        Provider 铁标准（白皮书，父仓库拥有）
├── CHANGELOG.md                版本变更记录
├── pyproject.toml              PEP 517/621 打包配置
└── .github/workflows/          CI / 文档 / 发布流水线
```

## 运行测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

已安装到当前环境时也可直接：

```bash
python -m unittest discover -s tests -v
```

测试套件不需要 PyYAML：默认走内置 YAML 子集解析器/序列化器；
PyYAML 分支在源码中以 `# pragma: no cover` 标注，不作为 CI 的必需路径。

### 测试文件与覆盖范围

| 文件 | 覆盖内容 |
| --- | --- |
| `test_formats.py` | JSON/YAML 解析与序列化、格式检测、`coerce_scalar`、媒体类型 |
| `test_validation.py` | 校验辅助函数、`ValidationError`、`Diagnostic` 序列化 |
| `test_devconfig_core.py` | `json` Provider 持久化、注册表、产物名越界拒绝 |
| `test_custom_provider.py` | `custom` 的任意结构、上下文解包、命名与媒体类型 |
| `test_env_provider.py` | `env` 的扁平化、标量转换、诊断、`.env` 持久化 |
| `test_singbox_provider.py` | `singbox` 的 Schema 校验、各 plugin 构建、`target` 产物、双格式确定性、CLI |
| `test_merge.py` | `deep_merge` 规则、多输入顺序、`--set` 语义 |
| `test_provider_metadata.py` | `ProviderStep`/`ProviderField`、`i18n`、`diagnose` 降级、内置注册 |
| `test_cli_e2e.py` | 以子进程方式端到端执行各 CLI 子命令与退出码 |
| `test_api_parity.py` | CLI 与 Python API 产物逐字节一致 |

运行单个测试文件：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_env_provider.py' -v
```

## CI

`.github/workflows/ci.yml` 在 push、pull request 和手动触发时运行：
Ubuntu 与 macOS 双平台 × Python 3.8–3.14 矩阵，执行
`PYTHONPATH=src python -m unittest discover -s tests -v`。

## 打包

```bash
pip install -e ".[dev]"    # 安装 build / wheel / PyYAML
python -m build            # 生成 dist/*.whl 与 dist/*.tar.gz
```

- 包名：`devconfig_gen_singbox`，导入名：`devconfig_gen`；
- 控制台脚本：`devconfig_gen_singbox = devconfig_gen.cli:main`；
- 运行时依赖为空；可选依赖 `yaml`（PyYAML）、`dev`（构建工具）与
  `docs`（`mkdocs-material`）；
- 版本同时出现在 `pyproject.toml` 与 `src/devconfig_gen/__init__.py` 的
  `__version__`；CLI `--version` 直接读取 `__version__`，因此发布时两处需
  保持一致（测试 `test_version_matches_package_version` 会校验 CLI 与包
  版本一致）。当前版本为 `2.1.3`。

## 文档站点（GitHub Pages）

`docs/` 目录通过根目录 `mkdocs.yml`（MkDocs + Material 主题）发布为项目文档
站点，Markdown 文件本身仍是唯一内容来源，发布地址为
<https://henryliu443.github.io/DevConfig-Gen/>。本地构建：

```bash
pip install -e ".[docs]"     # 安装 mkdocs-material
mkdocs build --strict        # 输出到 site/（已加入 .gitignore）
mkdocs serve                 # 本地预览 http://127.0.0.1:8000
```

- 导航在 `mkdocs.yml` 的 `nav` 中定义；
- 标题锚点使用 `pymdownx.slugs.slugify`（保留中文），因此文档中的
  `文件.md#中文锚点` 链接在站点内依然有效；
- 构建开启 `--strict`：文档内失效链接会直接导致构建失败。

### 发布分支与锁定

文档不通过 `main` 发布，而是走专用分支 `docs`：

- `.github/workflows/docs.yml` 只在推送到 `docs` 分支且改动
  `docs/**`、`mkdocs.yml`、`pyproject.toml` 或工作流自身时触发；
- `build` 与 `deploy` 两个 job 都带有
  `if: github.ref == 'refs/heads/docs'`，因此即使在其它分支手动
  `workflow_dispatch` 也不会构建或部署；
- 构建步骤先 `pip install -e ".[docs]"`，再执行 `mkdocs build --strict`，
  并把 `site/` 作为 Pages 产物上传；
- `permissions` 只申请 `contents: read`、`pages: write`、`id-token: write`，
  且 `concurrency: pages` 保证同一时间只有一次发布。

仓库设置侧的锁定（无法写入代码，需在 GitHub 上配置一次）：

1. **分支保护**：Settings → Branches，为 `docs` 添加保护规则（禁止直接
   push、要求 PR/审查/状态检查），使文档改动只能经评审合入；
2. **环境限制**：Settings → Environments → `github-pages`，在
   Deployment branches 中只允许 `docs`，避免其它分支触发部署；
3. **Pages 来源**：Settings → Pages → Source 选择 “GitHub Actions”。

本地开发与预览不需要任何部署权限。

## 发布

`.github/workflows/release.yml` 在推送 `v*` 标签（或手动指定 tag）时：
检出代码 → 构建 sdist/wheel → 创建/覆盖 GitHub Release → 通过 PyPI
Trusted Publishing（OIDC）发布。发布操作只在 CI 中执行；本地开发不需要
配置任何凭据。

## 开发约定

来自 `AGENTS.md` 的项目约束：

- 不要向核心引擎添加网络、部署、服务管理、凭据或系统修改行为；
- CLI 保持“薄”：只调用 `devconfig_gen.engine` 的共享流水线，不重复实现生成逻辑；
- 保持输出确定性：JSON/YAML 保留插入顺序，产物逐字节稳定；
- 每个行为变更都要有测试；完成前运行完整测试套件；
- 公共 API、CLI、格式或 Provider 契约变化时，同步更新 `README.md` 与
  `ARCHITECTURE.md`；
- 未经明确要求，不发布包、不创建 Release、不推送远端。

## 文档维护

- `docs/index.md` 是文档总入口与能力清单，按“CLI 优先”的顺序组织；
- CLI 是主要使用面：命令/参数变化时更新 `docs/cli.md`，并同步
  `docs/cli-cookbook.md` 中受影响的配方；
- 新增/修改 Provider、格式行为、合并语义时，更新对应主题页
  （`providers.md`、`formats.md`、`input-and-merge.md`）；
- 架构或设计决策变化时更新根目录 `ARCHITECTURE.md`，并同步
  `docs/architecture.md` 的摘要；
- `docs/cli.md` 的命令/参数应与 `devconfig_gen_singbox <command> --help` 保持一致，
  可直接用该命令核对。
