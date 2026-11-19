# aivudaOS Android 客户端

H16 地面站支持 Android 7.1（API 25）及以上版本。应用管理界面随 APK 安装到设备上，应用的安装、启停和参数修改在所连接的 aivudaOS 服务器上执行。

`aivuda-station.apk` 包含登录、系统状态、应用商店、应用管理和参数页面。

本分支提供[已编译的地面站 APK](apk/aivuda-station.apk)，使用开发密钥签名。

## 从源码构建

在 Linux 上准备 Bash、JDK 17 或更高版本、Node.js 22.12+ 或 24、Android SDK Platform 29 和 Build Tools 34.0.0。以下命令从仓库根目录执行。

```bash
export ANDROID_SDK_ROOT=/path/to/android-sdk
npm --prefix aivudaos/resources/ui ci
./android/build.sh
```

脚本会构建兼容 Chromium 52 的界面，打包地面站，并在签名验证通过后将安装包写入 `android/build/aivuda-station.apk`。网页资源、Java 类文件和未签名的中间包都在临时目录中生成，脚本退出时自动清理。

## 安装到设备

启用设备的 USB 调试，连接电脑并授权后，使用 Android SDK Platform Tools 中的 `adb` 安装地面站。

```bash
adb install -r android/build/aivuda-station.apk
```

打开「Aivuda 地面站」，点「设置服务器地址」，输入设备可访问的服务器 IP 或 HTTP(S) 地址，再使用服务器账号登录。登录后可从应用卡片进入参数页面。[地面站操作指南](../docs/android-h16.md)

## 签名与 GitHub Release

本地测试默认使用 `~/.local/share/aivuda-android/development.p12` 中的开发密钥，首次构建会创建它。正式发布时使用自己的单条目密钥库，通过绝对路径指定文件，并从终端输入密码。后续覆盖安装需要使用相同的签名密钥。

```bash
export AIVUDA_SIGNING_KEY=/absolute/path/to/release.p12
read -rs -p 'Keystore password: ' AIVUDA_KEY_PASSWORD; printf '\n'
export AIVUDA_KEY_PASSWORD
./android/build.sh
unset AIVUDA_KEY_PASSWORD
```

发布新版本前，更新对应 `AndroidManifest.xml` 的 `versionCode` 和 `versionName`。源码和锁文件随 Git 提交，正式签名的 APK 作为 GitHub Release 附件上传。签名密钥和密码保存在仓库外。

默认构建使用系统受信任的 CA。若部署环境使用私有商店 CA，在构建前设置 `AIVUDA_STORE_HOST` 为商店主机名，`AIVUDA_STORE_CA` 为 PEM 根证书的绝对路径。该证书会打入地面站 APK，信任范围仅限指定主机。

## 代码目录

| 路径 | 职责 |
| --- | --- |
| `station/` | 地面站入口、服务器地址选择和 WebView 宿主 |
| `i18n/locales/` | 原生界面的中英文资源 |
| `../aivudaos/resources/ui/` | 与桌面版共用的 Vue 源码，以及 H16 入口、兼容样式和词表 |
| `build.sh` | 构建网页资源、打包、签名和验证 |
