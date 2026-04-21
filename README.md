<div align="center">

<img src="./assets/banner.svg" alt="less is more" width="100%"/>

<br/>
<br/>

### 把任何东西变成你的笔记 · 跟你的笔记库对话 · 一切本地，一切可审计

<br/>

[![python](https://img.shields.io/badge/python-3.12+-3776ab?style=flat-square&labelColor=0a0e1a)](./backend/pyproject.toml)
[![react](https://img.shields.io/badge/react-18-61dafb?style=flat-square&labelColor=0a0e1a)](./frontend/package.json)
[![llm](https://img.shields.io/badge/llm-any%20OpenAI--compatible-ff6b35?style=flat-square&labelColor=0a0e1a)](./backend/app/providers)
[![license](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square&labelColor=0a0e1a)](#license)

<br/>

*Your notes stay on your disk. The AI just sits next to them.*

</div>

---

## 它是什么

`more` 是一个**本地优先的 AI 笔记工作区**。

你有一个装满 Markdown 笔记的文件夹 —— `more` 在旁边放了一个**能读、能写、能搜、能记住你偏好**的 AI 代理，把你零散的"输入→思考→输出"流程拼成一条。

它不是一个 ChatGPT 套壳，也不是 Obsidian 插件。它是一个**完整的本地产品**：前端编辑器 + 后端代理 + 检索 + 记忆 + 审批 + 可观测性，一次装好全都有。

---

## 你可以拿它干嘛

### ▸ 把任何东西变成笔记

URL、PDF、长文、粘贴板内容——一句话让 agent 存进来，自动切块、自动索引，之后就能被搜到、被引用。

```text
you: 把 https://arxiv.org/abs/2310.06770 存成笔记
more: ✓ notes/2310.06770-agentbench.md  (14.2 KB · 8 chunks · indexed)
      摘要: AgentBench proposes task-success-rate as the primary metric for ...
```

### ▸ 跟你的整个笔记库对话

Agent 回答前会先搜你的笔记，找到相关段落再作答——每条回答都带 `@文件名` 引用，可点击跳回原文。

```text
you: 我最近笔记里关于 agent 评测的观点都对比一下
more: 在你的 14 条笔记里找到 3 个相关观点:
      ├─ @agentbench.md          task-success-rate 是黄金标准
      ├─ @ragas-eacl2024.md      更关注 faithfulness 而非完成率
      └─ @my-notes/2025-04.md    你自己写过: "只测完成率会放过幻觉"
      结论: 你的看法其实更接近 RAGAS 的立场, 下一步可以...
```

### ▸ 让 agent 代写 / 重构 / 合并笔记

所有文件修改**必须过审批队列**——你先看完整 diff 再决定接不接受，0 意外破坏。

```text
you: 把上面三条合并成一篇对比笔记
more: ⚠ 将新建: notes/eval-methodology-compare.md (2.4 KB)
       + # Agent 评测方法论对比
       + ## AgentBench: task success
       + ...
       [ Approve ✓ ] [ Edit ✏ ] [ Cancel ✗ ]
```

### ▸ 跨会话记住你的偏好

Agent 自己挑出"值得记的"信号（不是贪婪记全部），下次打开照样认识你——可审、可删、可导出。

```text
more remembers:
  · 回复用简体中文
  · 偏好 fastembed 本地 embedding (性能 > 模型精度)
  · 笔记惯用 "技术/" "生活/" "项目/" 三级目录
```

### ▸ 接入外部工具（MCP 协议）

通过 **Model Context Protocol** 接任何 MCP server——日历 / GitHub / Slack / 浏览器 / 你自研的脚本——agent 能调用，一样走审批。

### ▸ 每一步都可回放

对接 Langfuse v4 后，每次对话的每一步（计划、工具调用、检索命中、LLM token）都在 trace 视图里可回放。**奇怪的输出不是靠猜，是靠看。**

---

## 30 秒快速开始

```bash
git clone https://github.com/<you>/more.git && cd more

# backend
cd backend
pip install -e ".[dev,rag]"
cp .env.example .env                       # 填 MORE_LLM_API_KEY
uvicorn app.main:app --reload              # :8000

# frontend
cd ../frontend
npm install && npm run dev                 # :5173 — 开浏览器就能用
```

首次启动会引导你选择一个 workspace 文件夹（或新建一个），之后你的笔记就永远在那个文件夹里，以标准 `.md` 格式保存。卸载 `more` 随时可以，笔记不会绑死。

---

## 核心能力速览

<table>
<tr>
<td width="50%" valign="top">

**◆ Workspace-first**
<br/>打开一个文件夹就能用，笔记是标准 Markdown，永远在你硬盘上，任何编辑器都能打开。

</td>
<td width="50%" valign="top">

**◆ Hybrid Retrieval**
<br/>Lexical 倒排 + 向量 embedding（BGE）+ Reciprocal Rank Fusion 融合，关键词和语义一起命中。

</td>
</tr>
<tr>
<td valign="top">

**◆ Three-tier Memory**
<br/>跨会话记偏好、会话内记 summary、本轮记证据。Agent 既"认识你"也"专注当下"。

</td>
<td valign="top">

**◆ Approval Queue**
<br/>所有写 / 删 / 移操作都先挂起，你看 diff 点确认。不会被 agent 偷偷改坏一整个文件夹。

</td>
</tr>
<tr>
<td valign="top">

**◆ MCP Tool Adapter**
<br/>原生支持 Model Context Protocol，接任何标准 MCP server（或你 10 行代码自己写一个）。

</td>
<td valign="top">

**◆ Langfuse Traced**
<br/>每 turn 挂完整 span 树，session 视图里一次对话折成一次回放。问题诊断不再靠玄学。

</td>
</tr>
<tr>
<td valign="top">

**◆ Skill Library**
<br/>把常用 agent 行为（"帮我润色日记"、"生成周报"）打包成可复用 skill，一条命令唤起。

</td>
<td valign="top">

**◆ Streaming SSE**
<br/>首 token 延迟 p50 = 93ms。不是"等 10 秒突然一大段"，是真的在你眼前打字。

</td>
</tr>
</table>

---

## 这不是什么

| 它不是 | 为什么 |
|---|---|
| **ChatGPT / Claude 网页版** | 你的笔记是你的——不上传、不进训练数据、不依赖厂商账户 |
| **Obsidian + AI 插件** | 不绑任何笔记软件，`.md` 文件 TextEdit / VSCode / vim 都能开 |
| **Cursor / Zed** | 不是写代码的，是**读写知识**的。虽然它也能帮你整理代码笔记 |
| **LangChain / LlamaIndex** | 不是一套 SDK，是一个**拿起来就用的完整产品**，前后端全套 |
| **RAG 玩具 demo** | 不是"嵌入 → 检索 → 生成"三行 notebook，是带记忆、审批、可观测性的工程品 |

---

## 界面

```
┌─────────────┬─────────────────────────────┬──────────────────┐
│  Sidebar    │      Document Hub           │    AgentDock     │
│             │                             │                  │
│  ◆ 工作区   │   [#] 2024-notes.md         │   you>  帮我把   │
│  ├─ 技术/   │                             │         这周的   │
│  │  └─ ... │   # Agent Evaluation        │         开会记录 │
│  ├─ 生活/   │                             │         汇总    │
│  └─ 项目/   │   AgentBench proposes task- │                  │
│             │   success-rate as ...       │   more> ✓ 找到  │
│  ◇ 最近     │                             │         3 篇... │
│             │                             │                  │
└─────────────┴─────────────────────────────┴──────────────────┘
                                              ↑
                                         SSE stream
```

左边是工作区目录树，中间是分 tab 的 Markdown 编辑器，右边是可常驻的对话抽屉。一切为"笔记 + 对话"同屏而生。

> 想要截图？跑起来截一张贴到 `assets/screenshot.png` 即可，README 会自动显示。

---

## 技术栈

<table>
<tr><td valign="top">

**Backend**
- Python 3.12+ · FastAPI · Pydantic
- LiteLLM · 接任何 OpenAI 兼容 API<br/>&nbsp;&nbsp;(OpenAI · Anthropic · DeepSeek · Ollama · vLLM ...)
- FastEmbed（本地 `BAAI/bge-small-en-v1.5`）
- Langfuse v4 + OpenTelemetry
- 自研 ReAct runtime + 3 层 fallback

</td><td valign="top">

**Frontend**
- React 18 · TypeScript 5 · Vite
- Tailwind · shadcn/ui · Radix · cmdk
- Zustand（全局状态）
- react-resizable-panels（可拖 dock）
- SSE streaming 客户端

</td><td valign="top">

**Infra & 生态**
- Docker Compose（可选 Langfuse stack）
- MCP（Model Context Protocol）
- Skills (可复用 agent prompt 包)
- Approval queue（写操作前置审查）
- 本地 Markdown + SQLite · 零外部数据库依赖

</td></tr>
</table>

---

## 为什么你该试试

- **你的知识是你的** · 笔记永远是 `.md` 文件躺在你硬盘上，不用担心哪天服务下线
- **真能用** · 不是 demo，不是 notebook，是真实 workspace 上跑得起来的完整产品
- **真可审** · 每次 agent 动你文件前都要点头；每次 LLM 调用都在 Langfuse 能回放
- **真开放** · MCP 标准协议、OpenAI 兼容 API、标准 Markdown ——换任何组件都不锁死

---

## 设计理念 · less is more

在一个 AI 项目爆炸式增长的时代，大多数仓库都长成了"加了 50 个 feature 的半成品"。`more` 反其道而行：

| 少一样 | 多一样 |
|---|---|
| 少一种抽象 · 一个 coordinator，没有多层 router / supervisor 套娃 | 多一种可读性 · 读完一个文件就懂主循环 |
| 少一种存储 · 本地 Markdown + SQLite，不搞向量数据库 | 多一种信任 · 笔记永远是你自己能打开的纯文本 |
| 少一种 magic · 所有 prompt 在 `PromptTemplateRegistry` 明面放 | 多一种可改造 · 任何一个 prompt / LLM / embedding 都能单独换 |
| 少一种 mock · 评测就是真 LLM 跑真实 workspace | 多一种诚实 · 每个数字单命令可复现 |

> 代码量不是目标，**被审计的正确性**才是。

---

## 未来要做的事

### 产品形态

- [ ] **桌面端一键安装包**（Tauri，Windows / macOS / Linux）
- [ ] **浏览器扩展**：划词 / 整页一键入库，自动生成摘要 + 标签
- [ ] **移动端只读伴侣**（iOS / Android）：离线看笔记 + 快速捕获
- [ ] **知识图谱视图**：note 间关联可视化，可缩放、可按标签过滤
- [ ] **命令面板（Cmd+K）**：任何操作都能键盘唤起

### AI 能力

- [ ] **一键离线 LLM**：内置 Ollama / llama.cpp 适配，隐私场景零网络调用
- [ ] **多模态输入**：图片 OCR · 语音转写 · 剪贴板图片直接识别
- [ ] **多 agent 协作**：研究员 / 编辑 / 归档员 各司其职、互相审查
- [ ] **Self-critique 自审循环**：生成 → 自审 → 修订，幻觉率进一步压低
- [ ] **语义锚点**：永久链接跨重命名幸存，引用永远不断
- [ ] **Agent Skill Marketplace**：社区共享的 Skill 包一键安装

### 协作与同步

- [ ] **多人 workspace**（CRDT）：实时协作编辑，无服务器中心
- [ ] **端到端加密远程同步**：自托管 relay，不经过任何云
- [ ] **单条笔记公开分享**：生成 permalink + 只读链接
- [ ] **Git-based 同步**：用任何 git 仓库做 backup / version history

### 知识管理

- [ ] **RSS / newsletter 订阅归档**：自动抓取 + AI 摘要入库
- [ ] **Daily / Weekly note 自动生成**：从 Git / 日历 / 对话拼周报
- [ ] **导出到 Obsidian / Notion / PDF**：一键迁入迁出，零锁定
- [ ] **自动 wiki 链接**：人物 / 地点 / 项目自动挖出并互链

### 开发者体验

- [ ] **Plugin API**：10 行代码注册一个 agent tool
- [ ] **LLM cost 面板**：每个 workspace 每个 turn 的 token / $ 实时追踪
- [ ] **可插拔 Embedding**：FastEmbed / OpenAI / Cohere / Voyage 一键切换
- [ ] **Public eval leaderboard**：接入后自动跑基准并发布分数

---

## License

MIT — 少说两句，多写点代码。

<br/>

<div align="center">
<sub>Built with the conviction that fewer things, done rigorously, beats many things done loosely.</sub>
<br/><br/>
<sub>◆</sub>
</div>
