# 分层重构实施记录

首批实施：2026-10-11。基线为 `acc8e1e9517e49fa502d7380b187d1f9e570c632`（合并 #86 后的 main）。
完整约束见 [重构 PLAN](./refactor-plan.md)。这里记录实际交付范围，不将首批入口等同于全部功能已迁移。

## 已实现的首批功能

- Qt-free 账户元数据、系统 keyring 密码存储和深浅色设置服务。
- 本科/研究生成绩查询：完整认证、当前/指定学期选择、本科成绩单补充及去重。
- 单文件下载：认证、可关闭的数据流、字节进度、长度校验、临时文件原子提交及取消清理。
- CLI 与 Qt6/PySide6/QML 入口调用同一套服务；QML 使用官方 Basic，外观仅有深色/浅色。
- 旧 `ScoreThread`、`GraduateScoreThread`、`LMSFileDownloadThread` 改为单向调用共享服务的兼容入口，删除其中重复的业务流程。
- 统一任务记录、协作取消、账户身份、主线程展示桥和高频事件合并；任务不属于页面对象。

## 运行

项目仍以源码方式运行。CLI 不要求安装 Qt；下面的 `--no-dev` 避免安装用于旧 GUI 回归的开发依赖。

```bash
uv sync --frozen --no-dev
uv run --frozen --no-dev python -m xjtutoolbox.cli --help
uv run --frozen --no-dev python -m xjtutoolbox.cli accounts add STUDENT_ID
uv run --frozen --no-dev python -m xjtutoolbox.cli accounts list --json
uv run --frozen --no-dev python -m xjtutoolbox.cli scores --account ACCOUNT_UUID --current-term --json
uv run --frozen --no-dev python -m xjtutoolbox.cli download --account ACCOUNT_UUID HTTPS_URL OUTPUT_PATH --json
```

密码在交互终端隐藏输入，也可通过 `XJTUTOOLBOX_PASSWORD` 环境变量提供。禁止将密码放在命令参数中。
`accounts add --remember` 使用系统凭据存储；默认只在本次进程内保留密码。下一次命令可以通过环境变量提供密码，
GUI 可以为选中账户重新输入密码。账户数据库只存储 UUID、用户名、名称、类型和设置。
`accounts unlock` 的密码同样只在当前进程内有效；自动化查询建议直接给查询命令提供环境变量。

CLI 的 `--interactive` 在当前进程中续接 MFA/图片验证码；默认需要输入时返回账户绑定的挑战数据。
进度与诊断写 stderr，JSON 结果写 stdout。退出码为：成功 `0`、失败 `1`、参数错误 `2`、需要输入 `3`、取消 `130`。
`--data-dir DIRECTORY` 位于子命令之前，可以隔离开发数据。

新 GUI：

```bash
uv sync --frozen --no-dev --extra gui
uv run --frozen --no-dev --extra gui python -m xjtutoolbox.gui
```

迁移期旧 GUI 保持原启动方式，安装 `legacy-gui` extra 或完整 dev 依赖。
新旧入口在独立进程运行；禁止同一进程同时初始化 Qt5/Qt6。新 GUI 目前仅提供账户、成绩和单文件下载。
旧账户加密文件和旧缓存没有被修改，也不会自动解密导入新数据库；账户/缓存迁移仍是后续交付项。
新 Qt6 extra 当前支持 64 位平台；旧 32 位 Windows 发布路径仍保留在旧入口。

## 目录与依赖

| 目录 | 职责 | 约束 |
| --- | --- | --- |
| `xjtutoolbox/api` | 账户绑定的认证、成绩协议、可关闭数据流、存储功能 | 没有 progress、TaskContext、Qt 或终端输出 |
| `xjtutoolbox/services` | 完整查询、成绩单合并、下载/校验/提交策略 | 不执行 HTTP/SQL、不调度线程、不操作 UI |
| `xjtutoolbox/gui` | QML、展示模型、Qt6 执行桥 | 不访问 API、会话、凭据和数据库 |
| `xjtutoolbox/cli` | 参数、输入、结果/进度输出和退出码 | 不 import Qt，不另写业务流程 |
| `xjtutoolbox/contracts` | 数据、可判别错误、进度与取消协议 | 基础数据和任务契约分开 |
| `xjtutoolbox/runtime` | 任务状态与事件、取消请求、订阅 | 不启动线程、不依赖 Qt 或校园业务 |
| `xjtutoolbox/infrastructure` | HTTP、SQLite、keyring、临时文件 | 只由 API 使用 |
| `xjtutoolbox/bootstrap.py` | 启动装配 | 只构造并注入依赖，不处理业务 |

`auth`、`jwxt`、`gmis` 中经过验证的纯协议实现继续复用，没有复制学校登录和成绩解析算法。
启动模块是有限的装配位置，GUI/CLI 的其余代码无法直接使用这些实现。

执行 `python scripts/check_architecture.py` 检查静态边界，核心测试还在子进程中拦截全部 Qt import。
[遗留依赖清单](./legacy-dependencies.json) 登记精确文件、已有框架依赖及退出条件；禁止扩大遗留 Qt 依赖。
两个 `app/utils/legacy_*` 文件是限于旧入口的临时适配器，不可被新 API/服务/GUI/CLI 导入，随旧页面退出删除。
它们仍受旧账户/会话生命周期限制；新账户失效与写入协调保证适用于新的 CampusAPI 路径。

## 功能迁移清单

| 用户操作 | 当前实现位置/接口 | 首批状态与退出条件 |
| --- | --- | --- |
| 账户、认证、设置 | `app/utils/account.py`、`config.py`、`session_manager.py`、`app/sessions/*` | 新入口有独立 Qt-free 实现；旧加密账户、二维码、WebVPN、会话持久化迁移后退出旧实现 |
| 本科/研究生成绩 | `jwxt/score.py`、`gmis/score.py`、两个旧成绩线程 | 共享查询服务贯通新 GUI/CLI；旧成绩页仅保留展示及兼容入口，随 P6 删除 |
| 课表、考试、考勤同步/导出 | `ScheduleThread`、`GraduateScheduleThread`、`ExamScheduleThread`、`ScheduleAttendanceThread`、`schedule/*` | 待 P3；须保留考勤→教学服务平台回退、显式学期、先校验后原子写入及导出 |
| LMS 浏览、作业、课程回放 | `LMSThread`、`LMSInterface`、`sub_interfaces/lms/*`、`lms/*` | 待迁移列表/详情工作流与 QML 页面 |
| 单文件下载 | `LMSFileDownloadThread` | 已使用共享服务；新 GUI 输入附件 URL/目标路径，LMS 资源选择导航仍待迁移 |
| LMS 批量下载 | `LMSBatchDownloadThread` | 待 P4 批量编排；需使用同一单文件服务并定义部分结果 |
| 本科/研究生评教 | `JudgeThread`、`GraduateJudgeThread`、`jwxt`、`gste` | 待 P5；需先定义不明提交状态、核验、重复提交和部分成功 |
| 通知与订阅 | `NoticeThread`、`sub_interfaces/NoticeInterface`、`notification/*` | 待迁移；统一过滤/来源规则，固定任务身份及取消边界 |
| 校园卡、学籍、体测 | `CampusCardInterface`、`ProfileInterface`、`FitnessInterface` 及 `CampusFeatureThread` | 待迁移；保留分页、金额语义、协议错误及账户隔离回归 |
| 图书馆、场馆预约 | `LibraryInterface`、`VenueThread`、`library/*`、`venues/*` | 待迁移；先定义提交、取消和查询核验语义 |
| 空闲教室、教学服务查询 | `EmptyRoomThread`、`CFEmptyRoomThread`、`SchoolCourseInterface`、`ywtb`、`jwxt` | 待迁移服务、DTO 与新页面 |
| AI、工具、通知托盘、更新/单实例 | `AIInterface`、`ToolBoxInterface`、`TrayInterface`、`UpdateThread`、`utils/single_app.py` | 待 P6；运行/发布设施不能混入业务服务 |

本分支未合入或关闭尚未完成的上游 PR，不把重构视为业务缺陷已自动解决。

## 关键行为

- 只有执行机制确定成功、失败、取消。返回 `None` 也是成功；100% 进度不能代表成功。
- 运行任务收到取消仍保持 RUNNING，直到服务退出并完成清理；提交成功后的迟到取消不改写成功。
- 每个任务固定 UUID 账户。单账户服务流程串行，会话不从全局 current 获取；删除与文件提交由同一协调锁保护。
- 账户删除不关闭正在使用的 HTTP 会话，当前使用者退出后清理；没有使用者的敏感会话立即清理。
- GUI 只在主线程修改模型，以任务 ID 和账户过滤结果；即使旧通知已经排入 Qt 队列也不能污染新请求。
- 页面不拥有 worker。关闭应用停止接收任务、请求取消，并保持事件循环直到 worker 完成；正常路径没有强杀线程。
- HTTP 的连接/读取超时为 10/30 秒；账户串行锁等待最多 30 秒。取消受阻塞 I/O 边界约束，不承诺立即停止。
- 下载不读 `response.text`，按可用网络数据推进；只检查有界正文片段识别登录页。gzip 等编码长度不当作解码后的总量。
- 下载失败或取消时清理临时文件，保留旧目标文件；只有验证通过且账户仍有效才原子替换最终文件。
- 挑战仅携带账户、站点、类型、提示和图片数据，5 分钟失效；活的登录对象和会话不传给前端。

## 验证记录

原始基线与首批实现都在 Linux x86_64 / Python 3.12.14 的隔离数据目录执行，Qt5 与 Qt6 域各用独立进程。
原始提交的 Qt 多媒体依赖先补齐再运行，没有跳过测试。

| 检查 | 原始基线 | 首批实现 |
| --- | ---: | ---: |
| 产品测试 | 365 | 453 |
| 测试契约 | 62 | 62 |
| 历史回归（有意重跑） | 158 | 158 |
| Qt-free 安装环境中的 CLI | 无独立入口 | 通过，环境未安装 PyQt/PySide/qfluentwidgets |
| 实际 QML 启动/退出、明暗切换、主线程、销毁/迟到事件、进度合并 | 无 Qt6 入口 | 11 个测试通过 |

可复现的完整检查：

```bash
uv sync --frozen --group dev
uv run --frozen local_test.py
uv run --frozen python -m test.ci.run_test_regressions
uv run --frozen python scripts/check_architecture.py
```

CI 保留全部既有平台/域，新增 core、qt6-ui 两个域；锁文件同步更新。
本地用例数与 CI 跨平台结果分别记录，不能以本地成功替代 Windows、macOS、Linux ARM64 的实际结果。
本次没有真实学校账户，因此未做带凭据的学校系统端到端验证；扫码/WebVPN/旧缓存等待迁移能力仍通过旧入口使用。
