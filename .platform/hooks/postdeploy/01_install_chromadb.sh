#!/bin/bash

# ログファイルの設定
LOG_FILE="/var/log/chromadb-install.log"
echo "Starting ChromaDB installation at $(date)" >> $LOG_FILE

# エラーが発生しても続行
set +e

echo "=== ChromaDB Installation Script ===" | tee -a $LOG_FILE

# Python環境を探す
if [ -d /var/app/venv/staging-* ]; then
    VENV_PATH=$(ls -d /var/app/venv/staging-* | head -n 1)
else
    VENV_PATH=$(ls -d /var/app/venv/* | head -n 1)
fi

echo "Using virtual environment: $VENV_PATH" | tee -a $LOG_FILE
source $VENV_PATH/bin/activate

# pipをアップグレード
echo "Upgrading pip..." | tee -a $LOG_FILE
pip install --upgrade pip setuptools wheel >> $LOG_FILE 2>&1

# 重要：httpxを最初にインストール（他のパッケージより先に）
echo "Installing httpx (pinned version)..." | tee -a $LOG_FILE
pip install httpx==0.27.2 --no-cache-dir >> $LOG_FILE 2>&1

# 依存関係を段階的にインストール
echo "Installing tiktoken..." | tee -a $LOG_FILE
pip install tiktoken==0.5.2 --no-cache-dir >> $LOG_FILE 2>&1

echo "Installing pypdf..." | tee -a $LOG_FILE
pip install pypdf==3.17.4 --no-cache-dir >> $LOG_FILE 2>&1

# langchain関連を特定のバージョンでインストール
echo "Installing Langchain..." | tee -a $LOG_FILE
pip install langchain==0.1.0 --no-cache-dir >> $LOG_FILE 2>&1

echo "Installing Langchain OpenAI..." | tee -a $LOG_FILE
pip install langchain-openai==0.0.5 --no-cache-dir >> $LOG_FILE 2>&1

echo "Installing Langchain Community..." | tee -a $LOG_FILE
pip install langchain-community==0.0.10 --no-cache-dir >> $LOG_FILE 2>&1

# ChromaDBは最後にインストール
echo "Installing ChromaDB..." | tee -a $LOG_FILE
pip install chromadb==0.4.22 --no-cache-dir >> $LOG_FILE 2>&1

echo "Installing sentence-transformers..." | tee -a $LOG_FILE
pip install sentence-transformers==2.2.2 --no-cache-dir >> $LOG_FILE 2>&1

# 確認
echo "Verifying installation..." | tee -a $LOG_FILE
python -c "import chromadb; print('ChromaDB version:', chromadb.__version__)" >> $LOG_FILE 2>&1
python -c "import langchain; print('Langchain version:', langchain.__version__)" >> $LOG_FILE 2>&1
python -c "import httpx; print('httpx version:', httpx.__version__)" >> $LOG_FILE 2>&1

echo "ChromaDB installation completed at $(date)" | tee -a $LOG_FILE
echo "Check log file at: $LOG_FILE" 