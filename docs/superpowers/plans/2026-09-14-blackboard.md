# Blackboard Implementation Plan

**Goal:** 多个独立 agent 在同一台机器上，从不同方向调查问题，并安全维护共享 Markdown。
**Architecture:** 一个 skill 加一个 Python 标准库 CLI；身份是署名，文档无固定结构。
**Tech Stack:** Python 3.9+，macOS/Linux，fcntl 系统锁。
**Spec:** ../specs/2026-09-14-blackboard-skill-design.md

## Constraints

用户已授权实现。单个新目录内执行，不采用 TDD，不提交、推送或创建 PR，不安装到全局 skill 目录。先实现，再验证。不启动真实黑板协作。

## Tasks

- [x] 更新设计：独立会话各自从调查方向选择署名；同一绝对路径；每个会话独立检查授权；协调者只负责汇总。
- [x] 编写 skills/blackboard/SKILL.md：启用检查、共享路径、独立加入、署名、证据与冲突处理，提供可运行 CLI 示例。
- [x] 实现 scripts/blackboard.py：init/read/append/replace；stdin 或文件输入；精确且不重叠的批量替换；可选 SHA-256；锁内读取、检查和原子发布。
- [x] 编写 README、忽略规则和事后 unittest 验证：并发追加、竞争替换、摘要冲突、失败不写入、Unicode/CRLF、锁超时与进程退出、发布中断。
- [x] 运行全部测试及 skill 格式检查，保存完整日志并核对退出码；自审代码及场景授权规则，输出验证边界。

2026-09-15：以上为首次实现记录。replace 已由 patch + save 替代，当前接口见 2026-09-15-patch-save.md。
