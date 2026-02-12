# EchoID

[English](#english) | [中文](#chinese)

---

<a name="english"></a>
## English

EchoID is a WhatsApp-based identity verification system. It provides a seamless way to verify user phone numbers by leveraging WhatsApp deep links and a backend verification service.

### Project Components

This repository contains:

1.  **Server (`/server`)**: A Python FastAPI backend that handles:
    *   Verification initialization (`/v1/init`).
    *   Deep link generation for WhatsApp.
    *   Interaction with the EchoB (WhatsApp Service) API.
    *   Rate limiting and security checks.

2.  **Android SDK Documentation (`/android`)**:
    *   Integration guide for Android applications.
    *   (Note: The SDK source code is maintained separately or packaged as an AAR).

## Project Structure / 项目结构

*   `server/`: Python FastAPI backend.
*   `android/`: Android SDK documentation.
*   `echoid.db`: Local SQLite database (for development).

<a name="configuration"></a>
## Configuration & Deployment / 配置与部署

The project uses environment variables for configuration. We provide example files for different environments:
*   `.env.dev.example`: For local development.
*   `.env.prod.example`: For production deployment.

### 1. Setup Environment Variables / 设置环境变量

Copy the example file to `.env` and fill in your actual secrets:

```bash
# For Local Development
cp .env.dev.example .env

# For Production
cp .env.prod.example .env
```

**⚠️ Important:** Never commit your `.env` file to version control.

### 2. Google Cloud Free Tier Deployment Guide / 谷歌云免费层部署指南

To deploy this project on Google Cloud Platform (GCP) "Always Free" tier (e.g., `e2-micro` instance with Debian/Ubuntu), follow these steps.

#### Server Initialization (Debian/Ubuntu)
New Debian instances might lack common tools. Run these commands first:

```bash
# 1. Update system and install basic tools
sudo apt-get update && sudo apt-get install -y git vim curl unzip

# 2. Enable 'll' alias (Optional, for convenience)
echo "alias ll='ls -l'" >> ~/.bashrc
source ~/.bashrc

# 3. Install Docker & Docker Compose
sudo apt-get install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# NOTE: Log out and log back in for docker group changes to take effect!
```

#### VM Instance (Compute Engine)
*   **Region**: `us-west1` (Oregon), `us-central1` (Iowa), or `us-east1` (South Carolina).
*   **Machine Type**: `e2-micro` (2 vCPU, 1 GB memory).
*   **Provisioning Model**: `Standard` (Do NOT use Spot).
*   **Boot Disk**:
    *   Type: `Standard persistent disk` (pd-standard).
    *   Size: Up to `30 GB`.

#### Networking
*   **External IP**: Ephemeral IP is free. Static IP is free ONLY if attached to a running instance.
*   **Network Tier**: Must use `Standard` tier (Not Premium) for outbound traffic to be partially free, though the 200GB free tier applies to Premium in some contexts. **Recommendation:** Stick to Standard tier if asked, or verify current "Always Free" network terms.

#### Observability & Costs
*   **Logging**: First 50 GiB/month is free.
*   **Monitoring**: Basic metrics are free.
*   **Snapshots**: ⚠️ **Caution**. Only 5 GB/month is free. Do NOT enable aggressive "Snapshot Schedules". Recommended to disable automatic snapshots or keep retention very low (e.g., 1 copy).

#### Docker Deployment (Git Workflow)
1.  **Clone the Repository** (on your VM):
    ```bash
    git clone https://github.com/YOUR_USERNAME/echoid.git
    cd echoid/echoid
    ```

2.  **Configure Environment**:
    ```bash
    cp .env.prod.example .env
    nano .env  # Fill in your secrets
    ```

3.  **Start Services**:
    ```bash
    docker-compose up -d --build
    ```

#### Update & Hot Reload
To update the server with the latest code:
```bash
# 1. Pull latest changes
git pull origin main

# 2. Rebuild and restart containers (Minimal downtime)
# This will pick up changes in code, install new requirements, and run init_db
docker-compose up -d --build --remove-orphans
```

### Getting Started

#### Prerequisites

*   Python 3.8+
*   Redis (Required for rate limiting)
*   PostgreSQL (Recommended) or SQLite (Default for dev)

#### Installation

1.  **Setup Virtual Environment**
    It is recommended to use a virtual environment.
    ```bash
    # Example using shared venv
    source ~/Documents/coding/venv/bin/activate
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r server/requirements.txt
    ```

3.  **Environment Configuration**
    The application uses `pydantic-settings`. You can set environment variables or use a `.env` file.
    Key variables:
    *   `DATABASE_URL`: Connection string for the database.
    *   `REDIS_URL`: URL for Redis instance.
    *   `API_KEY`: Secret key for API authentication.

#### Running the Server

```bash
python3 server/main.py
```

The server will start on `http://0.0.0.0:8000`.

#### Running Tests

To run the full test suite (including mocked Redis/DB interactions):

```bash
python3 server/test_server.py
```

### Android Integration

See [android/README.md](android/README.md) for detailed instructions on how to integrate the EchoID SDK into your Android app.

---

<a name="chinese"></a>
## 中文

EchoID 是一个基于 WhatsApp 的身份验证系统。它利用 WhatsApp Deep Links 和后端验证服务，提供了一种验证用户手机号码的无缝方式。

### 项目组件

本仓库包含：

1.  **服务端 (`/server`)**: 一个 Python FastAPI 后端，负责处理：
    *   验证初始化 (`/v1/init`)。
    *   生成 WhatsApp Deep Links。
    *   与 EchoB (WhatsApp 服务) API 交互。
    *   速率限制和安全检查。

2.  **Android SDK 文档 (`/android`)**:
    *   Android 应用程序集成指南。
    *   (注意：SDK 源代码单独维护或打包为 AAR)。

### 项目结构

```
echoid/
├── android/            # Android SDK 集成指南
├── server/             # 后端服务器代码
│   ├── main.py         # FastAPI 应用入口
│   ├── config.py       # 配置管理
│   ├── models.py       # 数据库模型
│   ├── schemas.py      # Pydantic 模式
│   ├── utils.py        # 工具函数 (加密等)
│   └── requirements.txt # Python 依赖
├── echoid.db           # 本地 SQLite 数据库 (开发用)
└── .gitignore          # Git 忽略规则
```

### 快速开始

####先决条件

*   Python 3.8+
*   Redis (速率限制需要)
*   PostgreSQL (推荐) 或 SQLite (开发默认)

#### 安装

1.  **设置虚拟环境**
    建议使用虚拟环境。
    ```bash
    # 使用共享 venv 示例
    source ~/Documents/coding/venv/bin/activate
    ```

2.  **安装依赖**
    ```bash
    pip install -r server/requirements.txt
    ```

3.  **环境配置**
    应用程序使用 `pydantic-settings`。您可以设置环境变量或使用 `.env` 文件。
    关键变量：
    *   `DATABASE_URL`: 数据库连接字符串。
    *   `REDIS_URL`: Redis 实例 URL。
    *   `API_KEY`: API 认证密钥。

#### 运行服务器

```bash
python3 server/main.py
```

服务器将在 `http://0.0.0.0:8000` 启动。

#### 运行测试

运行完整测试套件（包括模拟的 Redis/DB 交互）：

```bash
python3 server/test_server.py
```

### Android 集成

有关如何将 EchoID SDK 集成到 Android 应用中的详细说明，请参阅 [android/README.md](android/README.md)。
