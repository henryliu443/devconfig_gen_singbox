# devconfig_gen_singbox 部署与操作实战指南

> 本指南用于明确本项目的**命令行体系**、**服务器落地实战**，以及**“写文档（声明式）”与“交互式（向导问答）”两种模式的区别与协作原理**。

---

## 一、命令体系全貌（统一单命令入口）

本项目在经过统一重构后，**只有唯一一个可执行命令**（与 PyPI 发行名完全一致）：

```bash
devconfig_gen_singbox <子命令> [选项]
```

所有旧名字（如 `devconfig-gen`、`singbox-ops`）已全部废除并统一。子命令按职责分为两大层：

```text
devconfig_gen_singbox
│
├── 【纯配置生成层（纯函数·零副作用）】
│   ├── generate   根据输入配置/文档生成输出产物
│   ├── validate   校验输入配置是否合法，输出错误定位
│   ├── schema     打印 Provider 的字段元数据规范 (JSON)
│   ├── providers  列出系统中注册的可用 Provider
│   ├── init       配置生成终端向导（仅交互生成配置，不碰系统）
│   └── ui         启动本地 Web 可视化配置工作台
│
└── 【服务器运维部署层（Ops·执行系统变更）】
    ├── deploy     执行服务器完整部署（无参数时自动进入交互向导）
    ├── redeploy   重新生成随机凭据并更新部署
    ├── plan       交互式问答并将结果输出为 plan.yaml（只写文档，不部署）
    ├── context    仅组装并打印给 sing-box 的最终上下文数据
    ├── certs      安全检查与修剪冗余的 acme.sh 证书目录
    └── destroy    根据部署状态安全卸载并反向清理系统资源
```

---

## 二、关键概念澄清：“写文档” vs “交互式”

在实际使用中，经常听到“写文档部署”与“交互式部署”，这两者到底有什么区别？到底有没有道理区分？

**答案：有非常本质的区别。这是自动化运维（GitOps / 声明式）与新手友好（向导式 / 命令交互）的核心分岔点。**

| 维度 | 交互式问答模式（Interactive Wizard） | 声明式写文档模式（Document-Driven / Plan） |
|---|---|---|
| **核心形式** | 终端命令行一问一答（Prompt） | 预先编写好一份结构化文件（`plan.yaml`） |
| **触发方式** | `devconfig_gen_singbox deploy`（不加任何文件参数） | `devconfig_gen_singbox deploy --plan plan.yaml` |
| **优势** | **零门槛、零记忆**。不需要提前知道 YAML 语法、不需要查字段名字，敲回车即可使用默认值。适合初次部署、临时测试。 | **完全确定、可复现、可审计**。把整套服务器规格白纸黑字写下来，可以提交到 Git 仓库做版本管理，随时在多台机上重演。 |
| **微观控制能力** | 只能回答预设的问题，无法微调未暴露的深层配置。 | **拥有终极控制权**。例如固定某协议的子域名前缀以复用现有证书、自定义特殊端口、指定防火墙放行规则等。 |
| **缺点** | 每次都需要人工在键盘前敲，无法放入脚本批量化执行。 | 需要使用者对 YAML 结构有基本认识。 |

### 它们如何相互连接？

我们并不强制你在两者之间二选一，而是提供了三座**桥梁**：

1. **直接交互部署**：
   ```bash
   devconfig_gen_singbox deploy
   ```
   *过程*：程序直接向你提问，你在内存中完成规格确定，回车结束后程序立即在服务器上执行部署。**（最快体验）**

2. **交互式帮你“写文档”**：
   ```bash
   devconfig_gen_singbox plan --output my-plan.yaml
   ```
   *过程*：程序像上面一样提问，但问完之后**不碰系统**，而是帮你把一份合法的、美观的 `my-plan.yaml` 写在磁盘上。你随后可以用文本编辑器微调它。**（既要省事、又要留痕）**

3. **文档驱动批量部署**：
   ```bash
   devconfig_gen_singbox deploy --plan my-plan.yaml
   ```
   *过程*：静默、精准、严格按照你文档中规定的参数落地。**（生产标准做法）**

---

## 三、第一步：拿到软件在服务器上怎么部署？

登录你的全新或存量 Linux 服务器（以 root 权限为例），按照以下标准流程推进：

### 步骤 1：安装软件

系统已配置好 Python 3.8+ 环境后，推荐使用 `pipx` 隔离安装：

```bash
pipx install "devconfig_gen_singbox[ops]"
pipx ensurepath
exec bash -l
```

*校验安装*：
```bash
devconfig_gen_singbox --version
# 输出: devconfig_gen_singbox 2.1.5
```

---

### 步骤 2：选择你的部署路径

#### 路径 A：直接交互式向导部署（初学者推荐）

直接敲下 `deploy`，不带 `--plan` 参数：

```bash
devconfig_gen_singbox deploy
```

命令行会依次向你提问：
1. **`主域名 (例: example.com)`**：输入你的根域名（必填）。
2. **`启用协议 [anytls,tuic,hysteria2]`**：直接回车默认三协议全开，或输入子集（逗号分隔）。
3. **`出站模式 none/proxy/tun [proxy]`**：如果服务器上有运行正常的 WARP，选 `proxy`；如果无 WARP 或想纯直连，填 `none`。
4. **`服务器公网 IP (留空=自动探测)`**：回车即可自动从公网探测。
5. **`Cloudflare API Token`**（不回显）：DNS A 记录必填，需要 Zone.DNS 编辑权限。
6. **`Cloudflare Zone ID`**：域名对应的 Zone ID。
7. **`用 acme.sh 自动签发 TLS 证书？ [Y/n]`**：TUIC 和 Hysteria2 需要证书。选 Y 自动调 acme.sh 签发；如果已有证书或打算自己签，选 n。
8. **`启用运行时适配器？ [Y/n]`**：是否自动安装依赖、配置 systemd、加载 nftables 防火墙、部署守护任务。生产部署选 Y。
9. **`输出路径`**：服务端/客户端/链接文件的保存路径，一路回车使用标准默认路径。

> **小技巧**：在执行真实操作前，你可以随时加上 `--dry-run` 查看演练结果而不对服务器产生任何改动：
> ```bash
> devconfig_gen_singbox deploy --dry-run
> ```

---

#### 路径 B：文档驱动部署（精准控制/保留既有配置推荐）

如果你有特定需求（例如：服务器上已有旧证书，必须锁定固定的子域名前缀以防证书域名失效），推荐使用写文档的方式：

1. **准备你的配置文件** `my-plan.yaml`：
   ```yaml
   domain_root: example.com
   server_ip: auto
   protocols: [anytls, tuic, hysteria2]
   tunnel_mode: none              # 若无 WARP 必须设为 none，防止出站死循环

   # 手动锁定前缀（可选，不写则随机生成）
   subdomain_prefixes:
     reality: a1b2c3d4
     tuic: e5f6a7b8
     hy2: c9d0e1f2

   # 协议级参数（可选；不写则用下面这些默认值）
   protocol_params:
     anytls:
       decoy_server: react.dev        # REALITY 伪装站（默认 www.cloudflare.com）
       decoy_port: 443
     hysteria2:
       masquerade: https://react.dev  # HY2 伪装网址（默认 https://www.cloudflare.com）

   adapters:
     secrets: singbox-subprocess  # 调用 sing-box 二进制生成高强度 UUID 与 Reality 密钥
     dns: cloudflare               # DNS 必填：A 记录由 Cloudflare 管理（需 CF_Token / CF_Zone_ID）
     acme: null                   # 设为 null 跳过证书签发，由自己管理
     state: local-json
     runtime:
       packages: debian
       systemd: systemd
       firewall: nftables-basic
       watchdog: warp
       auto_update: auto-update

   outputs:
     server_config: /etc/sing-box/config.json
     client_config: /root/singbox-client.json
     links: /root/singbox-links.txt
   ```

2. **第一步演练（Dry-Run）**：
   ```bash
   devconfig_gen_singbox deploy --plan my-plan.yaml --dry-run
   ```
   观察输出的每一步是否符合预期，产物路径是否正确。

3. **第二步正式生效**：
   ```bash
   devconfig_gen_singbox deploy --plan my-plan.yaml
   ```

---

### 步骤 3：部署后验证与客户端提取

部署完成后，服务器将自动激活服务。运行以下命令验证：

1. **检查服务运行状态**：
   ```bash
   systemctl is-active sing-box
   # 应输出: active
   ```

2. **获取客户端节点分享链接**：
   ```bash
   cat /root/singbox-links.txt
   ```
   里面包含可直接导入手机/桌面客户端的 URI 格式节点（`anytls://...`、`tuic://...`、`hy2://...`）。

3. **获取完整客户端 JSON 配置文件**：
   ```bash
   cat /root/singbox-client.json
   ```
   支持直接导入 sing-box 桌面端或各类 GUI 客户端。

---

## 四、常见维护命令速查

| 需求 | 推荐命令 |
|---|---|
| 快速审阅将要生成的配置（不碰系统） | `devconfig_gen_singbox context --plan plan.yaml` |
| 重新生成全套密码并无缝热更新 | `devconfig_gen_singbox redeploy --plan plan.yaml` |
| 安全清理过期的 acme.sh 冗余证书目录 | `devconfig_gen_singbox certs --keep host1,host2 --apply` |
| 启动网页端配置编辑器 (WebUI) | `devconfig_gen_singbox ui --port 8848` |
| 完整干净卸载服务与防火墙规则 | `devconfig_gen_singbox destroy --plan plan.yaml` |
