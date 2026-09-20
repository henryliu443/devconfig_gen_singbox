# HANDOFF — sing-box Provider 接入（给下一个 Agent）

> 本文件是**可执行交接单**。执行对象：子仓库 `DevConfig-Gen_SingBox`
> （本地路径 `/Users/henry/DevConfig-Gen_SingBox`）。
> 详细需求见子仓库 `FUTURE_PLAN_SINGBOX.md`；本文件是它的执行入口与护栏。
> 状态：父仓库侧已完成；**子仓库侧待执行**。

---

## 0. 一页速览

| 项 | 值 |
|---|---|
| 父仓库（upstream） | `DevConfig-Gen` — https://github.com/henryliu443/DevConfig-Gen |
| 子仓库（本任务） | `DevConfig-Gen_SingBox` — https://github.com/henryliu443/DevConfig-Gen_SingBox（私有） |
| 本地子仓库路径 | `/Users/henry/DevConfig-Gen_SingBox` |
| 父仓库当前版本 | v1.1.0（已发布 PyPI / Release / Pages） |
| 两仓库同起点 | `c2f097c` |
| 本任务目标 | 在子仓库实现 `providers/singbox/`，测试全绿，产物确定 |
| 铁标准 | 父仓库 `PROVIDER_STANDARD.md` |

---

## 1. 仓库关系与执行顺序

```
parent (DevConfig-Gen)  →  child (DevConfig-Gen_SingBox)  →  downstream (A-repo, 退役中)
```

- 父仓库拥有中立核心与标准；**领域 provider 只存在于子仓库**。
- **不要**在父仓库加 sing-box 领域代码；**不要**分叉/改写中立核心。
- 核心更新从 `upstream` 合入，不在子仓库重新实现 engine/formats/validation。
- A-repo（`Automated-sing-box-json-generator`）**只读参考**，本阶段**不碰**。

---

## 2. 已完成（父仓库）

- `PROVIDER_STANDARD.md`：铁标准 + 「WebUI Widget 扩展」章节。
- `AGENTS.md`：父/子/下游关系与红线。
- WebUI 全链路 pluggable：`WidgetRegistry`、可选 `web_ui_widgets()`、
  `GET /api/widgets`、`WebUIWidgets` 协议。
- v1.1.0 已发布；143 测试全绿；`docs/` 文档站与落地页已上线。

---

## 3. 硬性护栏（先读，违规=返工）

1. **零副作用**：provider 不读环境变量、不写 state、不调子进程生成凭据。
2. **凭据即输入**：`subdomain_prefixes`、`auth.*`、密钥全部显式传入 context。
3. **无版本追逐**：sing-box 上游变化只改对应 `plugins/<variant>.py`。
4. **确定性**：同输入连跑两次 byte-for-byte 一致（JSON/YAML 双格式）。
5. **不做第二套扩展体系**：只通过 Provider 扩展。

> **禁止（等用户起床确认后再做）**：任何 DNS-01 / ACME 证书签发、
> Cloudflare DNS 写操作、真实网络请求、部署、服务管理、凭据生成。
> 本阶段**只跑离线测试与烟雾**。如任务需要真实域名/证书/网络，**停下来等用户**。

---

## 4. 任务清单

### P0 — 子仓库就绪（先做）
- [ ] 确认 `upstream` remote 已配置（应已存在）：
  `git remote -v` → `upstream https://github.com/henryliu443/DevConfig-Gen.git`；
  若缺失：`git remote add upstream https://github.com/henryliu443/DevConfig-Gen.git`。
- [ ] 确认身份已修正：子仓库 `AGENTS.md` / `README.md` 声明「本仓库是**子仓库 child**」（应已修正，核对即可）。
- [ ] 基线自检：`PYTHONPATH=src python3 -m unittest discover -s tests -v` → 143 全绿。

### P1 — 实现 singbox provider（核心工作）
按 `FUTURE_PLAN_SINGBOX.md` 第 3–8 节建：

```
src/devconfig_gen/providers/singbox/
├── __init__.py          # 导出 SingBoxProvider
├── provider.py          # 校验 / 分派 / 组装（不含变体字段细节）
├── schema.py            # Context Schema + 结构校验
├── models.py            # ProtocolConfig / RoutingConfig …
├── plugins/
│   ├── __init__.py      # 插件注册表
│   ├── base.py          # ProtocolPlugin Protocol + 通用工具
│   ├── anytls.py
│   ├── tuic.py
│   └── hysteria2.py
├── route.py             # DNS + Route 组装（读 data/rules.json）
├── links.py             # 分享链接聚合
└── data/
    └── rules.json       # 内嵌规则数据（Path(__file__).parent 加载）
```

- [ ] 注册到 `default_registry`（子仓库 `registry.py`，2 行）。
- [ ] Context Schema 见 `FUTURE_PLAN_SINGBOX.md` 第三节；WireGuard 整体不要。
- [ ] 产物契约：
  - `sing-box.server.{json,yaml}`（`target != client`）
  - `sing-box.client.{json,yaml}`（`target != server`）
  - `sing-box-links.txt`（`target != server`，`text/plain`，可选）
- [ ] `diagnose`/`validate` 用 `validation.py`，诊断路径 dotted path。

### P2 — 测试与示例
- [ ] `tests/test_singbox_provider.py`：
  - schema 校验（缺字段、类型错误、未知 protocol type、非法 `tunnel_mode`）；
  - 每个 plugin 的 server inbound / client outbound / share link 结构快照；
  - `target=server|client|both` 的 artifact 集合与命名；
  - 双格式（JSON/YAML）连跑两次 byte-for-byte 一致。
- [ ] `examples/singbox.yaml` 示例输入。
- [ ] 子仓库 `CHANGELOG.md` 新条目；`ARCHITECTURE.md` 记录 provider 与 `data/*.json` 约定。
- [ ] 子仓库 `README.md` 增加 singbox provider 输入示例。

### P3 — 收尾
- [ ] 全量测试 + 烟雾全绿（见第 6 节）。
- [ ] 提交（commit）；**不要**推送到父仓库；子仓库推送需用户确认。
- [ ] 汇报：产物快照、测试数量、烟雾轮次、遗留决策。

---

## 5. 烟雾测试（自己跑几轮）

子仓库已带脚本：`scripts/smoke_rounds.py`

```bash
cd /Users/henry/DevConfig-Gen_SingBox
python3 scripts/smoke_rounds.py 8      # 建议 8 轮
```

每轮三查：全量单测 + API/CLI/WebUI 产物逐字节一致 + 前端 JS 在 DOM stub 下执行。
要求 **8 轮全 PASS**。Node 缺失时前端检查自动跳过（本机有 node）。

---

## 6. 验收准则

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` 全绿；
- 同输入连跑两次输出 byte-for-byte 一致（JSON/YAML 双格式）；
- `target=server|client|both` 产物集合与命名正确；
- provider 输出与目标行为结构等价（golden 快照）；
- 核心零改动（除 `registry.py` 注册 2 行）。

---

## 7. 开放决策（需用户拍板，先按推荐做并标注）

1. 多选字段：**推荐父仓库加通用 `list`/`multiselect` 类型**（走父→子）；暂可先用逗号分隔 string，由 provider 归一化。
2. 子仓库是否发布独立包：**推荐否**（仅内部/CI）。
3. A-repo：**本阶段不动**（B1/B2 之后再说）。
4. 父仓库下次版本：v1.2.0（无破坏性变更时）。

---

## 8. 明确不做

- 不碰 A-repo；不碰父仓库领域逻辑；不引入第二套扩展体系；
- 不读环境变量、不生成凭据、不调 `sing-box` 子进程；
- **不做 DNS-01 / 证书 / 网络 / 部署**（等用户起床）。

---

## 9. 常用命令

```bash
# 同步父仓库核心到子仓库
cd /Users/henry/DevConfig-Gen_SingBox
git fetch upstream && git merge upstream/main

# 测试 / 烟雾
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/smoke_rounds.py 8

# CLI 冒烟
PYTHONPATH=src python3 -m devconfig_gen.cli providers
```
