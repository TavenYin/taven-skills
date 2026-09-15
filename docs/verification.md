# Blackboard patch + save 交付验证

日期：2026-09-15
项目：`/Users/taven/WorkSpace/mine/taven-skills`

## 本次变更

移除 replace，新增 patch 和 save，保留 init/read/append。patch/save 在 CLI 与写入函数内都要求预期 SHA-256，任何文档变化都拒绝旧版本。

patch 复用 [git apply](https://git-scm.com/docs/git-apply)，在无仓库临时目录处理 BLACKBOARD.md 副本；检查 Git numstat 与 summary，仅接受单一文本文件内容修改。补丁成功后才原子发布，不使用 reject、三方合并或自动空白修复。Git 不可用或超时返回明确错误。save 接收完整 UTF-8 Markdown，不需要输出旧文。

skill 示例、README、设计与实施记录已同步，启用授权和独立 agent 调查约定不变。

## 验证结果

13 项 unittest 全部通过，退出码 0，完整日志没有测试错误或失败；skill 格式校验通过。

覆盖：无仓库真实 git apply；多个修改块成功及局部失败不写回；patch/save 同版本竞争；缺失或旧摘要；其他路径、多文件、创建、删除、改名、模式与符号链接模式、二进制补丁拒绝；模拟 Git 缺失与超时；继承 Git 环境隔离；24 个独立进程并发追加；锁超时与持锁进程退出；原子发布失败及发布前进程中断；Unicode/CRLF 保存、权限和路径别名。

## 验证边界

在当前 macOS 上验证脚本行为，未对 GPT-5.6、GPT-6、Grok 4.6 分别做真实多会话端到端测试。版本保护不能发现模型整篇保存时遗漏信息；直接绕过脚本编辑也不受锁保护。Windows、网络盘和断电级持久性未验证。

## 自审与交付

Git 是实际外部边界，保留 apply_patch 函数封装隔离调用；删除旧文本匹配器，没有自建补丁解析、身份服务或新增包装类。

源码包已更新。未全局安装、未 commit/push/创建 PR，未启动真实黑板调查。
