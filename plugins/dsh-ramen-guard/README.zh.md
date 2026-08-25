# dsh-ramen-guard

[English](README.md) | 中文

> [!IMPORTANT]
> **非官方社区集成。** 本项目由 ramen-ai 社区独立开发和维护，未经 DeepSeek
> 审核、推荐或支持。使用任何第三方插件前，请自行评估其安全性。详见
> [DeepSeek Harness 插件专区规则](https://github.com/deepseek-ai/deepseek-harness/discussions/2004)。

<p align="center">
  <img src="../../assets/ramen-logo.png" alt="ramen-ai" width="100"/>
</p>

<p align="center"><strong>在意图变成行动之前，保护 DeepSeek Harness 工具执行。</strong></p>

`dsh-ramen-guard` 是一个故障关闭（fail-closed）的
[Cordis](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-primer.zh.md)
插件。它会在 DeepSeek Harness 工具执行之前，通过 ramen-ai 语义防火墙评估工具调用。
插件拦截官方 `tools/pre-execute` waterfall，将已解析的工具名称和参数交给
`@ramen-ai/node-core`，并且只有在 verdict 允许且 Ed25519 收据已在本地验证后，
才会继续执行。

DeepSeek Harness 可以赋予自主代理真实的 shell、代码、数据和 API 操作能力。
本插件在模型自身推理之外增加一道独立的语义策略门禁。在默认的强制执行模式中，
违反策略的调用会在产生副作用前被阻止；允许的调用只有携带与已评估工具意图绑定、
并经过本地验证的收据，才会继续进入后续 Cordis guard 链。审计模式明确为非阻止模式。

需要 **Node.js 24 或更高版本**。已针对 DeepSeek Harness
`@deepseek-ai/cordis@4.0.1` 和 `@deepseek-ai/dsh-tools@0.1.1-rc.2` 测试。

---

<p align="center">
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/langchain-python">
    <img src="https://img.shields.io/badge/LangChain-1C3C3C?style=flat&logo=langchain&logoColor=white" alt="LangChain"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/pydantic-ai">
    <img src="https://img.shields.io/badge/PydanticAI-E92063?style=flat&logo=pydantic&logoColor=white" alt="PydanticAI"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/mcp-proxy">
    <img src="https://img.shields.io/badge/MCP-6B21A8?style=flat&logo=anthropic&logoColor=white" alt="MCP"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/agt-typescript">
    <img src="https://img.shields.io/badge/Microsoft%20AGT-0078D4?style=flat&logo=microsoft&logoColor=white" alt="Microsoft AGT"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/github-action">
    <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat&logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/cmcp-python">
    <img src="https://img.shields.io/badge/cMCP-00A67E?style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyTDIgN2wxMCA1IDEwLTV6TTIgMTdsOCA0VjExbC04LTR6TTE0IDIxbDgtNFYxMWwtOCA0eiIvPjwvc3ZnPg==&logoColor=white" alt="cMCP"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/mlflow-python">
    <img src="https://img.shields.io/badge/MLflow-0194E2?style=flat&logo=mlflow&logoColor=white" alt="MLflow"/>
  </a>
  &nbsp;
  <a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/ramen-data-filter">
    <img src="https://img.shields.io/badge/ramen%20data%20filter-D97706?style=flat&logo=pandas&logoColor=white" alt="ramen data filter"/>
  </a>
  &nbsp;
  <img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
</p>

---

## 为什么值得使用？

具备真实操作能力的代理，可能把一条被操纵的指令变成 shell 命令、数据库变更、
云资源操作或支付请求。工具一旦执行，仅记录日志已经太晚。`dsh-ramen-guard`
把策略判断放在最后一个仍可安全阻止动作的时刻：DeepSeek Harness 已解析工具调用，
但工具函数尚未产生副作用。

- **在执行前阻止。** 对已解析的 `{ tool, arguments }` 意图执行策略，而不是事后补救。
- **使用语义策略，而不只是字符串匹配。** 当所选 policy 或 bundle scope 覆盖相关风险时，
  配置的 ramen-ai 策略可以识别编码 payload、委婉表达或间接措辞。
- **边界不可用时故障关闭。** 在强制执行模式中，超时、格式错误的响应、取消或无法验证的
  收据都不能静默授权动作。
- **要求执行具备加密证据。** allow 响应只有包含与已评估意图绑定、并经过本地验证的
  Ed25519 收据，才能到达工具；边界故障则使用固定的 unavailable 原因拒绝调用。
- **保留纵深防御。** 允许的调用通过 `next()` 继续，因此本 guard 会补充而不是绕过
  后续 Cordis 策略。

---

## 你能绕过它吗？

标准安全过滤器可以识别基础语法，却难以识别编码后的 payload 和企业话术。
欢迎使用官方 **[Red Team Guide](../../RED_TEAM_GUIDE.md)** 中的零日规避向量，
测试我们的语义防火墙。

下图模拟 Grok/Bankr 攻击：对抗性 prompt 以“视觉障碍”为社会工程包装，
把一条 3,000,000,000 DRB 转账指令编码为摩尔斯电码。防火墙理解其真实语义，
在执行前拦截未授权转账，并生成经过验证的 Ed25519 收据。

<p align="center">
  <img src="../../assets/grok-bankr.png" alt="ramen-ai 在执行前拦截 Grok/Bankr 摩尔斯电码攻击" width="720"/>
</p>

---

## API 密钥

使用本集成前，请在以下页面为**托管推理 Enterprise 账户**获取 ramen-ai API 密钥：
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

本版本尚未公开 Free Starter 和 Professional BYOK 套餐所需的 provider-key 配置。
使用仅支持 BYOK 的账户可能会收到 `402 Payment Required`，强制执行模式会拒绝该请求。

请把 ramen-ai 密钥存放在环境变量中，并通过 Cordis 配置解析。不要把真实密钥直接写入
`cordis.patch.yml` 或提交到源代码仓库。

```bash
export RAMEN_API_KEY=ramen_ak_...
```

插件不会隐式读取环境变量。下方配置使用 Cordis 官方的 `!!js` loader 表达式，
在加载时把环境变量传给 `apiKey`。

---

## 安装

### npm 发布后安装

DeepSeek Harness 会把 `dsh plugin` 的包管理操作转发到所选 profile：

```bash
dsh plugin --profile web add @ramen-ai/dsh-ramen-guard@0.1.0
```

### 从本仓库安装

```bash
cd plugins/dsh-ramen-guard
npm install
npm run build
npm pack

dsh plugin --profile web add /absolute/path/to/ramen-ai-dsh-ramen-guard-0.1.0.tgz
```

如果你运行的不是 `web` profile，请替换为实际 profile 名称。

---

## 配置

在所选 profile 的 `cordis.patch.yml` 中添加插件。该文件通常位于
`${DSH_HOME:-$HOME/.dsh}/profiles/<profile>/cordis.patch.yml`：

```yaml
- insert:
    - id: dsh-ramen-guard
      name: '@ramen-ai/dsh-ramen-guard'
      config:
        apiKey: !!js process.env.RAMEN_API_KEY
        bundleIds: ['ramen__shield_core_it']
        mode: enforce
```

必须提供至少一个非空的 `bundleIds` 或 `policyIds` 数组，也可以同时提供两者。
配置无效或缺失时，插件会加载失败，而不是启动一个未受保护的边界。

### 强制执行模式

`mode: enforce` 是默认值，也是生产安全边界。出现以下任一情况时，工具调用会被拒绝：

- ramen-ai 返回阻止 verdict；
- 评估请求失败、超时或被取消；
- 响应格式无效；
- 加密收据缺失或无法在本地验证。

基础设施或收据失败会确定性返回：

```text
ramen ai execution boundary unavailable
```

本插件不存在 fail-open 配置。

### 审计模式

只有在明确需要观察策略结果、但不把 ramen-ai 作为强制门禁时，才使用 `mode: audit`：

```yaml
- insert:
    - id: dsh-ramen-guard-audit
      name: '@ramen-ai/dsh-ramen-guard'
      config:
        apiKey: !!js process.env.RAMEN_API_KEY
        policyIds: ['<POLICY_UUID>']
        mode: audit
```

审计模式会记录允许、拒绝、不可用和未验证结果，然后继续执行 Cordis 策略链。
Harness 中的其他 guard 仍然可以拒绝调用。

### BYOK 账户兼容性

当前插件配置公开 ramen-ai `apiKey`，但尚未公开 provider key。需要 BYOK provider key
的 ramen-ai 账户可能收到 `402 Payment Required`；强制执行模式会把该响应视为拒绝。
本版本请使用托管推理的 Enterprise 账户。不要把 provider 凭据放入工具参数或受版本控制的配置。

---

## 快速开始

1. 导出 `RAMEN_API_KEY`。
2. 把 package 安装到 DeepSeek Harness profile。
3. 添加上方 `dsh-ramen-guard` insert。
4. 重启 profile；如需检查组合后的配置，可运行：

```bash
dsh --profile web --dump-config
dsh web
```

插件激活后，所有进入官方 `tools/pre-execute` waterfall 的工具调用，
都会在工具函数运行前完成评估。

---

## 使用场景示例

### 保护编码与运维代理

在 shell、文件系统、数据库、Kubernetes、云平台或部署工具前增加策略边界。
例如，可在底层工具运行前拒绝破坏性命令、不安全的生产环境变更或权限提升。

### 防止密钥和数据外泄

评估已经解析到工具调用中的目标地址和 payload。策略可以拒绝把 API key、凭据、
源代码、客户记录或其他敏感数据发送到未批准端点的尝试。

### 保护财务与管理工作流

在转账、支付、账户管理或访问控制工具执行前，要求 ramen-ai 返回允许 verdict。
当代理能够执行具有真实资金或权限后果的动作时，这道边界尤其重要。

### 为高风险工作流增加可验证控制

对每个特权工具调用应用标准 ramen-ai bundle 或显式 policy ID。allow 响应只有在其收据
已在本地针对所评估的工具意图完成验证后，才能到达工具。

### 首日不阻断，逐步上线策略

先使用 `mode: audit` 观察 verdict 并调优策略，同时让所有调用继续进入 Cordis 链。
准备好启用真实边界后，再显式切换到 `mode: enforce`。审计模式本身永远不会阻止调用。

> [!NOTE]
> 本插件只评估进入 `tools/pre-execute` 的已解析工具名称和参数。它不会直接扫描源文档
> 或 prompt，也无法治理 Harness 工具 pipeline 之外执行的动作。

---

## 工作原理

```text
DeepSeek 模型提出工具调用
             |
             v
   tools/pre-execute waterfall
             |
             v
 JSON { tool, arguments } intent payload
             |
             v
 @ramen-ai/node-core evaluateCompliance()
             |
             v
 ramen-ai verdict + 本地 Ed25519 验证
        |                         |
 已验证且允许              阻止 / 不可用 /
        |                   收据缺失
        v                         |
     next()                       v
 后续 Cordis 策略          { kind: 'deny', reason }
        |
        v
 工具函数可以执行
```

对于已验证且允许的调用，listener 会调用 `next()`，因此不会绕过任何后续 Harness 策略。
已验证的阻止 verdict 会返回 evaluator 的 steering 原因。在强制执行模式中，
评估或收据失败永远不会进入工具函数。

---

## API 参考

### Cordis exports

| Export | 说明 |
|---|---|
| `name` | 稳定的插件显示名称：`dsh-ramen-guard`。 |
| `inject` | 要求 Harness `tools` service。 |
| `Config` | Cordis loader 使用的 Schemastery validator。 |
| `apply(ctx, config)` | 注册 `tools/pre-execute` listener 并创建 `RamenClient`。 |
| `BOUNDARY_UNAVAILABLE_REASON` | 评估不可用或无法验证时使用的稳定拒绝原因。 |

### 配置字段

| 字段 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `apiKey` | 是 | — | ramen-ai API 密钥。通过 `!!js` 从 `RAMEN_API_KEY` 解析。 |
| `bundleIds` | 二选一 | `[]` | 每次工具调用使用的 bundle slug。 |
| `policyIds` | 二选一 | `[]` | 显式 policy UUID；可与 bundle 同时使用。 |
| `mode` | 否 | `enforce` | `enforce` 或显式的非阻止 `audit`。 |
| `baseUrl` | 否 | SDK 默认值 | ramen-ai API base URL override。 |

发送给 SDK 的 intent：

```json
{
  "tool": "shell",
  "arguments": { "command": "rm -rf /" }
}
```

SDK 还会收到 `context.tool_name`，用于策略和审计上下文。

---

## 运行测试

```bash
cd plugins/dsh-ramen-guard
npm install
npm run typecheck
npm test
npm run build
```

隔离的 Vitest 测试使用 mock Cordis context 和 mock `RamenClient`，
不发送网络请求，也不需要凭据。覆盖配置验证、已验证的 allow/deny、steering、
transport 失败、取消、收据缺失或无效、payload 结构以及审计模式 delegation。

---

## 可用 bundles

| Bundle slug | 覆盖范围 |
|---|---|
| `ramen__shield_core_it` | 破坏性执行、基础设施滥用、prompt 泄漏、jailbreak、密钥外泄和间接 prompt injection。 |
| `ramen__eu_ai_act_baseline` | 欧盟 AI 法案中的禁止行为、数据治理和透明度控制。 |

自定义策略请使用显式 `policyIds`。Bundle 和 policy 详情见
[ramenai.dev/pricing](https://ramenai.dev/pricing)。

---

## 限制

- DeepSeek Harness 仍处于 developer preview，plugin API 可能发生破坏性变更。
  已测试的 peer 版本固定在 `package.json` 中。
- 每次工具执行前都会增加一次网络往返。
- 审计模式仅用于可观测性，不构成执行边界。
- 当前版本尚未公开 ramen-ai BYOK provider-key 配置。
- 本插件只治理进入 Harness 工具 pipeline 的调用，不治理 pipeline 之外或其他进程中的动作。
- 这是非官方社区集成。DeepSeek 不审核或推荐其策略行为、安全保证或发布流程。
