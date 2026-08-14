# AGENTS.md

本文件用于指导 AI Coding Agents 在本项目中读取、分析和修改代码。

在处理任何业务功能前，请优先阅读：

1. `AGENTS.md`（本文件：怎么工作）
2. `README.md`（项目是什么）
3. `docs/CODE_INDEX.md`（代码在哪里）
4. `docs/CHANGELOG_AI.md`（为什么这么改、当前状态、最近 Handoff）

---

## Project

Stockgood 是单团队库存工具：订单 + 明细行 → 进库 → 在库合箱 → 出库批次 → 签收。  
前端主要是 `frontend/src/App.tsx` 单页多 Tab；顾客入口为 `/apply`、`/me`。  
后端 FastAPI：`backend/app/main.py` 路由，业务在 `backend/app/services/`。  
SQLite：生产 `backend/data/stockgood.sqlite`，影子库 `backend/data/stockgood.shadow.sqlite`。

工作区根目录是 `stockgood/`。Git 仓库可能在上一级 `good-bate1.0.01/`。

---

## Code Navigation

本项目使用统一 FEATURE 标记定位业务功能：

`FEATURE: XXXXX`

完整列表与调用链见 [`docs/CODE_INDEX.md`](docs/CODE_INDEX.md)。

当用户要求修改一个业务功能时：

1. 确定对应 FEATURE（可在 `docs/CODE_INDEX.md` 顶部目录查找）。
2. 阅读该 FEATURE 章节。
3. 根据索引确定相关：前端页面 / API / 后端接口 / 业务逻辑 / 模型 / 数据库 / 测试。
4. **优先只读取相关文件。**
5. 不要无理由扫描或修改整个项目。
6. 大文件（`App.tsx`、`api.ts`、`main.py`）内用 `FEATURE:` 注释跳转，不要拆文件。

推荐搜索顺序：

1. `FEATURE: XXXXX`
2. `docs/CODE_INDEX.md`
3. `docs/CHANGELOG_AI.md`（同一 FEATURE 的历史决策）
4. API endpoint
5. 函数名
6. 组件名
7. 数据模型
8. 数据库表

---

## Modification Workflow

修改之前：

1. 找到 FEATURE。
2. 阅读 CODE_INDEX 与调用链。
3. 确认影响范围。
4. 按 [Reasoning Effort Guidance](#reasoning-effort-guidance) 选择最低合理 Effort。
5. 再改代码。

修改之后：

1. 检查相关调用方。
2. 确认 API 兼容。
3. 确认数据库操作范围（unittest 用临时 sqlite；冒烟写操作只用影子库）。
4. 运行相关测试 / 冒烟。
5. 查看 Git diff，确认没有改无关代码。
6. 可交付改动同步 `CHANGELOG.md` 与版本号（`VERSION`、`backend/app/main.py`、`frontend/package.json`）。
7. 较大任务结束前做 [Context Checkpoint](#context-checkpoint)。

文档同步（只更新真正受影响的文件，不要机械改四个文件）：

```text
修改代码
↓
确认调用关系是否变化
↓
如果代码位置 / API / 数据库关系变化 → 更新 docs/CODE_INDEX.md
↓
如果业务行为 / 设计决策变化 → 更新 docs/CHANGELOG_AI.md
↓
如果 AI 工作规则变化 → 更新 AGENTS.md
↓
如果项目整体使用方式变化 → 更新 README.md
```

若新增页面、API、后端模块、数据模型或 FEATURE，检查是否需要更新 `docs/CODE_INDEX.md` 与 README 导航表。  
若只是修 bug、改算法、调样式、改内部实现且调用关系不变，不必机械更新文档。

---

## Safety Rules

未经用户明确允许：

- 不删除文件或现有代码。
- 不清空数据库；不删除表/字段；不执行 destructive migration。
- 不在生产库写入测试数据（`STOCKGOOD_DB_MODE=production` / `stockgood.sqlite`）。
- unittest 必须走 `STOCKGOOD_DATABASE_PATH` 临时文件，不要写共享影子库 `stockgood.shadow.sqlite`。
- 会改变实际库存的操作：先影子库验收，用户确认后再动实库。
- 不强制覆盖用户现有代码。
- 不执行 `git reset --hard` 或会丢失未提交代码的 Git 操作。
- 不进行大规模重构；不升级主要框架；不引入不必要依赖。
- 用户未要求改 UI 布局/文案/控件位置时，只改逻辑与数据层。

如果操作可能造成数据或代码丢失：停止并请求用户确认。

---

## Scope Control

用户说 `修改 FEATURE: XXXXX` 时，默认只改该 FEATURE 的直接相关代码。  
必须改其他 FEATURE 时，先说明原因和影响范围。  
不要「顺手优化」其他模块。

---

## Existing Code

优先遵循现有代码风格和架构。不要因为个人偏好更换框架、数据库、目录结构，或重写正常工作的模块。

主界面是 `App.tsx` 内 Tab，没有独立的 `OutboundBatchPage.tsx` 一类路由文件。

---

## Uncertainty

无法确认接口调用方、字段用途、函数是否仍在使用、业务规则时：不要猜测。写 `未确认`，继续搜代码；仍无法确认再问用户。

已知未接线（代码存在、前端未调用；**不是必须立刻补上的 bug**）：

- `POST /api/auth/change-password`（规范第 8 节待实现；现码仍为旧定金流程）
- `GET /api/order-requests/{request_id}`（员工列表多用列表接口）
- `POST /api/shipments` 通用建单（进库 UI 走 `POST /api/orders/{id}/inbound`）

客户侧拍板规则见 `docs/client-product-rules.md`。第 8 节（`/me` 改密、凭证截图、员工二次确认、未登录不可看公开列表等）是**已确定但未落地的新行为**，现码为**旧行为**。不要当成现有 bug 擅自修改；等用户明示开始实现。

未经用户明确要求：**不执行 git commit**。不要把文档/导航规划说成已实现的产品功能。涉及 `shipments` 重建表时：关外键前必须先 commit；不要补写已省略的事故恢复细节。

---

## Context Recovery

不要假设当前聊天包含完整项目历史。

在开始较大的修改任务前，优先阅读：

1. `AGENTS.md`
2. `README.md`
3. `docs/CODE_INDEX.md`
4. `docs/CHANGELOG_AI.md`

如果任务涉及某个具体 FEATURE：

1. 在 `CODE_INDEX.md` 找到 FEATURE
2. 在 `CHANGELOG_AI.md` 搜索该 FEATURE 的历史记录
3. 再读取实际代码

这样可以避免因为对话上下文压缩或新开会话而丢失历史设计背景。

---

## Do Not Trust Chat Memory Alone

聊天上下文可能被压缩、截断或丢失。

任何长期重要信息都应该写入项目文件，而不是只存在聊天中。

包括：

- 业务规则
- 设计决策
- 特殊兼容要求
- 用户长期要求
- 已知风险
- 未完成任务

如果这些信息只存在于当前对话，并且会影响未来开发，请在任务完成前写入：

`docs/CHANGELOG_AI.md`

必要时同步更新：

- `AGENTS.md`
- `README.md`
- `docs/CODE_INDEX.md`

不要把大量临时调试信息写入长期上下文（一次性 console.log、临时测试数据、npm 安装输出、已解决且无历史价值的小问题）。

原则：

```text
记录决策，不记录流水账。
记录原因，不复制整段代码。
记录风险，不堆日志。
```

---

## New Agent Session Startup

当这是一个新的 Agent / Codex 会话，或者上下文可能不完整时：

先不要直接修改代码。

按照以下顺序恢复项目上下文：

### Step 1

读取 `AGENTS.md`，了解工作规则。

### Step 2

读取 `README.md`，了解整体项目结构。

### Step 3

读取 `docs/CODE_INDEX.md`，了解 FEATURE 和代码位置。

### Step 4

读取 `docs/CHANGELOG_AI.md`（含 Current Development State 与最近一条 Session Handoff），了解历史修改和设计原因。

### Step 5

根据当前任务，只读取相关 FEATURE 的代码。按 [Reasoning Effort Guidance](#reasoning-effort-guidance) 选择最低合理 Effort（上下文不足时先恢复，不要直接升到 Extra High）。

### Step 6

向用户简要说明已经找到：

- 对应 FEATURE
- 主要相关文件
- 相关历史修改

然后再开始修改。

用户可能直接说：

```text
这是新会话，请读取 AGENTS、CODE_INDEX 和 CHANGELOG_AI，然后继续上次未完成工作。
先看最近一次 Session Handoff，然后继续开发。
先恢复项目上下文，再处理 FEATURE: INV_EXPORT。
```

---

## Context Checkpoint

完成一个较大的功能开发、Bug 修复或架构修改后，在结束任务前执行一次 Context Checkpoint。

检查：

1. 是否产生新的重要业务规则？
2. 是否产生新的设计决策？
3. 是否改变 FEATURE 调用链？
4. 是否存在新的已知风险？
5. 是否有未完成事项？
6. 是否有未来 Agent 容易误解的代码？
7. 是否有只存在当前聊天、但未来仍需要的信息？

如果有，更新 `docs/CHANGELOG_AI.md`（含 Current Development State；阶段未完则追加 Session Handoff）。  
必要时更新 `docs/CODE_INDEX.md`。然后再结束任务。

较大任务完成后的标准顺序：

```text
Code Check
↓
Test
↓
Git Diff
↓
CODE_INDEX Check
↓
CHANGELOG_AI Check
↓
Current State Check
↓
Session Handoff（如任务未完全结束）
```

不要每次改一行代码都更新 Current State。只在大功能完成/开始、重要 bug 出现或解决、工作未完成、开发方向改变时更新。

---

## Incomplete Context

如果发现：

- 用户说「继续刚才的功能」，但当前会话没有完整历史
- 某段代码明显存在历史兼容逻辑
- CHANGELOG_AI 提到旧决策
- 当前代码和直觉设计不一致

不要立即重写。

先：

1. 搜索 `docs/CHANGELOG_AI.md`
2. 搜索 `FEATURE: XXXXX`
3. 检查 Git 历史（如有必要）
4. 查看相关调用方
5. 再判断是否应该修改

不要因为不知道历史原因就删除看起来「多余」的逻辑。

---

## Reasoning Effort Guidance

处理任何开发任务前，先判断完成该任务所需的**最低合理** Reasoning Effort。

可选：`Low` / `Medium` / `High` / `Extra High`

核心原则：用能够可靠完成当前任务的最低合理档，而不是默认最高档。兼顾正确率、修改安全性、速度、额度与上下文消耗。

与本文件其它规则一起用：Code Navigation、FEATURE、CODE_INDEX、CHANGELOG_AI、Context Recovery、Safety Rules、Modification Workflow。

冲突时：

- **Safety Rules 优先**于本规则
- **用户当前明确指令优先**于本规则
- 新会话或上下文压缩时：先 Context Recovery，再判断 Effort；**不要因为聊天历史缺失就直接 Extra High**

判断在内部完成。不要向用户输出复杂度评分表。用户只需：

```text
Effort 建议：Medium
```

必要时补一句理由。High 是正式开发的默认档；用户已长期用 High 时，普通 High 任务可不重复提醒。

Agent **不能**自行切换 Cursor UI 档位。禁止声称「已切换到 High / 已开启 Extra High」。正确说法是「建议使用 Extra High」。用户未切换时，仍可继续当前能安全完成的分析；高风险复杂修改若当前推理明显不足，先说明风险，不要假装已升级。

### 档位

**Low** — 问题与位置都明确、单文件或极少文件、无复杂业务/调用链/数据库/复杂 API、失败影响很小。例如：改按钮文案、提示语、颜色、简单 CSS、常量、拼写、明确配置。不得用于：数据库、API 行为、订单核心、金额、库存、权限、导入导出核心、多文件业务（即使只改一行）。

**Medium** — 需求明确、基本在单个 FEATURE、约 1～3 个主要文件、调用简单、Bug 位置基本确定。例如：表单校验、筛选、普通 CRUD、明确 Bug、单组件/单函数、简单 API 字段、简单状态判断。CODE_INDEX 已能定位到少数文件时用 Medium，不必因「还没打开过」升档。

**High** — 正式项目开发的主要默认档。多文件、前后端联动、API、数据库读写、导入导出、一个 FEATURE 的完整修改、需追踪调用链、需测、需查多个调用方。例如：改 INV 导出、费用计算、库存处理、接口参数/返回结构、完整新功能、普通跨文件 Bug。

**Extra High** — **不作为默认档**。仅当确实需要更深层分析：根因未知且大范围排查、多 FEATURE 耦合、多层历史兼容、数据一致性/并发/事务/Race、无法稳定复现、大规模架构、High 已合理尝试仍未解决、需大量 Git 历史才能理解。不要因为「文件很多」自动 Extra High——若 CODE_INDEX 已写清调用链，8 个文件的 FEATURE 通常 High 足够。

目标使用比例（不要机械追求）：Low 少量，Medium 较多，High 最常用，Extra High 少量。

### 决策顺序

```text
先用 CODE_INDEX / CHANGELOG_AI 缩小范围
↓
判断真实复杂度（代码规模 × 业务复杂度 × 失败影响）
↓
选择最低合理 Effort
↓
执行；发现复杂度变化则升级或降级
```

问题明确且位置明确且局部简单 → Low  
问题明确、单 FEATURE 常规开发 → Medium  
问题明确但跨模块 / 或 CODE_INDEX 无法快速收窄 → High  
问题不明确且根因未知且跨多 FEATURE / 数据层 / 并发 → Extra High  

收到 `修改 FEATURE: XXXXX` 时：先 CODE_INDEX → CHANGELOG_AI → 确认文件 → 再判断 Effort。不要先全仓库扫描。

### 向用户提示

- **Low**：`Effort 建议：Low。这个任务范围很小，Low 足够。` 若当前像在用更高档：`当前任务只需要 Low，可以降档节省推理消耗。` 然后继续，不等待确认。
- **Medium**：`Effort 建议：Medium。这个任务属于常规局部开发，不需要 High。` 若当前像 High / Extra High：`这个任务 Medium 足够，可以降档。` 然后继续。
- **High**：可只写 `Effort 建议：High`。
- **Extra High**：必须说明原因，例如：`Effort 建议：Extra High。原因：根因未知，且涉及多个 FEATURE、后端调用链和数据库状态。` 若用户可能不在 Extra High：`建议切换到 Extra High 后进行完整排查。`

### 动态升级 / 降级

初始档不是永久决定。允许 Low→Medium→High→Extra High，也允许反向降级。不要因为开头用了高档就整段任务一直用高档。

- Low→Medium：不止一处、出现业务逻辑、额外调用方、多文件。提示：`实际范围比预期更大，建议从 Low 升到 Medium。`
- Medium→High：前后端 / API / 数据库 / 多重要文件联动 / 需完整调用链。提示：`实际涉及多个模块，建议从 Medium 升到 High。`
- High→Extra High（任一重要条件）：High 下连续两次合理修复仍失败；根因仍未知；冲突数据源；复杂历史兼容；多 FEATURE 强耦合；事务/并发/Race；无法稳定复现；改 A 持续弄坏 B；需大量 Git 历史；架构与最初理解明显不同。提示：`当前问题复杂度已经超过普通 High。建议切换到 Extra High 后继续。原因：……`

降级：

- Extra High→High：根因/调用链/方案已明确，剩余是正常编码。`复杂分析已经完成。剩余工作属于明确代码修改，可以从 Extra High 切回 High。`
- High→Medium：实际只改单模块、API/库不变、范围明确。`影响范围已经确认，后续 Medium 足够。`
- Medium→Low：只剩文案/样式/一个常量/简单收尾。`剩余任务很简单，可以切到 Low。`

### 失败不要立刻升档

第一次失败：先检查是否理解错需求、读错文件、遗漏调用方、测试方法错误。  
第二次合理方案仍失败：再升档（如 Medium→High）。  
High 多次失败且涉及复杂系统行为：再考虑 Extra High。  
禁止为了「保险」全程 Extra High。简单任务用 Extra High 只会增加延迟和额度，收益不明显。

### 风险与类型（不得只看行数）

一行 `if amount > 0` 若决定付款/退款/库存/财务，不能因为短而用 Low，至少 Medium / High。

| 类型 | 通常档位 |
|---|---|
| 简单只读查询 | Medium |
| 普通 CRUD / Schema / Migration / 普通事务 | High |
| 数据一致性 / 并发 / 事务异常 | Extra High |
| Bug 根因已明确（如变量名写错） | Low / Medium |
| 大概知道模块、不知具体位置 | Medium / High |
| 完全不知原因但范围局限 | High |
| 不稳定、跨模块、偶发 | Extra High |
| 简单 UI 新功能 | Medium |
| 单 FEATURE 完整新功能 | High |
| 跨多 FEATURE 大型新功能 | High；仅真正要复杂架构设计时 Extra High |
| 小范围函数整理 | Medium |
| 单模块重构 | High |
| 跨项目架构重构 | Extra High |
| 编辑 README / CODE_INDEX / AGENTS / CHANGELOG_AI | Low / Medium |
| 扫描全项目才能建准确映射 | High |
| 需理解复杂架构与大量历史决策 | Extra High |
| 测试已直接指出错误 | Medium / High |
| 测试随机失败 / 并发 / 无法复现 / 多模块同时失败 | 考虑 Extra High |

### 最终原则

不用 Extra High 做本可由 Medium 完成的事，也不用 Low 冒险处理本应由 High 深入分析的核心业务。
