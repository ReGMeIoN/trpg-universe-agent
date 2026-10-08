# 🎩 杰克 · 立绘外貌提示词（NovelAI）

> 由 `trpg-agent` 从项目证据链提取 · 2026-09-13
> 证据来源：`数据\头像\杰克.jpg`（KP 当年那张「男人的样貌：」参考图）+ 转写/提炼稿 + 杰克档案
> 原则：**canon 与推断严格分开标注**；玩梗内容一律不写进提示词（见第四节）

---

## 一、证据链（每条都可追溯）

| 类别 | 内容 | 出处 |
|---|---|---|
| ✅ canon | 「房间中央，站着一个**戴着黑色礼帽的年轻男人**」 | `素材\segments\异世界大逃杀_段1_2024-07-30.txt` L80 |
| ✅ canon | KP 打出「**男人的样貌：**」后**发的是一张图**（非文字） | 同上 L81-L83 |
| ✅ canon | **黑礼帽绅士**形象把前作角色逐一拖入异世界大逃杀 | `characters.json` `cross_jieke.note` |
| ✅ canon | 「**黑礼帽的年轻男人**，站在圆桌/大厅中央」「大厅中央站着一个黑色、带着黑色礼帽的年轻男人」 | `魔法少女五_段1提炼.md` L23 / L49 |
| ✅ canon | 「一个戴着**高礼帽**的男人出现，拍着拍手」 | `魔法少女五_段1_…txt` L141（视频轨转写） |
| ⚠️ 待确认 | 「**面具男=杰克**（剧透确认，剧内未点名）」；对应正文「一个**黑礼帽西装面具男**和一个刀疤脸在谈话」 | `异世界大逃杀_段2提炼.md` L42 / `…段2_…txt` L958 |
| ✅ canon | 自报「我的名字叫**杰克/捷克**，是这场游戏的组织者」；称玩家「**小羊们**」；打响指发地图、凭空消失；「**杀手/收割者**」气质、烂俗剧本的调味者 | `杰克档案.md` |
| ❌ 剔除 | 「章鱼怪物」「巨大机甲」「杰克机械降神」= 玩家玩梗，档案已明确剔除 | `杰克档案.md` 第三节 |
| ❌ 剔除 | 蓝色系（像素里几乎不存在，见下） | 图像分析 |

**「男人的样貌」用的是图** —— 所以外貌的真源是 `数据\头像\杰克.jpg`，任何文字提示词都只是它的近似。
→ **强烈建议用 NAI 的 Precise Reference / Vibe Transfer 直接引用这张图**（见第五节）。

---

## 二、参考图配色（客观像素数据，非猜测）

对 `杰克.jpg`（1920×1658）与 `杰克大笑.mp4` 的 3 帧（960×960）做分带色彩统计，**4 份样本高度一致**：

| 类别 | 占比 | 位置倾向 |
|---|---|---|
| **白** | 45~55% | 四角为**纯白 #ffffff**（背景白）；中段最多 → 白衬衫/白衣 |
| **深红棕 / 酒红栗** | 22~36% | **下 1/3 最多（32~48%）** → 主体衣物为酒红/栗色 |
| **黑** | 8~17% | 上 1/3 与下 1/3 都有（帽/发 + 裤/鞋/描边） |
| 肤色 | 3~6% | 中位高度 39~68%（脸/手） |
| **绯红（点缀 3~5%）** | 3~5% | 上 1/3 偏多 → 可能是帽带/衣饰/瞳色任一处 |
| 灰 | 3~5% | — |
| **蓝** | **0.2~0.4%** | 可忽略 → **不要加蓝眼/蓝发** |

整体明暗：暗 33% / 中 16% / 亮 52%，对比强（舞台灯光感）。

> ⚠️ 像素只能证明**配色分布**，不能证明「哪块是什么部位」。所以下面提示词里
> **颜色是硬证据**，**款式/发型/瞳色是推断或待确认**。

---

## 三、NovelAI 提示词（可直接粘贴）

### 3.1 主提示词 · 主形象（黑礼帽绅士，无面具）★推荐

```
{best quality}, {amazing quality}, very aesthetic, absurdres, highres,
1boy, solo, handsome young man, mature male, tall, slender,
{black top hat}, {hat ribbon}, short black hair, {sharp eyes}, {red eyes},
pale skin, {confident smile}, {grinning}, {smug}, {joking around}, dark atmosphere,
{white dress shirt}, {black necktie}, {burgundy long coat}, {dark red coat}, black trousers, black leather shoes, {white gloves},
standing, looking at viewer, {one hand raised}, snapping fingers,
{white background}, {simple background}, {full body}, {portrait}, cowboy shot,
{dramatic lighting}, {rim light}, {chiaroscuro}, {high contrast}, {stage spotlight}
```

**权重语法**（NAI 两套都行，你惯用哪套用哪套）
- 花括号：`{tag}` = ×1.05，`{{tag}}` = ×1.10，`[tag]` = ×0.95
- 精确权重：`1.4::black top hat::`、`0.8::dark atmosphere::`

### 3.2 主提示词 · 面具形态（备用，对应「面具男=杰克」那条待确认）

把上面两行替换掉即可：

```
{black top hat}, {black suit}, {white half mask}, {masks covering the eyes},
short black hair, {sharp eyes}, pale skin, {slight smile},
```
> 若你确认「面具男」是独立 NPC 而非杰克，本段直接废弃。

### 3.3 负面提示词（Undesired Content）

```
lowres, {worst quality}, {low quality}, {normal quality}, bad anatomy, bad hands,
extra fingers, fewer fingers, extra limbs, missing limbs, deformed, disfigured,
jpeg artifacts, signature, watermark, username, text, error, blurry, cropped,
{blue eyes}, blue hair, blonde hair, {octopus}, {tentacles}, {mecha}, {robot},
{monster}, {giant robot}, 3d, realistic, photo, nsfw
```
> 后段三个是**针对性负向**：把「章鱼怪物／巨大机甲」这类玩梗形象从生成空间里挤出去，
> 同时锁死蓝色系（避免偏色）。`nsfw` 按你的习惯保留或去掉。

### 3.4 质量词串（v4/v5 常用）

```
best quality, amazing quality, very aesthetic, absurdres, highres
```
（放进主提示词开头即可，不必再另起）

### 3.5 构图 / 视角 / 打光

| 想要 | 加这些 |
|---|---|
| 半身立绘 | `upper body, portrait, looking at viewer, {{{white background}}}` |
| 全身立绘 | `full body, standing, from front, {{simple background}}` |
| 登场压迫感 | `low angle, from below, {dramatic lighting}, {rim light}, dark room, {black round table}` |
| 收割者气质 | `{elegant}, {villain}, {cruel smile}, {theatrical}, {stage}`, 背景 `{spotlight}` |
| 概念化（S05 终局） | `{concept art}, {fractured reality}, {glitch}, {black hole}, {storybook pages}` |

### 3.6 尺寸与参数（起点值，按你版本微调）

| 场景 | 分辨率 | 备注 |
|---|---|---|
| 单人立绘（竖） | **832 × 1216** | 标准竖构图，最适合立绘 |
| 正方形（头像/表情） | 1024 × 1024 | 视频参考图就是 1:1 |
| 双人 / 群像（横） | 1216 × 832 | 多角色用，配 3.7 的格式 |

- 采样步数 28、Guidance 5~6、Rescale 0 作为起点；出图偏软就提 Guidance，偏硬就降。
- NAI v4.5+ 支持更高分辨率，但**立绘没必要盲目拉大**，832×1216 先定妆再放大。

### 3.7 多角色格式（杰克 vs 小羊 / 杰克与雪人）

```
2boys, 1girl, {black top hat}, {white background}, simple background, full body,
char1: 1boy, {black top hat}, short black hair, {red eyes}, {burgundy long coat}, {confident smile}, smug,
char2: 1boy, {sheep ears}, {white coat}, trembling, surprised, {sweatdrop},
```
> `char1:` / `char2:` 是 NAI 的分角色写法（个别版本行为不同，以你实测为准）；角色块内**只写该角色的特征**，场景词放最前。

### 3.8 画师串（这一项你自己定，我给方向）

画师串是**风格偏好**，取决于你想要的味道；而且 v4.5/v5 对画师 tag 的响应与你早前用 v3 时不一样，
我不好替你拍板。给你几组**方向词**代替硬塞画师名：

| 想要的味道 | 方向词 |
|---|---|
| 干净赛璐璐 / 动画截图感 | `anime coloring, cel shading, flat color, clean lines` |
| 厚涂剧场感（配登场戏） | `thick painting, dramatic shading, rich shadow, painterly` |
| 复古绅士插画 | `art nouveau, vintage illustration, ornate frame` |
| 万圣节/提灯黑幽默 | `halloween, jack-o'-lantern motif, gothic` |

你把惯用的 2~3 个画师名给我，我按 NAI 权重语法排好给你。

---

## 四、写提示词时必须避开的坑（canon 铁律）

| 禁止 | 原因 |
|---|---|
| octopus / tentacles / mecha / giant robot | 玩家玩梗（「杰克=章鱼怪物」「巨型机甲」），档案已剔除 |
| 「机械降神」类要素 | 牢昌的场外玩梗（伪人杀） |
| 蓝色系 | 像素里几乎不存在（0.2~0.4%），会偏色 |
| 给杰克「角色卡」式装扮 | canon：**「杰克没有卡」=机制怪**，不是普通 PC/NPC |
| 把他的形象画成某个具体玩家 | **角色 ≠ 玩家**；杰克没有 `played_by` |

---

## 五、落地配方：Precise Reference 为主（主推）

因为「男人的样貌」本来就是图，**让图定形、提示词只管颜色与氛围**是最稳的路径。

### 5.1 三条参数起点

| 参数 | 起点值 | 调法 |
|---|---|---|
| 参考图 | `<工作区>\数据\头像\杰克.jpg`（1920×1658，近正方） | 想连构图一起沿用就把画幅也调近 1:1；只想要人物就用 832×1216 竖版 |
| **信息提取量** | 中（约 50%） | **形不准 → 往上调**；太像描图/失去风格 → 往下调 |
| **参考强度** | 0.5~0.6 | 往上更贴设计，往下更有发挥；超过 ~0.8 容易变成"复刻" |
| 采样 | 步数 28 / Guidance 5~6 / Rescale 0 | 出图偏软提 Guidance，偏硬降 |

> 各版本滑块命名与取值范围不同，以上是**调参方向**，不是绝对刻度——按你面板上的实际标尺映射。

### 5.2 配套提示词（**精简版**，与参考图分工）

```
{best quality}, {amazing quality}, very aesthetic, absurdres, highres,
1boy, solo, {black top hat}, {burgundy long coat}, {white dress shirt}, {white gloves},
{confident smile}, {smug}, {sharp eyes},
standing, looking at viewer, upper body, portrait, {simple background},
{dramatic lighting}, {rim light}, {high contrast}, {stage spotlight}
```

**与 3.1 的差别（重要）**——配合参考图时**删掉**这些，避免提示词与参考图互相拉扯：

| 删除 | 原因 |
|---|---|
| `red eyes` | 瞳色待确认（那 3~5% 绯红定位不明），**交给参考图** |
| `short black hair` | 发色/发型同理交给参考图 |
| `black necktie` / `black trousers` / `black leather shoes` / `snapping fingers` | 款式细节交给参考图，写死了反而两张皮 |
| `full body` | 参考图是近正方半身倾向，先出半身更稳 |

**保留**的都是有硬证据的：`black top hat`（canon 文本 + 上段黑 13~14%）、
`burgundy long coat` / `white dress shirt`（下 1/3 酒红 32~48%、中段白 57%）、表情与打光（舞台感）。

### 5.3 背景怎么处理

| 想要 | 写法 |
|---|---|
| 沿用白底（参考图就是纯白 #ffffff） | `{white background}, {simple background}` |
| 换场景（黑圆桌 / 新宿墓碑 / 归墟之眼） | 去掉 `white background`，改成场景词 + `{simple background}`，参考图只锁人物 |

> 参考图是白底，若你不写背景词，**白底会跟着串过来**——这不是 bug，是参考图在起作用。

### 5.4 迭代纪律（不然你会白烧图）

1. **固定 seed**：第一版满意后记下 seed，之后只改**一个**变量（一个权重 / 一个词）。
2. **单变量对比**：一次改三个词，你永远不知道是哪个起了作用。
3. **先定形，再上风格**：形准了再加方向词（`cel shading` / `painterly` 等），别一开始就堆风格词。
4. **负向保持稳定**：`octopus / tentacles / mecha / robot` 这几个别删（防玩梗形象回流）。

### 5.5 常见症状 → 对策

| 症状 | 对策 |
|---|---|
| 人物形不像 | 信息提取量 ↑、参考强度 ↑ |
| 太像原图复刻、没有新意 | 信息提取量 ↓、参考强度 ↓，改用 Vibe Transfer（抽 0.6~0.8） |
| 画面整体偏白、背景被带跑 | 加 `{simple background}` + 明确背景词 |
| 颜色被参考图带偏（比如衣物变酒红但你要黑） | 在正向里把目标色提权重：`{{black coat}}`，并在负向加 `burgundy coat` |
| 眼睛/发色不对 | 那是参考图在说话 —— 要么接受，要么把 3.1 的 `red eyes` / `short black hair` 加回来强制覆盖 |


---

## 六、我无法从像素确定的 5 件事（你确认后我改稿）

1. **帽子**：纯黑？酒红帽带？高礼帽还是圆顶？（canon 写「黑礼帽」+「高礼帽」，图里上段有黑 13~14% 与红 5~9%）
2. **发型/发色**：黑短发？（黑占 8~17%，但无法区分是发还是帽）
3. **瞳色**：绯红是瞳色，还是帽带/衣饰？**图里只有 3~5% 绯红，无法定位**
4. **服装款式**：酒红长外套？白衬衫打领带？有白手套吗？（下 1/3 酒红 32~48%、黑 24~29%）
5. **面具**：那个「面具男=杰克」要不要作为第二形象？

> 你可以直接看图回答，或者干脆只回「按 3.1 来」——那我就不动，用参考图定形。
