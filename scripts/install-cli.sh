#!/bin/bash
# XJTUToolBox CLI 安装脚本
# 将 CLI 链接到 /usr/local/bin/xjtutoolbox-cli
DEST=/usr/local/bin/xjtutoolbox-cli
if ln -sf /Applications/XJTUToolbox.app/Contents/MacOS/xjtutoolbox-cli "$DEST" 2>/dev/null; then
  echo "✓ CLI 安装成功，现在可以在终端使用 'xjtutoolbox-cli' 命令"
else
  echo "✗ 安装失败，请尝试手动运行:"
  echo "  sudo ln -sf /Applications/XJTUToolbox.app/Contents/MacOS/xjtutoolbox-cli $DEST"
fi
