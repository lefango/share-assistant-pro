# 玄天典籍 · 界面模块设计说明

## 一、设计取舍

### 气质
「古籍藏阁」——暗金底色、琥珀书签、玉青点缀。每个区块左侧有 3px 琥珀竖条，像书签夹页。
右侧分享栏顶部有 2px 色带，随状态变色（待机=蓝灰，运行=翠绿，错误=朱红）。

### 形状语言
- 按钮：胶囊（`R_CAPSULE = 20`）
- 卡片：4px 直角（`R_CARD = 4`），保留收口感，区别于现版本的 14px 大圆角
- 分组 chip：胶囊（`R_CHIP = 16`）
- 输入框：胶囊（`R_CAPSULE`），区别于现版本的方形输入框

### 配色
| 色号      | 用途                         |
|-----------|------------------------------|
| `#0d1119` | 背景（bg）                   |
| `#111820` | 侧栏/右栏底色（panel）       |
| `#182230` | 卡片底色（card）             |
| `#1e2d40` | 卡片 hover（card_hover）     |
| `#2a3d50` | 普通边框（border）           |
| `#3d5a72` | 高亮边框（border_hi）        |
| `#c9922a` | 琥珀金·主 accent             |
| `#e3a83a` | 琥珀金 hover                 |
| `#4fc3c8` | 玉青·辅 accent2              |
| `#5ecb8a` | 成功/运行（ok）              |
| `#e9b233` | 警告（warn）                 |
| `#e05a52` | 危险/停止（danger）          |
| `#dde6f0` | 主文字（text）               |
| `#7a99b4` | 注释文字（text_dim）         |

### 字体层级
| 常量       | 大小  | 用途               |
|------------|-------|--------------------|
| `FS_TITLE` | 16px  | 页标题（粗）        |
| `FS_SECTION`| 14px | 分区标题（粗）      |
| `FS_BODY`  | 12px  | 正文               |
| `FS_SMALL` | 11px  | 注释/按钮标签      |
| `FS_MICRO` | 10px  | 路径/版本等极小信息 |

### 图标
使用 Unicode 几何符号，不用 emoji，避免字体替换乱码：
`◈ ▷ ♩ ◫ ◉ ◆ ▤ ⇅ ▣ ⊡`

---

## 二、可调项（全部在 view.py 顶部常量区）

```python
# 字号
FS_TITLE    = 16
FS_SECTION  = 14
FS_BODY     = 12
FS_SMALL    = 11
FS_MICRO    = 10

# 间距
PAD_OUTER   = 18   # 外边距
PAD_INNER   = 14   # 卡片内边距
PAD_ROW     = 6    # 行间距
PAD_BTN     = 8    # 按钮间距

# 形状
R_CAPSULE   = 20   # 胶囊按钮/输入框圆角
R_CARD      = 4    # 卡片圆角
R_CHIP      = 16   # 分组 chip 圆角

# 布局宽度
W_SIDEBAR   = 192  # 左侧导航栏宽
W_RAIL      = 300  # 右侧分享栏宽

# 书签竖条宽度
BOOKMARK_W  = 3
```

配色全部走 `theme["colors"]`，直接修改 `skin/xuantian/theme.json`（或 preview.py 顶部的 `THEME` 字典）即可，无需改 view.py 代码。

---

## 三、文件说明

| 文件         | 说明                                              |
|--------------|---------------------------------------------------|
| `view.py`    | 界面本体，`class ShareView(ctk.CTkFrame)`         |
| `preview.py` | 独立预览，假数据，`python app\ui\xuantian\preview.py` |
| `README.md`  | 本文件                                            |

---

## 四、接入方式

```python
from app.ui.xuantian.view import ShareView

view = ShareView(master=root, theme=skin.load("xuantian"), on={
    "share": lambda: service.start(...),
    "stop":  lambda: service.stop(),
    # ... 其余回调
})
view.pack(fill="both", expand=True)

# 之后通过 set_* 方法推入数据
view.set_state("running", "")
view.set_links(share_url, receive_url)
view.set_files(items)
```

---

## 五、已知限制

- 拖拽依赖 `tkinterdnd2`，若未装则静默忽略（不报错）
- 二维码依赖 `qrcode` + `Pillow`，均已在项目中安装
- 只有深色主题，浅色未实现（产品需求未要求）
- 文件图标为通用几何符号，未按文件扩展名细分（扩展点）
