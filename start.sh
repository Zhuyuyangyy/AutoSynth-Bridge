#!/bin/bash
# AutoSynth-Bridge 启动脚本
# 三模型协同工作流 - GPT学术裁判 + Gemini创新发散 + Claude Code落地

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================="
echo "  AutoSynth-Bridge - 三模型协同工作流"
echo "  GPT裁判 + Gemini发散 + Claude落地"
echo "=============================================="
echo

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

pip install -q openai anthropic requests python-dotenv 2>/dev/null

echo "[启动] 运行主程序..."
python3 main.py "$@"