# Codex Research & Delivery Skills

两套可独立安装、跨项目复用的 Codex 技能：面向结果与证据的软件交付，以及面向数据与机制的机器学习论文深读。

## 技能

| 技能 | 用途 | 入口 |
|---|---|---|
| `evidence-driven-delivery` | 从目标、issue 或已有 change 自动推进 Spec-first 交付；持久化状态、适配目标项目、执行验证与有界修复，仅在真实决策门请求人工输入 | [SKILL.md](skills/evidence-driven-delivery/SKILL.md) |
| `deep-paper-reading` | 从黑盒输入输出深入数据表示、模块契约、数学机制、训练推理、完整追踪与创新实验依据 | [SKILL.md](skills/deep-paper-reading/SKILL.md) |

两个技能均自包含：资源路径相对各自技能目录，不依赖原始开发项目。

```text
skills/
├── evidence-driven-delivery/
│   ├── SKILL.md
│   ├── references/
│   ├── assets/
│   └── scripts/
└── deep-paper-reading/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/
    └── assets/
```

## 安装

克隆仓库，将需要的整个技能目录复制到用户级技能目录：优先使用环境变量 `CODEX_HOME` 下的 `skills`，未设置时使用 `~/.codex/skills`。不要只复制入口文件。

Windows PowerShell 示例（在计划存放本仓库的父目录执行）：

```powershell
git clone https://github.com/Shliey/codex-research-delivery-skills.git
cd codex-research-delivery-skills

$skillsRoot = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $HOME '.codex\skills'
}

New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
foreach ($name in @('evidence-driven-delivery', 'deep-paper-reading')) {
    $destination = Join-Path $skillsRoot $name
    if (Test-Path -LiteralPath $destination) {
        throw "技能目录已存在，请先检查并备份后再更新：$destination"
    }
    Copy-Item -LiteralPath (Join-Path '.\skills' $name) -Destination $destination -Recurse
}
```

仓库为私有时，克隆需要拥有访问权限。安装后在新的 Codex 会话中调用技能。

## 使用

以下输入到 Codex 聊天，不是在终端运行。

### Evidence-driven Delivery

```text
$evidence-driven-delivery 根据当前仓库的要求完成这个目标：……
```

宿主 Agent 负责适配项目、读取仓库规则并推进阶段。目标项目拥有自己的策略、issue 和运行状态；技能包只携带通用控制逻辑与默认契约。审查或解释请求保持只读，不自动转成实施授权。

脚本需要 Python 3.11+，仅使用标准库；完整 Spec-first 交付还需要目标环境可用的 OpenSpec CLI。目标项目的测试、构建与部署依赖由该项目决定。

### Deep Paper Reading

提供论文文件、可访问的链接或原文，并指定模式：

| 模式 | 调用示例 |
|---|---|
| `full`（默认） | `$deep-paper-reading 请用中文完整深读这篇论文。` |
| `overview` | `$deep-paper-reading overview：解释精确输入输出、整体架构和主要创新。` |
| `module` | `$deep-paper-reading module：深入分析本文的量化模块与数据表示。` |
| `trace` | `$deep-paper-reading trace：用一个论文案例追踪所有核心中间数据。` |
| `evidence` | `$deep-paper-reading evidence：核查创新是否得到实验与消融支持。` |

默认中文、完整八阶段；区分论文事实、补充材料、推断和教学示例，未公开细节保持未知。默认不转入环境配置、源码分析或运行复现。LaMoGen 仅作为条件加载的验收案例，不是通用论文模板。

该技能没有硬编码解析工具依赖；具体 PDF、图表或网页读取能力取决于宿主环境。

## 校验与边界

可以用本机 skill-creator 提供的 `quick_validate.py` 分别校验两个目录。中文文件在 Windows 上建议使用 `python -X utf8`。技能包结构校验不等同于行为效果或论文结论被独立验证。

修改交付技能的控制脚本后，在仓库根目录运行：

```powershell
python -X utf8 .\skills\evidence-driven-delivery\scripts\test_delivery.py
```

测试涉及真实的本地 TypeScript、Python 和 OpenSpec 路径；缺少前提时以测试实际输出为准，不能把跳过当成通过。

仓库只包含可复用技能包与仓库说明，不附带用户论文、论文阅读报告、模型权重、凭据、项目运行状态或原项目历史。初始导入保持已安装的两个技能包内容不变。
