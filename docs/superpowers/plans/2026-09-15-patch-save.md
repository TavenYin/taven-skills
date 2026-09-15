# Patch + Save 实施记录

用户已确认用 patch + save 替换 replace，授权直接实现。保留 init/read/append；无 Git 提交、全局安装或真实协作。

- [x] 核对 git apply 官方契约与本机能力：无仓库使用，默认整份补丁失败不发布。
- [x] 移除 replace，patch/save 强制摘要。锁内使用临时副本、Git numstat/summary 限定单一文本文件，再应用并原子写回；不编写 diff 匹配器。
- [x] 实现后更新测试，验证补丁成功、多修改块失败不写回、越界路径与元数据拒绝、版本竞争、Git 缺失/超时及原有并发/中断行为。
- [x] 更新 skill、README、设计、交付报告和源码包。完整日志确认 13 项测试通过、格式校验成功。

约束：Python 3.9+，macOS/Linux 本地盘，patch 依赖 Git；现有权限规则不变。不采用 TDD，不运行自动格式化，不自行安装或发布。
