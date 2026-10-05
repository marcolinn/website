# 我的书房

一个用 Markdown 写、用 Python 生成、托管在 Cloudflare 上的个人网站。

主要内容：**读书笔记**（主体）、文章、旅行记录、照片。

---

## 一、目录结构

```
Website/
├─ build.py              ← 生成器（唯一需要动的代码）
├─ check.py              ← 构建后自检（死链、缺标题），也是部署闸门
├─ sync_book_page.py     ← 把《中国租界通史》那套手工网页同步进来（见第四节末）
├─ content/              ← 所有内容都在这里，写 Markdown 就行
│   ├─ about.md          ← 关于页
│   ├─ books/            ← 每本书一个 .md
│   ├─ blog/             ← 每篇文章一个 .md
│   └─ travel/           ← 每条旅行记录一个 .md
├─ photos/               ← 照片原图丢这里
├─ static/               ← 原样复制到站点根目录的静态资源
│   ├─ style.css         ←   全站样式
│   └─ books/zhongguo-zujie-tongshi/   ← 《中国租界通史》整套手工网页
├─ wrangler.jsonc        ← Cloudflare 部署配置
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

### 整页手工网页（某一本不做成 Markdown 的那种）

`content/books/` 里的书默认按模板生成一个简单详情页。如果某一本你已经做好了整套独立网页
（自带样式和脚本，不是 Markdown），可以把它接进来，以《中国租界通史》为例：

1. 把网页放进 `static/books/<slug>/`，目录名必须和 `content/books/<slug>.md` 的**文件名一致**
   （本例是 `static/books/zhongguo-zujie-tongshi/`）。`static/` 下的东西会被原样复制到站点根目录，
   所以这个目录在线上就是 `/books/zhongguo-zujie-tongshi/`。
2. 在那个 `.md` 的 front matter 里加一行：

   ```yaml
   custom_page: true
   ```

   作用是**让 `build.py` 跳过自动生成详情页**——否则简易模板会把它覆盖掉。
   这本书仍然照常出现在书单和首页（书名、星级、短评都还来自那个 `.md`），
   只是「点进去」看到的是你自己那套页面。

> **原稿在仓库之外**。《中国租界通史》的网页原稿在 `D:\Data\Onedrive\DSH\Book\中国租界通史_网页`
> （177 个文件、14.7 MB），站点只用得到其中三个：`index.html`、`chapters.html`、`assets/`（39 张图，约 2 MB）。
> 原稿改动后，本地跑一次 `python sync_book_page.py` 把它们同步进 `static/`，再照常提交。
> 云端的构建机看不到原稿目录，它只认仓库里的文件——所以 `static/` 里那份是**要提交进 git** 的。

---

## 五、部署到 Cloudflare

当前线上地址：**https://website.marcolinn.workers.dev**

GitHub 仓库：**https://github.com/marcolinn/website** —— 推一个 commit 上去，Cloudflare 会自动重新构建上线。

### 现在用的方式：Worker + 静态资源

Cloudflare 把静态站点也当成一种 Worker——一个**没有脚本、只有静态资源**的 Worker。仓库根目录的 `wrangler.jsonc` 就是干这个的：

```jsonc
{
  "name": "website",              // 必须和 Cloudflare 上那个 Worker 同名
  "compatibility_date": "2026-10-01",
  "assets": {
    "directory": "./public",              // 构建产物目录
    "not_found_handling": "404-page",     // 找不到的路径 → 404.html，带真 404 状态码
    "html_handling": "auto-trailing-slash" // /books/ 带斜杠，/style.css 不带
  }
}
```

**每次 push 之后云端发生的事**：

1. 克隆仓库
2. 跑 **Build command**：`python3 build.py && python3 check.py` → 生成 `public/`
3. 跑 **Deploy command**：`npx wrangler deploy` → 读 `wrangler.jsonc`，把 `public/` 上传

所以 `public/` 不进 git 是对的（`.gitignore` 里挡掉了），云端每次自己生成。

**配置在**：Cloudflare 控制台 → **Workers & Pages** → 点进 `website` → **Settings** → **Build**

| 字段 | 填什么 |
|---|---|
| Build command | `python3 build.py && python3 check.py` |
| Deploy command | `npx wrangler deploy`（默认值，别动） |

> ⚠️ **`Build command` 留空 = 部署失败**。留空时第 2 步被整个跳过，`public/` 不存在，wrangler 就报 `Could not detect a directory containing static files`。第一次部署踩的就是这个坑。改完点 **Retry deployment**，或随便推一个 commit。

> **构建命令末尾为什么要跟 `check.py`**：它会给所有内部链接做一次体检，非零退出码会让构建**失败**。等于给自己上了一道闸——哪天手滑写错一个链接、或者某个页面漏了标题，Cloudflare 会拒绝上线并保留上一个好版本，而不是把坏页面推出去。

> **Python 从哪来**：Cloudflare 的构建镜像自带 **Python 3.13.3**（Workers Builds 是 Ubuntu 24.04），不需要任何环境配置。本项目只用标准库，不用 `pip install`。
> 万一提示找不到 `python3`，把命令里的 `python3` 换成 `python` 再试。

### 另一种方式：Cloudflare Pages（备选）

Pages 同样自带 Python 3.13.3，配置项更少，但 Pages 项目名要**全球唯一**，且一旦选了 Direct Upload 就不能再转 Git。

1. **Workers & Pages** → **Create application** → 选 **Pages** 标签 → **Connect to Git**
2. 授权 GitHub，选 `marcolinn/website` → **Begin setup**
3. 构建配置填：

   | 字段 | 填什么 |
   |---|---|
   | Project name | **不能填 `website`**——`website.pages.dev` 已被别人占用，用 `marcolinn-website` |
   | Production branch | `main` |
   | Framework preset | **None**（预设列表里没有 Python，留着默认值会套错命令） |
   | Build command | `python3 build.py && python3 check.py` |
   | Build output directory | `public` |

4. **Save and Deploy** → 得到 `https://marcolinn-website.pages.dev`

### 绑定自己的域名（可选）

1. 在域名注册商买一个域名（约 ¥50–100/年）
2. Cloudflare 控制台 → 你的 Worker / Pages 项目 → **Settings** → **Domains & Routes**（Pages 里叫 **Custom domains**）→ 添加
3. 输入域名，按提示配置
   - 域名托管在 Cloudflare：一键完成，自动加 DNS 记录
   - 域名在别处：去域名商后台加一条 CNAME，指向 `website.marcolinn.workers.dev`（Pages 则指向 `项目名.pages.dev`）
4. SSL 证书**自动签发、自动续期**，不用管

> Cloudflare 不需要备案。中国大陆可以访问（速度取决于线路），但没有国内节点。

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

Cloudflare 免费版：

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

**改了《中国租界通史》的网页，线上没变？**
`static/books/zhongguo-zujie-tongshi/` 是**同步过来的拷贝**，不是原稿。改完原稿要跑一次 `python sync_book_page.py` 再提交。
另外那一页的样式是内联的、不引 `style.css`，所以它对全站换色不敏感，要单独改。

**想加新栏目（比如"观影"）？**
1. `content/` 下新建 `films/` 文件夹
2. 在 `build.py` 的 `SITE["nav"]` 里加一行 `("观影", "/films/")`
3. 照着 `travel` 那一段复制一份页面生成逻辑
