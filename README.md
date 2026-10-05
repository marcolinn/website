# 我的书房

一个用 Markdown 写、用 Python 生成、托管在 Cloudflare Pages 上的个人网站。

主要内容：**读书笔记**（主体）、文章、旅行记录、照片。

---

## 一、目录结构

```
Website/
├─ build.py              ← 生成器（唯一需要动的代码）
├─ content/              ← 所有内容都在这里，写 Markdown 就行
│   ├─ about.md          ← 关于页
│   ├─ books/            ← 每本书一个 .md
│   ├─ blog/             ← 每篇文章一个 .md
│   └─ travel/           ← 每条旅行记录一个 .md
├─ photos/               ← 照片原图丢这里
├─ static/               ← 样式等静态资源（style.css）
└─ public/               ← 构建产物，自动生成，不用管（已 gitignore）
```

---

## 二、本地预览

```powershell
python build.py --serve
```

会自动打开浏览器到 <http://localhost:8000>。

只想重新生成、不预览：

```powershell
python build.py
```

> 需要 Python 3.8+。没有任何第三方依赖，不用 `pip install`。

---

## 三、改站点信息（第一次必做）

打开 `build.py`，最上面有一段 `SITE = {...}`，改这些：

| 字段 | 含义 |
|---|---|
| `title` | 网站名（现在是"我的书房"） |
| `tagline` | 副标题/一句话slogan |
| `author` | 你的名字（显示在页脚和版权行） |
| `description` | 网站描述，会写进搜索引擎的 description |
| `nav` | 顶部导航，增删页面改这里 |

---

## 四、怎么加内容

所有内容都是 Markdown 文件，前面用 `---` 包一段"属性"（front matter），后面写正文。

### 加一本书 → `content/books/文件名.md`

```markdown
---
title: 书名
author: 作者
translator: 译者          # 可选
publisher: 出版社          # 可选
date: 2026-10-05          # 日期，用于排序
rating: 4                 # 1–5 星；填 0 或删掉这一行 = 暂不评分
status: 读过              # 在读 / 读过 / 想读
tags: [历史, 近代史]       # 可选
summary: 一句话短评，会显示在列表页
---

正文写在这里，支持标题、列表、引用、代码块、图片、链接。
```

文件名会变成网址，例如 `wanli-shiwunian.md` → `/books/wanli-shiwunian/`。
**建议用英文或拼音命名**，中文文件名在网址里会被转义成一长串。

### 加一篇文章 → `content/blog/文件名.md`

```markdown
---
title: 标题
date: 2026-10-05
summary: 摘要（可省略，省略就自动截取正文前 90 字）
tags: [随笔]
---

正文……
```

### 加一条旅行记录 → `content/travel/文件名.md`

```markdown
---
title: 徽州七日
place: 安徽 · 黄山 / 黟县 / 歙县
date: 2026-04-12
summary: 摘要
---

正文……
```

### 加照片 → 丢进 `photos/`

把图片放进 `photos/`（支持子文件夹），然后重新 `python build.py`，照片墙会自动生成。

**⚠️ 放之前先压缩**：长边压到 1600px 左右。手机原图一张 3–10 MB，几十张就会让网站变慢、也占满 Cloudflare 的 20000 文件额度以外没必要。
推荐用 <https://squoosh.app/>（免费、在线、可存成 WebP，体积能降 80%）。

### 改"关于"页

直接编辑 `content/about.md`。

---

## 五、部署到 Cloudflare Pages

### 先选路线（这一步不能反悔）

Cloudflare 有两个入口，**创建项目时选定，之后不能互转**：

| | 路线 A：连 Git 仓库 | 路线 B：直接上传 |
|---|---|---|
| 需要 GitHub | 是 | 否 |
| 以后改内容 | `git push`，自动上线 | 每次手动重新拖一次 |
| 能不能互转 | ✗ 不能 | ✗ 不能（官方原文：*You cannot switch to Git integration later*） |

不能互转不等于进死胡同——大不了以后**另建一个新项目**选另一条路线，旧项目删掉即可。但既然要建，一次选对省事。

**建议**：你会持续加读书笔记，选**路线 A**。

### 前期准备

1. 注册 [Cloudflare](https://dash.cloudflare.com/sign-up) 账号（免费，邮箱即可，不用绑卡）
2. 注册 [GitHub](https://github.com/signup) 账号（走路线 B 的话跳过）
3. 本目录**已经是 git 仓库了**（已初始化 + 已提交一次），只差一个远程仓库：

```powershell
cd D:\Data\Onedrive\DSH\Website
# 先在 GitHub 网页上新建一个空仓库（不要勾 Add README / .gitignore），
# 然后把下面这行的「你的用户名」换成你的账号
git remote add origin https://github.com/你的用户名/website.git
git push -u origin main
```

### 路线 A：连 Git 仓库（推荐）

1. Cloudflare 控制台 → **Workers & Pages** → **Create** → 选 **Pages** 标签 → **Connect to Git**
2. 授权 GitHub，选中刚才的仓库 → **Begin setup**
3. 构建配置填：

   | 字段 | 填什么 |
   |---|---|
   | Project name | 随便起，会变成 `项目名.pages.dev` |
   | Production branch | `main` |
   | Framework preset | **None** |
   | Build command | `python3 build.py && python3 check.py` |
   | Build output directory | `public` |

4. 点 **Save and Deploy**，等一两分钟
5. 得到网址 `https://项目名.pages.dev` —— **这个地址是长期有效的**，可以直接发给别人

> **构建命令末尾为什么要跟 `check.py`**：它会给所有内部链接做一次体检，非零退出码会让构建**失败**。等于给自己上了一道闸——哪天手滑写错一个链接、或者某个页面漏了标题，Cloudflare 会拒绝上线并保留上一个好版本，而不是把坏页面推出去。

> **Python 从哪来**：Cloudflare 的构建镜像（v3，Ubuntu 22.04）自带 **Python 3.13.3**，不需要任何环境配置。本项目只用标准库，不用 `pip install`。
> 万一提示找不到 `python3`，把构建命令里的 `python3` 换成 `python` 再试；仍然不行就走路线 B。

### 路线 B：直接上传（不用 Git，30 秒上线）

1. 本地跑一次 `python build.py`
2. Cloudflare 控制台 → **Workers & Pages** → **Create** → **Pages** → **Upload assets**
3. 把 `public` 文件夹里的**所有内容**拖进去（注意是 `public` 里面的东西，不是 `public` 这一层）
4. 点 **Deploy**

> 两个限制：拖拽上传**单次最多 1000 个文件**、单个文件最大 25 MiB。现在这个站只有十几个文件，远够用；但照片攒到上千张时会撞上限，那时要么改用路线 A（Git 集成是 20000 个文件），要么把照片挪到 R2。

### 绑定自己的域名（可选）

1. 在域名注册商买一个域名（约 ¥50–100/年）
2. Cloudflare 控制台 → 你的 Pages 项目 → **Custom domains** → **Set up a custom domain**
3. 输入域名，按提示配置
   - 域名托管在 Cloudflare：一键完成，自动加 DNS 记录
   - 域名在别处：去域名商后台加一条 CNAME，指向 `项目名.pages.dev`
4. SSL 证书**自动签发、自动续期**，不用管

> Cloudflare Pages 不需要备案。中国大陆可以访问（速度取决于线路），但没有国内节点。

---

## 六、以后的日常

改内容 → 三个命令：

```powershell
python build.py --serve                   # 先本地看看效果
python check.py                           # 检查有没有死链、缺标题
git add . ; git commit -m "新增《xxx》读书笔记" ; git push
```

push 之后 Cloudflare 会自动重新构建并上线，大约 1 分钟。

`check.py` 不是必须的，但加完内容跑一下很快——它会告诉你哪个页面缺标题、哪条链接指向了不存在的地址。

> **OneDrive 的一个小脾气**：这个项目在 OneDrive 同步目录里，构建时 OneDrive 偶尔会锁住 `public/` 文件夹。`build.py` 已经处理了这种情况（先整体删、不行就逐个文件删、再不行原地覆盖），最多只会多打一行提示。真遇到"删掉的页面还在"，把 OneDrive 暂停同步再跑一次就行。

---

## 七、免费额度够不够用

Cloudflare Pages 免费版：

| 项目 | 额度 |
|---|---|
| 带宽 / 请求数 | **不限量** |
| 构建次数 | 500 次/月 |
| 单站点文件数 | 20000 个 |
| 单文件大小 | 最大 25 MiB |
| 自定义域名 | 100 个/项目 |

个人站点完全用不完。唯一需要留意的是 **20000 个文件**——如果照片按原图存，几百张就能吃掉可观的比例，所以记得压缩。

---

## 八、常见问题

**中文文件名变成乱码网址？**
用英文/拼音命名 `.md` 文件，`title` 里写中文标题。

**列表页显示的顺序不对？**
按 front matter 里的 `date` 倒序排的，检查日期格式是不是 `YYYY-MM-DD`。

**照片没出现？**
确认格式是 jpg/jpeg/png/webp/gif 之一，并且重新跑过 `python build.py`。

**想换配色？**
`static/style.css` 最上面 `:root` 里的 CSS 变量：`--accent` 是主色（赭石红），`--accent-2` 是辅助色（松绿），`--paper` 是背景色。改这三个就能整体换风格。

**想加新栏目（比如"观影"）？**
1. `content/` 下新建 `films/` 文件夹
2. 在 `build.py` 的 `SITE["nav"]` 里加一行 `("观影", "/films/")`
3. 照着 `travel` 那一段复制一份页面生成逻辑
