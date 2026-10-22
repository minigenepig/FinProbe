# mcp_erp_readme.md

面向采购到付款（P2P）的 Multi-Agent 风控系统。本仓库当前交付 **Mock ERP HTTP API + MCP Tool + Agent Skills**。

## 你需要先建立的正确分层

你举例里的 `curl.exe -H "X-Api-Key: ..." http://localhost:8081/...` 是对的，但那是 **ERP**，不是 MCP。

```
Agent / Skill  --MCP协议-->  mcp-server  --HTTP+API Key-->  mock-erp  --JSON-->  data/
     调查剧本                  Python 工具适配器              模拟真实 ERP 接口
```

1. **mock-erp**：假装公司里的 ERP。给它发的是普通 REST，和以后接 SAP/Oracle 的方式一样。你可以（也应该）用 curl 验收。
2. **mcp-server**：给大模型用的工具层。工具函数内部用 Python `httpx` 调 mock-erp，**不要让 Agent 自己拼 curl**，也不要让 MCP 直接读 JSON 文件。以后把 `ERP_BASE_URL` 换成真实 ERP 即可。
3. **Skills**：告诉 Agent 查什么、怎么分析根因、怎么做消解、怎么分级。Skill 不是数据接口。

你给的 TypeScript `server.registerTool('financial_analysis', ...)` 思路完全正确。本项目语言是 Python，所以对等写法是 FastMCP 的 `@mcp.tool(name="financial-analysis")`，沙箱执行的是 **Python 统计代码**（不是 JS）。大模型动态生成 `result = {...}` 的脚本，沙箱只允许数学和集合操作。

## 大结果怎么返回（不要把 74 张发票塞进模型）

查询类工具统一采用：

- **summary**：规则生成的统计（金额合计、税率分布、重复发票、一票多付等）
- **sample / data**：最多几条样例；小于阈值则全部内联
- **artifact**：完整结果写到 `.tmp/finprobe-artifacts/art_xxx.json`
- 后续用 `financial-analysis(artifactIds=[...])` 做聚合，或 `artifact-get` 再看几条

这是给 Agent 用的正确契约：模型看到摘要，程序保留全量。

## 启动

终端 1（必须先起 ERP）：

```powershell
pip install -r requirements.txt
python mock-erp/server.py
```

健康检查：

```powershell
curl.exe http://127.0.0.1:8081/health
curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/invoices?supplierId=VEN-0121&page=1&pageSize=5"
```

终端 2 / MCP 宿主以 stdio 拉起工具层：

```powershell
python mcp-server/server.py
```

把根目录 `mcp.json` 配进 Cursor/Codex MCP 设置即可。

## MCP 工具

| 工具 | 作用 |
| ---- | ---- |
| vendor-query | 供应商主数据 |
| po-query | 采购订单，可附 5 日拆单聚类 |
| gr-query | 入库单；供应商全量用 supplierId |
| invoice-query | 发票 |
| payment-query | 付款单 |
| approval-query | 审批（消解检查必用） |
| policy-query | 企业制度 |
| financial-analysis | 沙箱统计；允许 try/except、isinstance；禁止 import/type()，必须 result=... |
| artifact-get | 按需读取 artifact 若干条 |

鉴权头：`X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f`  
ERP 端口：`8081`

## Skills（`skills/`）

规划表中的技能均已落地。每个 `SKILL.md` 统一为：目标、执行步骤、规则、输出格式、示例、边界。调查类 Skill 发现异常后必须继续分析根因并做审批消解，输出带字段说明的结构化 JSON。


- supplier-profile-audit-skill
- supplier-relation-audit-skill
- internal-policy-qa-skill
- p2p-three-way-match-skill
- split-order-audit-skill
- payment-audit-skill
- payee-account-security-skill
- general-query-skill
- evidence-validation-skill
- risk-report-generator-skill

制度正文在 `internal-policy-qa-skill/references/policies.md`，也通过 `policy-query` 从 mock-erp 读取。


## Python 环境创建记录

```
python -m venv finprobe_env
.\finprobe_env\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

启动后端：
```
.\finprobe_env\Scripts\Activate.ps1
python -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000
```

启动前端：
```
.\finprobe_env\Scripts\Activate.ps1
cd src/frontend
% npm install 
npm run dev
```