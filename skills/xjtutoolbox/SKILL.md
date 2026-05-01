---
name: xjtutoolbox
description: XJTUToolBox CLI — 西安交通大学校园服务命令行工具。查询课表/成绩/考勤、管理通知、评教、空闲教室、WebVPN 转换。使用 xjtutoolbox 命令或 python -m cli.main。
---

# XJTUToolBox CLI

西安交通大学校园服务命令行工具，支持全部 GUI 功能。

## 下载

始终指向最新 release，无需手动改版本号：

| 平台 | 文件 |
|------|------|
| Windows | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-windows.zip`（内含 `xjtutoolbox-cli.exe`） |
| macOS x86_64 | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-macOS-x86_64.dmg` |
| macOS arm64 | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-macOS-arm64.dmg` |
| Linux x86_64 deb | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-x86_64.deb` |
| Linux x86_64 rpm | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-x86_64.rpm` |
| Linux x86_64 pacman | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-x86_64.pkg.tar.zst` |
| Linux x86_64 AppImage | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-x86_64.AppImage` |
| Linux arm64 deb | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-arm64.deb` |
| Linux arm64 rpm | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-arm64.rpm` |
| Linux arm64 pacman | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-arm64.pkg.tar.zst` |
| Linux arm64 AppImage | `https://github.com/yan-xiaoo/XJTUToolBox/releases/latest/download/XJTUToolbox-linux-arm64.AppImage` |

### macOS CLI 安装

安装脚本位于 `.app` 内部，也可以手动创建软链：

```bash
# 方法一：运行 .app 内的安装脚本
open /Applications/XJTUToolbox.app/Contents/Resources/install-cli.sh

# 方法二：手动创建软链
sudo ln -sf /Applications/XJTUToolbox.app/Contents/MacOS/xjtutoolbox-cli /usr/local/bin/xjtutoolbox-cli
```

安装后即可在终端使用 `xjtutoolbox-cli` 命令。

> 如果 GUI 首次启动成功，CLI 会自动安装到 `/usr/local/bin/xjtutoolbox-cli`。若自动安装失败（如权限不足），请手动执行上述脚本或命令。

## 运行方式

```bash
# CLI 安装包 / pip 安装
xjtutoolbox-cli [--json] <命令> [参数]

# 未安装（项目目录下）
python -m cli.main [--json] <命令> [参数]

# Windows（压缩包内）
xjtutoolbox-cli.exe [--json] <命令> [参数]
```

`--json` 全局参数输出 JSON 格式，适合 AI 解析。

## 账户

首次使用需要登录。账户数据保存在 `shared.account`。

```bash
xjtutoolbox-cli account list              # 列出已保存的账户
xjtutoolbox-cli account switch <index>    # 切换当前账户
xjtutoolbox-cli account remove <index>    # 删除账户
xjtutoolbox-cli account encrypt           # 加密账户数据
xjtutoolbox-cli account decrypt           # 解密账户数据
```

## 配置

```bash
xjtutoolbox-cli config list               # 列出所有配置项
xjtutoolbox-cli config get <key>          # 获取某项配置值
xjtutoolbox-cli config set <key> <value>  # 修改配置
```

## 课表

```bash
xjtutoolbox-cli schedule get              # 获取当前学期课表
xjtutoolbox-cli schedule get --week 6     # 获取第 6 周课表
xjtutoolbox-cli schedule exam             # 考试安排
xjtutoolbox-cli schedule attendance       # 本周考勤统计
xjtutoolbox-cli schedule export-ics <file># 导出为 ICS 日历
```

分页参数：`--page N --page-size M`

## 成绩

```bash
xjtutoolbox-cli score query                        # 全部学期成绩
xjtutoolbox-cli score query --semester "2024-2025-2"  # 指定学期
```

返回含 GPA、学分统计。

## 考勤

```bash
xjtutoolbox-cli attendance flow                    # 考勤打卡流水
xjtutoolbox-cli attendance flow --page 2 --page-size 10
```

## 通知

```bash
xjtutoolbox-cli notice list                        # 通知列表
xjtutoolbox-cli notice list --page 2               # 翻页
xjtutoolbox-cli notice sources                     # 通知来源
xjtutoolbox-cli notice refresh                     # 刷新通知
xjtutoolbox-cli notice mark-read                   # 全部标记已读
```

## 评教

```bash
xjtutoolbox-cli judge list                         # 列出待评教问卷
xjtutoolbox-cli judge all                          # 一键全部评教
```

## 空闲教室

```bash
xjtutoolbox-cli empty-room query                   # 查询当前空闲教室
xjtutoolbox-cli empty-room query --date 2026-05-01 --start 3 --end 4  # 指定时间
xjtutoolbox-cli empty-room export <output.png>     # 导出为图片
```

## 思源学堂（LMS）

```bash
xjtutoolbox-cli lms courses                        # 课程列表
xjtutoolbox-cli lms activities <course-id>         # 课程活动
xjtutoolbox-cli lms detail <activity-id>           # 活动详情
xjtutoolbox-cli lms download <activity-id> [文件]  # 下载附件
```

## WebVPN

```bash
xjtutoolbox-cli webvpn encode <普通URL>   # → WebVPN 地址
xjtutoolbox-cli webvpn decode <WebVPN URL>  # → 普通地址
```

## 更新

```bash
xjtutoolbox-cli update check                      # 检查更新
xjtutoolbox-cli update check --prerelease         # 包含预发布版本
```

## 典型工作流

```bash
# 1. 查看今日课表
xjtutoolbox-cli schedule get

# 2. 查成绩
xjtutoolbox-cli score query

# 3. 查考勤
xjtutoolbox-cli attendance flow

# 4. 查最新通知
xjtutoolbox-cli notice list

# 5. 导出课表到日历
xjtutoolbox-cli schedule export-ics my_schedule.ics
```

## 注意

- 需要有效的 XJTU 统一认证账号
- 首次使用会在 `shared.config` 中创建配置
- `--json` 模式输出结构化数据，不包含人类友好的表格格式
