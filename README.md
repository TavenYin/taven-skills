# taven-skills

个人 agent skills。首个 skill：`blackboard`，用于多个独立 agent 在同一台机器上从不同方向调查问题，共享自由 Markdown。

## 使用

将 `skills/blackboard` 复制到宿主支持的 skill 目录，或让 agent 读取其中的 `SKILL.md`。仓库不自动修改全局配置，不安装后台服务。脚本需要 Python 3.9+、macOS/Linux 本地文件系统，patch 额外依赖 PATH 中的 Git，其余操作仅需 Python 标准库。

在第一个会话中：

> 使用 $blackboard，在 /绝对路径/incident/BLACKBOARD.md 创建黑板，从日志方向调查问题，保持只读。

在另一个独立会话中：

> 使用 $blackboard，加入 /绝对路径/incident/BLACKBOARD.md，从代码方向调查同一个问题，保持只读。

各会话可以选择自己的署名，不依赖父 agent 或身份服务。用户未明确要求启用时，agent 必须先询问。同名文件不等于同一块黑板，必须传递相同绝对路径。文档更新不会唤醒另一个会话。需要共同结论时，由用户指定或明确约定一个汇总负责人。

黑板及临时调查文件放在用户选定的任务目录，不放在 skill 仓库。锁仅协调通过脚本执行的写入。

## 编辑方式

`init` 创建，`read` 返回正文和 SHA-256，`append` 追加。局部更新使用 `patch`（标准 unified diff，由 git apply 在非仓库临时副本应用），整篇整理使用 `save`。两者都必须传入 `--expected-sha256`；版本冲突或补丁失败不写回。旧 `replace` 命令已移除。完整示例见 skill。

## 文档与验证

- [Skill](skills/blackboard/SKILL.md)
- [设计](docs/superpowers/specs/2026-09-14-blackboard-skill-design.md)
- [实施计划](docs/superpowers/plans/2026-09-14-blackboard.md)

在仓库根目录运行：

```bash
python3 -m unittest discover -s tests -v
```

测试使用隔离临时目录，不访问业务系统。模型是否在所有场景正确询问授权不是单元测试能证明的；见交付验证报告中的边界。
