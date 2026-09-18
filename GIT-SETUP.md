# Git 提交配置

## 提交身份

| 项目 | 值 |
|------|-----|
| 提交姓名 | ZX666X |
| 统一邮箱 | zx19836980213@outlook.com |
| Gitee 账号 | ZX666X |
| GitHub 账号 | ZX466 |

- 统一邮箱已同时绑定 Gitee 与 GitHub 两账号，故一条提交可同时归属两个平台的贡献图。
- 机器全局 git 身份已配置（`git config --global user.name=ZX666X` / `user.email=zx19836980213@outlook.com`），新 clone 仓库无需再单独配置。

## 远程仓库

| 平台 | 地址 |
|------|------|
| GitHub | https://github.com/ZX466/natural-world.git |
| Gitee | https://gitee.com/ZX666X/natural-world.git |

双远程同步推送：`git push origin main && git push gitee main`

## 网络代理

- GitHub 直连网络不通，走本地代理 `127.0.0.1:7897`。
- 已按域名范围配置（仅对 github.com 生效，不影响 Gitee 直连）：

```bash
git config --global http.https://github.com.proxy http://127.0.0.1:7897
```

- 取消代理：`git config --global --unset http.https://github.com.proxy`
