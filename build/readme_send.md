# 请先看我 —— 投料计算器 网页部署

你好，麻烦帮我把这个小网站挂到服务器上，谢谢！

这是个**纯静态页面**，没有后端、没有数据库、没有构建步骤。

---

## 一、你要上传的东西

把 **`网站文件\`** 这个目录里的 **7 个文件**，整套放到服务器的任意一个静态目录下即可：

| 文件 | 作用 |
|---|---|
| `index.html` | 程序本体（单文件，约 353 KB） |
| `manifest.json` | PWA 清单（让手机能"添加到主屏幕"） |
| `sw.js` | Service Worker（离线缓存） |
| `icon-192.png` / `icon-512.png` | 主屏幕图标 |
| `apple-touch-icon.png` | iOS 主屏幕图标 |
| `favicon.png` | 浏览器标签页图标 |

**关键：这 7 个文件必须在同一个目录里、同一层级**，目录结构不要改（`manifest.json` 和 `sw.js` 是按相对路径找 `index.html` 和图标 `../../` 的）。

---

## 二、不需要的东西

不用装 Node、Python、PHP、Java，不用数据库，不用编译，不用配后端，不用改任何代码。

---

## 三、Nginx 最小配置示例

```nginx
server {
    listen 80;
    server_name calc.example.com;

    root /var/www/calc;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

把 `网站文件\` 里的 7 个文件传到 `/var/www/calc/` 下：

```
/var/www/calc/
├── index.html
├── manifest.json
├── sw.js
├── icon-192.png
├── icon-512.png
├── apple-touch-icon.png
└── favicon.png
```

Apache / Caddy 同理，指向同一个目录即可。

> **建议加 HTTPS。** HTTP 下页面能正常用，但「添加到主屏幕」和离线缓存这两个功能浏览器会禁用（Service Worker 只在 `https://` 或 `localhost` 下注册）。有免费证书的话直接上。

---

## 四、怎么验证挂好了

1. 浏览器打开你的网址 —— 界面应该直接出来，顶部有「投料计算器」和「内置词典 313 条」
2. 按 `F12` → `Application`（应用）→ `Service Workers` —— 应该能看到 `sw.js` 已注册并处于 activated
3. **断网**（或开发者工具里勾 Offline）后刷新 —— 页面仍应完整打开

---

## 五、⚠️ 两件要提醒的事

**1. 网址（域名 + 路径）定下来就别再改。**

用户在里面记录的试剂会存在**浏览器本地**（localStorage），而 localStorage 是按「域名 + 路径」隔离的。以后要是把目录从 `/calc` 挪到 `/tools/calc`，或者换了域名，**用户之前记录的试剂就找不到了**（数据还在，但页面读不到）。

**2. 这只是个计算器，不含任何用户数据上传。**

页面上没有任何统计、埋点或数据回传。联网只用于向百度百科和 PubChem 查询试剂信息，用户查了什么不会被记录到你的服务器上。

---

## 六、如果只想要最省事的方案

其实不挂服务器也能用：把 `投料计算器（预览用，不用上传）.html` 这一个文件直接发给对方，**双击就能打开**，功能完全一样，只是没有图标、不能离线缓存。

如果你觉得部署麻烦，可以直接跟对方说用这个文件。

---

再次感谢！
