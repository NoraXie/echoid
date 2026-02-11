# EchoID Android SDK Integration Guide / Android SDK 集成指南

[English](#english) | [中文](#chinese)

---

<a name="english"></a>
## English

This guide describes how to integrate the EchoID SDK into your Android application to enable WhatsApp-based verification.

### 1. Installation

1.  Copy the `echoid-sdk-release.aar` file into your project's `libs` directory (e.g., `app/libs/`).
2.  Add the dependency in your module-level `build.gradle` file:

```gradle
dependencies {
    implementation files('libs/echoid-sdk-release.aar')
    // Required dependencies
    implementation 'com.squareup.okhttp3:okhttp:4.9.0'
}
```

### 2. Configuration (AndroidManifest.xml)

#### A. Permissions
Ensure your app has internet permission:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

#### B. Deep Link Configuration
Configure an Activity to handle the authentication callback. This Activity will receive the deep link from WhatsApp.

**Crucial:** You must use the scheme `echoid` and host `login`.

```xml
<activity
    android:name=".AuthActivity"
    android:exported="true"
    android:launchMode="singleTask">
    
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        
        <!-- STRICT REQUIREMENT: scheme="echoid", host="login" -->
        <data android:scheme="echoid" android:host="login" />
    </intent-filter>
</activity>
```

### 3. Initialization

Initialize the SDK in your `Application` class or main entry point.

```java
import com.echoid.sdk.EchoID;

public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        // Initialize with your API Key
        // Base URL is pre-configured in the SDK, or can be passed as a second argument if needed.
        EchoID.initialize("pk_live_YOUR_API_KEY");
    }
}
```

### 4. Usage

#### A. Start Verification
Call `startVerification` when the user requests OTP (e.g., clicks a button).

```java
String phone = "5215512345678"; // Format: CountryCode + Number (No + sign)

EchoID.startVerification(context, phone, new EchoCallback() {
    @Override
    public void onRedirect(String deepLink) {
        // The SDK normally handles the redirect automatically.
        // If you need to manually handle it, you can use this link.
        // Example: Opening WhatsApp manually
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(deepLink));
        startActivity(intent);
    }

    @Override
    public void onError(String message) {
        Toast.makeText(context, "Error: " + message, Toast.LENGTH_SHORT).show();
    }
    
    @Override
    public void onVerified(String otp) {
        // Not called in this step
    }
});
```

#### B. Handle Callback (Deep Link)
In the Activity configured in Manifest (e.g., `AuthActivity`), handle the incoming intent.

```java
@Override
protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    handleIntent(intent);
}

private void handleIntent(Intent intent) {
    EchoID.handleDeepLink(intent, new EchoCallback() {
        @Override
        public void onVerified(String otp) {
            // Success! The OTP is extracted automatically.
            // Fill it into your UI or submit it to your server.
            Log.d("EchoID", "Verified OTP: " + otp);
            otpInputView.setText(otp);
        }

        @Override
        public void onError(String message) {
             Log.e("EchoID", "Verification failed: " + message);
        }
        
        @Override
        public void onRedirect(String deepLink) {
            // Not used in this step
        }
    });
}
```

### 5. API Reference

#### `EchoID` (Singleton)

*   `void initialize(String apiKey)`
    *   Initializes the SDK.
*   `void startVerification(Context context, String phone, EchoCallback callback)`
    *   Initiates the verification process. Calls backend `/v1/init`.
*   `void handleDeepLink(Intent intent, EchoCallback callback)`
    *   Parses the incoming Deep Link (`echoid://login?token=...&otp=...`) and extracts the OTP.

#### `EchoCallback` (Interface)

*   `void onRedirect(String deepLink)`: Called when the deep link to WhatsApp is ready.
*   `void onVerified(String otp)`: Called when the user returns with a valid OTP.
*   `void onError(String message)`: Called when an error occurs.

---

<a name="chinese"></a>
## 中文

本指南介绍了如何集成 EchoID SDK 到您的 Android 应用程序中，以启用基于 WhatsApp 的验证。

### 1. 安装

1.  将 `echoid-sdk-release.aar` 文件复制到项目的 `libs` 目录（例如 `app/libs/`）。
2.  在模块级 `build.gradle` 文件中添加依赖项：

```gradle
dependencies {
    implementation files('libs/echoid-sdk-release.aar')
    // 必需的依赖项
    implementation 'com.squareup.okhttp3:okhttp:4.9.0'
}
```

### 2. 配置 (AndroidManifest.xml)

#### A. 权限
确保您的应用具有互联网权限：

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

#### B. Deep Link 配置
配置一个 Activity 来处理认证回调。该 Activity 将接收来自 WhatsApp 的 Deep Link。

**关键：** 您必须使用 scheme `echoid` 和 host `login`。

```xml
<activity
    android:name=".AuthActivity"
    android:exported="true"
    android:launchMode="singleTask">
    
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        
        <!-- 严格要求：scheme="echoid", host="login" -->
        <data android:scheme="echoid" android:host="login" />
    </intent-filter>
</activity>
```

### 3. 初始化

在您的 `Application` 类或主入口点初始化 SDK。

```java
import com.echoid.sdk.EchoID;

public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        // 使用您的 API Key 进行初始化
        // 如果需要，Base URL 已经在 SDK 中预配置，也可以作为第二个参数传递。
        EchoID.initialize("pk_live_YOUR_API_KEY");
    }
}
```

### 4. 使用方法

#### A. 开始验证
当用户请求 OTP（例如点击按钮）时调用 `startVerification`。

```java
String phone = "5215512345678"; // 格式：国家代码 + 号码（无 + 号）

EchoID.startVerification(context, phone, new EchoCallback() {
    @Override
    public void onRedirect(String deepLink) {
        // SDK 通常会自动处理重定向。
        // 如果您需要手动处理，可以使用此链接。
        // 示例：手动打开 WhatsApp
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(deepLink));
        startActivity(intent);
    }

    @Override
    public void onError(String message) {
        Toast.makeText(context, "错误: " + message, Toast.LENGTH_SHORT).show();
    }
    
    @Override
    public void onVerified(String otp) {
        // 此步骤中不会调用
    }
});
```

#### B. 处理回调 (Deep Link)
在 Manifest 中配置的 Activity（例如 `AuthActivity`）中，处理传入的 intent。

```java
@Override
protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    handleIntent(intent);
}

private void handleIntent(Intent intent) {
    EchoID.handleDeepLink(intent, new EchoCallback() {
        @Override
        public void onVerified(String otp) {
            // 成功！OTP 已自动提取。
            // 将其填充到您的 UI 或提交到您的服务器。
            Log.d("EchoID", "Verified OTP: " + otp);
            otpInputView.setText(otp);
        }

        @Override
        public void onError(String message) {
             Log.e("EchoID", "验证失败: " + message);
        }
        
        @Override
        public void onRedirect(String deepLink) {
            // 此步骤中不使用
        }
    });
}
```

### 5. API 参考

#### `EchoID` (单例)

*   `void initialize(String apiKey)`
    *   初始化 SDK。
*   `void startVerification(Context context, String phone, EchoCallback callback)`
    *   启动验证流程。调用后端 `/v1/init`。
*   `void handleDeepLink(Intent intent, EchoCallback callback)`
    *   解析传入的 Deep Link (`echoid://login?token=...&otp=...`) 并提取 OTP。

#### `EchoCallback` (接口)

*   `void onRedirect(String deepLink)`: 当跳转到 WhatsApp 的 deep link 准备就绪时调用。
*   `void onVerified(String otp)`: 当用户带有效 OTP 返回时调用。
*   `void onError(String message)`: 当发生错误时调用。
