# 🚀 WAHA Auth 系统部署指南

本项目已配置为**单容器全栈部署**模式。这意味着你只需要部署一个 Google Cloud Run 服务，就可以同时拥有后端 API 和前端网页。

## 🛠 准备工作

1.  **准备账号配置**:
    打开 `accounts_config.json` 文件，填入你真实的 WAHA 账号信息（API URL, Key, Session Name 等）。
    *   *注意：不要将包含敏感 Key 的文件提交到公共代码仓库（如 GitHub）。*

2.  **打开 Cloud Shell**:
    登录 [Google Cloud Console](https://console.cloud.google.com)，点击右上角的 `>_` 图标打开 Cloud Shell。

3.  **上传代码**:
    在 Cloud Shell 中创建一个文件夹（如 `waha-deploy`），将 `test_wa_auth` 目录下的所有文件上传进去。
    *   *包含文件*: `backend.py`, `Dockerfile`, `requirements.txt`, `index.html`, `LoginPage.js`, `LoginPage.css`, `index.js`, `accounts_config.json`。

---

## ☁️ 执行部署 (只需 3 步)

在 Cloud Shell 终端中，依次运行以下命令：

### 1. 设置默认项目和区域
```bash
# 替换 [YOUR_PROJECT_ID] 为你的项目 ID
gcloud config set project [YOUR_PROJECT_ID]

# 设置默认区域 (推荐 us-central1，便宜且稳定)
gcloud config set run/region us-central1
```

### 2. 提交构建并部署
这一步会自动打包代码并发布服务。
```bash
gcloud run deploy waha-auth-service \
  --source . \
  --platform managed \
  --allow-unauthenticated
```
*   `waha-auth-service`: 你的服务名称，可以随意修改。
*   `--source .`: 使用当前目录的代码。
*   `--allow-unauthenticated`: 允许任何人访问（因为这是登录页面）。

### 3. 获取访问地址
部署成功后，终端会显示一个 URL，格式如下：
```
Service URL: https://waha-auth-service-xyz123-uc.a.run.app
```

---

## ✅ 测试

1.  点击终端生成的 **Service URL**。
2.  你应该能直接看到登录页面（不再是 404 或空白）。
3.  点击“Abrir WhatsApp y Enviar”按钮，系统会自动分配一个可用的 WAHA 账号并跳转到 WhatsApp。

## 🔄 如果你需要更新配置

如果你修改了 `accounts_config.json`（例如添加了新账号），只需要重新运行第 2 步的命令：
```bash
gcloud run deploy waha-auth-service --source .
```
Cloud Run 会自动平滑更新，不会中断服务。
