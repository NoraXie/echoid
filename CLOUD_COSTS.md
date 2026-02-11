# Google Cloud 服务使用与成本管理指南

本文档旨在帮助你管理本项目（WAHA WhatsApp 登录系统）所使用的 Google Cloud 资源，了解免费额度，并避免产生意外费用。

## 📊 当前使用的服务概览

本项目目前主要使用以下 Google Cloud 服务：

| 服务名称                    | 用途                                  | 计费模式                           | 免费层级 (Free Tier) *                                                             |
| :-------------------------- | :------------------------------------ | :--------------------------------- | :--------------------------------------------------------------------------------- |
| **Cloud Run**               | 托管后端 Python (Flask) 代码          | 按 CPU 和内存使用时间 + 请求数计费 | 每月前 200 万次请求免费；每月前 180,000 vCPU-秒 免费；每月前 360,000 GiB-秒 免费。 |
| **Cloud Build**             | 构建 Docker 容器镜像 (部署时自动触发) | 按构建分钟数计费                   | 每天前 120 分钟构建时间免费。                                                      |
| **Artifact Registry**       | 存储构建好的 Docker 镜像              | 按存储空间和流量计费               | 每月前 0.5 GB 存储免费 (部分区域)。                                                |
| **Firebase Hosting** (可选) | 托管前端 HTML/JS 静态文件             | 按存储和流量计费                   | 免费计划 (Spark Plan) 包含 10 GB 存储和 10 GB/月 流量。                            |

> *注：免费层级可能会随 Google 政策调整，请以官方最新文档为准。*

---

## 💰 详细成本分析与控制

### 1. Cloud Run (后端服务)
这是我们运行 `backend.py` 的地方。
*   **风险点**：如果你设置了 "Always on" (CPU 始终分配) 或者实例最小数量 (`--min-instances`) 大于 0，即使没有流量也会持续计费。
*   **如何省钱**：
    *   **保持默认设置**：Cloud Run 默认是 "按需扩缩" (Scale to Zero)。这意味着如果没有人访问你的登录页面，实例数为 0，**完全不扣费**。
    *   **并发设置**：默认并发度通常足够处理大量请求，无需调整。
    *   **避免死循环**：确保代码中没有无限循环或错误重试导致的资源耗尽。

### 2. Cloud Build & Artifact Registry (构建与存储)
当你运行 `gcloud run deploy --source .` 时，Google 会先在云端构建 Docker 镜像，然后存放在 Artifact Registry 中。
*   **风险点**：每次部署都会产生一个新的镜像版本。久而久之，Artifact Registry 中会堆积大量旧镜像，超出 0.5 GB 的免费存储额度。
*   **如何省钱**：
    *   **定期清理镜像**：你可以设置生命周期策略，或者手动删除旧的镜像版本。
    *   **命令检查**：
        ```bash
        # 列出所有镜像
        gcloud artifacts docker images list
        
        # 删除特定镜像
        gcloud artifacts docker images delete [IMAGE_URI]
        ```

### 3. 流量费用 (Network Egress)
*   **说明**：数据从 Google Cloud 流出到互联网（例如发给用户的浏览器）需要付费。
*   **免费额度**：标准层级下，每月前 1 GB 网络流出通常是免费的（适用于北美等地区）。
*   **现状**：本项目传输的主要是 JSON 文本，数据量极小，很难超出免费额度。

---

## 🛡️ 预防措施：如何避免账单休克

### 1. 设置预算提醒 (强烈推荐)
即使你打算只用免费额度，也应该设置一个预算提醒（例如 1 美元/月）。
1.  访问 [Google Cloud Console Billing](https://console.cloud.google.com/billing)。
2.  点击左侧菜单的 **Budgets & alerts** (预算和提醒)。
3.  点击 **Create Budget**。
4.  设置金额为 **$1** (或者 $5)。
5.  设置提醒阈值 (例如达到 50%, 90%, 100% 时发送邮件)。
    *   *作用：一旦产生任何费用，你立刻就会收到邮件通知，可以及时去停用服务。*

### 2. 停止/删除服务
如果你不再需要这个项目，可以彻底删除以绝后患。

**删除 Cloud Run 服务：**
```bash
gcloud run services delete waha-auth-backend --region us-central1
```

**删除容器镜像 (Artifact Registry)：**
```bash
# 需先找到仓库名称
gcloud artifacts repositories list
gcloud artifacts repositories delete [REPOSITORY_NAME] --location=[REGION]
```

**删除整个项目 (最彻底)：**
在 Google Cloud Console 主页 -> Settings -> Shut down project。

---

## 🚀 总结
对于目前的测试和低流量使用场景：
1.  **Cloud Run** 几乎肯定是免费的（只要你没配置预留实例）。
2.  **构建和存储** 是唯一可能产生微小费用的地方（几分钱），只要记得测试完清理旧镜像即可。
3.  **设置预算提醒** 是最保险的手段。


# Supabass

## 账号准备
注册账号： newnora0921@gmail.com的github账号
数据库密码： xbIIoF7Lx5MEWdnI
项目名称： BuenType

## 如何使用supabass

正确的配置流程应该是：
第一步：注册 Supabase (管家)
前往 Supabase 官网。
点击 "Start your project"，使用你的 GitHub 账号登录。
创建一个新项目（选择靠近你的服务器位置，比如新加坡或美国）。
注意：Supabase 会给每个项目分配一个 Project URL 和 Anon Key，这是我们要写在代码里的。
第二步：在 Google Cloud Console 申请通行证
这一步你已经在做了，你只需要在 Google Cloud 里完成以下操作：

在 “API 和服务” > “凭据” 中创建一个 “OAuth 2.0 客户端 ID”。
应用类型选择 “Web 应用程序”。
在 “授权的重定向 URI” 中，填入 Supabase 后台给你的回调地址（在 Supabase 的 Authentication > Providers > Google 页面可以找到）。
第三步：连接两者
把 Google Cloud 里的 Client ID 和 Client Secret 复制，粘贴到 Supabase 的 Google 配置项里。

建议操作：
你可以先打开 Supabase 官网创建一个项目。一旦创建好，它会提供一个控制面板，我们就可以在那里：

配置 Google 登录。
直接编写 SQL 语句创建 leaderboards（排行榜）表。
你现在是在电脑旁吗？如果是，你可以先打开 Supabase 项目创建页面，我一步步引导你完成后续配置。


