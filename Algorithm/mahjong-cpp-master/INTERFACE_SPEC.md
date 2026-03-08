# mahjong-cpp 对接接口说明

本文档用于说明 `mahjong-cpp-master` 在“Crawler/状态采集端 -> 算法服务端 -> HUD/展示端”链路中的输入与输出格式。

文档内容基于当前源码实现整理，重点描述：

- 请求端需要准备什么数据
- 算法端实际接收什么字段
- 算法端返回什么字段
- 每个变量的类型、含义、取值范围
- 当前实现中需要特别注意的行为差异

## 1. 对接模型

推荐的对接方式如下：

1. Crawler 从雀魂界面或通信中采集当前局面。
2. Crawler 将当前局面整理为一个 JSON 请求。
3. 本地运行 `mahjong-cpp` 的 HTTP 服务端。
4. Crawler 通过 `POST` 将 JSON 发给算法服务。
5. 算法服务返回推荐切牌、有效牌、听牌率、和了率、期待值等结果。
6. HUD 读取返回结果并展示。

默认服务端示例监听：

- URL: `http://localhost:50000`
- Method: `POST`
- Content-Type: `application/json`

## 2. 两端职责

### 2.1 Crawler / 状态采集端输入

Crawler 侧需要从对局中尽量还原以下信息：

- 当前手牌
- 当前是否为 13 张或 14 张状态
- 副露信息
- 场风
- 自风
- 宝牌指示牌
- 是否启用赤宝牌、里宝牌等规则
- 如果可能，统计剩余牌山 `wall`

### 2.2 算法服务端输出

算法端根据请求数据输出：

- 向听数
- 每个候选舍牌对应的有效牌
- 每巡听牌率
- 每巡和了率
- 每巡期待值
- 搜索状态数量
- 计算耗时

## 3. 通用数据类型

下面这些类型会在请求和响应中反复出现。

### 3.1 Tile

类型：

- `integer`

范围：

- `0..36`

含义：

- 牌的整数编码

编码表：

| 编码 | 牌 |
| --- | --- |
| `0..8` | `1m..9m` |
| `9..17` | `1p..9p` |
| `18..26` | `1s..9s` |
| `27` | `1z` 东 |
| `28` | `2z` 南 |
| `29` | `3z` 西 |
| `30` | `4z` 北 |
| `31` | `5z` 白 |
| `32` | `6z` 发 |
| `33` | `7z` 中 |
| `34` | `0m` 赤5万 |
| `35` | `0p` 赤5筒 |
| `36` | `0s` 赤5索 |

说明：

- `34..36` 是赤宝牌专用编码。
- 普通 `5m/5p/5s` 仍然使用 `4/13/22`。
- 如果手牌里有赤5，通常会同时占用“普通5的计数”和“赤5的计数”这一层内部表示，但请求层只需要按上面的整数数组传入牌列表即可。

### 3.2 Meld

类型：

```json
{
  "type": 0,
  "tiles": [0, 0, 0]
}
```

字段说明：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `type` | `integer` | 是 | 副露类型 |
| `tiles` | `integer[]` | 是 | 该副露包含的牌 |

`type` 枚举：

| 值 | 含义 |
| --- | --- |
| `0` | `Pong`，碰 |
| `1` | `Chow`，吃 |
| `2` | `ClosedKong`，暗杠 |
| `3` | `OpenKong`，明杠 |
| `4` | `AddedKong`，加杠 |

说明：

- `tiles` 长度通常为 3 或 4。
- 当前实现不会帮你纠正副露是否合法，Crawler 侧应尽量保证正确。

### 3.3 Wall

类型：

- `integer[37]`

含义：

- 每一种牌当前在“剩余牌山/未知牌池”中的剩余张数

索引规则：

- 索引与 `Tile` 编码一致

值域建议：

- 普通牌索引 `0..33`：`0..4`
- 赤牌索引 `34..36`：`0..1`

说明：

- 这是**剩余枚数数组**，不是牌列表。
- 如果你能从 crawler 统计出全场公开信息，建议自己构造这个数组。
- 如果不传，服务端会根据当前手牌、副露和宝牌指示牌自动估算一个默认 `wall`。

### 3.4 Shanten 类型标志

类型：

- `integer`

含义：

- 表示向听数是按哪一种和牌形计算得到的

枚举：

| 值 | 含义 |
| --- | --- |
| `1` | 一般形 |
| `2` | 七对子 |
| `4` | 国士无双 |
| `7` | 三者都参与比较 |

说明：

- 某些位置会返回多个类型并列成立，此时会按位或组合。

## 4. 请求体定义

算法服务端接收的请求对象如下：

```json
{
  "enable_reddora": true,
  "enable_uradora": true,
  "enable_shanten_down": true,
  "enable_tegawari": true,
  "enable_riichi": true,
  "round_wind": 27,
  "dora_indicators": [30],
  "hand": [1, 1, 1, 4, 5, 6, 12, 13, 14, 20, 20, 20, 28, 28],
  "melds": [],
  "seat_wind": 27,
  "version": "0.9.1"
}
```

### 4.1 顶层字段

| 字段 | 类型 | 必填 | 含义 | 备注 |
| --- | --- | --- | --- | --- |
| `enable_reddora` | `boolean` | 是 | 是否启用赤宝牌 | 影响赤5与剩余牌计算 |
| `enable_uradora` | `boolean` | 是 | 是否启用里宝牌期望值 | 只影响期望值相关计算 |
| `enable_shanten_down` | `boolean` | 是 | 是否允许“向听倒退”的搜索 | 用于更远视的打牌搜索 |
| `enable_tegawari` | `boolean` | 是 | 是否允许手变搜索 | 用于扩展未来分支 |
| `enable_riichi` | `boolean` | 是 | 是否允许听牌后立直 | 当前实现里会被强制开启，见文末注意事项 |
| `round_wind` | `integer` | 是 | 场风 | 只能取 `27/28/29/30` |
| `dora_indicators` | `integer[]` | 是 | 宝牌指示牌列表 | 长度 `0..5` |
| `hand` | `integer[]` | 是 | 当前手牌牌列表 | 长度 `1..14`，实际应满足麻将牌数规则 |
| `melds` | `Meld[]` | 是 | 当前副露列表 | 长度 `0..4` |
| `seat_wind` | `integer` | 是 | 自风 | 通常也是 `27/28/29/30` |
| `version` | `string` | 是 | 请求版本号 | 必须与程序编译版本一致 |
| `wall` | `integer[37]` | 否 | 剩余牌山计数 | 不传则自动估算 |
| `ip` | `string` | 否 | 客户端标识/IP | 用于日志 |

### 4.2 字段详细说明

#### `enable_reddora`

- 类型：`boolean`
- 说明：是否把赤5当成有效存在的牌进行建模
- 影响：
  - 手牌表示
  - `wall` 剩余枚数
  - 期望值计算

#### `enable_uradora`

- 类型：`boolean`
- 说明：是否在期待值中考虑里宝牌加分
- 影响：
  - `exp_score`
- 不影响：
  - 向听数
  - 有效牌
  - 舍牌候选

#### `enable_shanten_down`

- 类型：`boolean`
- 说明：搜索过程中是否允许出现“本步操作后向听数更差，但未来更优”的分支
- 典型用途：
  - 允许为了更大打点或更好进张，暂时退向听

#### `enable_tegawari`

- 类型：`boolean`
- 说明：是否允许把“手变”也算入未来搜索
- 作用：
  - 使推荐不只考虑眼前有效牌，还会考虑未来换形

#### `enable_riichi`

- 类型：`boolean`
- 说明：理论上表示听牌后是否考虑立直
- 实际代码行为：
  - 在期待值搜索中会被强制改成 `true`
- 因此：
  - 这个字段目前更像“预留字段”，不能完全代表最终行为

#### `round_wind`

- 类型：`integer`
- 取值：
  - `27` 东场
  - `28` 南场
  - `29` 西场
  - `30` 北场

#### `dora_indicators`

- 类型：`integer[]`
- 内容：
  - 宝牌指示牌，不是宝牌本身
- 示例：
  - 东作为指示牌时传 `27`

#### `hand`

- 类型：`integer[]`
- 内容：
  - 当前自家手牌列表
- 说明：
  - 13 张时表示“轮到摸牌前”的状态
  - 14 张时表示“轮到出牌时”的状态
- 这个区别会直接影响返回结果的 `stats` 结构

#### `melds`

- 类型：`Meld[]`
- 内容：
  - 当前自家副露

#### `seat_wind`

- 类型：`integer`
- 说明：
  - 当前玩家自风

#### `version`

- 类型：`string`
- 说明：
  - 服务端会检查版本字符串是否与编译版本一致
- 示例：
  - `0.9.1`

#### `wall`

- 类型：`integer[37]`
- 说明：
  - 可选
  - 传入后，算法会直接按你提供的剩余牌进行搜索
  - 不传则自动根据当前牌面生成默认墙

建议：

- 如果 crawler 能统计全场明牌、宝牌指示牌、自己手牌和副露，尽量自己生成 `wall`
- 这样 HUD 的推荐会比默认估算更可信

#### `ip`

- 类型：`string`
- 说明：
  - 仅用于记录日志或来源标识

## 5. 请求端应如何准备数据

如果你要从 crawler 组织请求，建议按下面思路准备。

### 5.1 必需信息

这些字段基本必须从当前局面恢复：

- `hand`
- `melds`
- `round_wind`
- `seat_wind`
- `dora_indicators`
- `version`

### 5.2 推荐补充信息

如果能拿到，建议补齐：

- `wall`

原因：

- 默认 `wall` 只会扣除手牌、副露、宝牌指示牌
- 不会自动扣除河里已经打出的牌，除非你自己统计
- 因此缺少 `wall` 时，期待值会偏理想化

### 5.3 13 张与 14 张的区别

#### 当 `hand` 长度为 13

表示：

- 当前处于摸牌前状态

返回结果：

- `stats` 通常只有 1 项
- `tile` 会是特殊值 `-1`

#### 当 `hand` 长度为 14

表示：

- 当前处于出牌选择状态

返回结果：

- `stats` 会按“每个可打的牌种”返回一项
- 最适合直接用于 HUD 的“推荐切牌列表”

## 6. 响应体定义

### 6.1 成功响应外层结构

```json
{
  "success": true,
  "request": {},
  "response": {}
}
```

### 6.2 失败响应外层结构

```json
{
  "success": false,
  "request": {},
  "err_msg": "错误信息"
}
```

### 6.3 顶层响应字段

| 字段 | 类型 | 成功时 | 失败时 | 含义 |
| --- | --- | --- | --- | --- |
| `success` | `boolean` | 有 | 有 | 是否成功 |
| `request` | `object` | 有 | 有 | 服务端回显的原始请求 |
| `response` | `object` | 有 | 无 | 计算结果 |
| `err_msg` | `string` | 无 | 有 | 错误信息 |

## 7. `response` 对象定义

成功时，`response` 对象大致如下：

```json
{
  "shanten": {
    "all": 1,
    "regular": 1,
    "seven_pairs": 3,
    "thirteen_orphans": 8
  },
  "stats": [],
  "searched": 12345,
  "time": 9876,
  "config": {
    "t_min": 1,
    "t_max": 18,
    "sum": 70,
    "extra": 1,
    "shanten_type": 7,
    "calc_stats": true,
    "num_tiles": 14
  }
}
```

### 7.1 `shanten`

类型：

```json
{
  "all": 0,
  "regular": 0,
  "seven_pairs": 2,
  "thirteen_orphans": 8
}
```

字段说明：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `all` | `integer` | 综合最优向听数 |
| `regular` | `integer` | 一般形向听数 |
| `seven_pairs` | `integer` | 七对子向听数 |
| `thirteen_orphans` | `integer` | 国士无双向听数 |

取值说明：

- `-1`：已经和牌
- `0`：听牌
- `1+`：几向听

### 7.2 `stats`

类型：

- `Stat[]`

含义：

- 核心结果数组

不同手牌长度下的行为：

- `13 张手牌`：通常只有 1 个元素，代表当前整体状态
- `14 张手牌`：每个元素对应“打出某张牌后的结果”

#### `Stat` 结构

```json
{
  "tile": 34,
  "tenpai_prob": [0.0, 0.12, 0.23],
  "win_prob": [0.0, 0.03, 0.08],
  "exp_score": [0.0, 320.5, 611.8],
  "necessary_tiles": [
    { "tile": 1, "count": 3 }
  ],
  "shanten": 2
}
```

字段说明：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `tile` | `integer` | 当前候选打牌的牌编码；13 张场景下通常为 `-1` |
| `tenpai_prob` | `number[]` | 每巡听牌率 |
| `win_prob` | `number[]` | 每巡和了率 |
| `exp_score` | `number[]` | 每巡期待值 |
| `necessary_tiles` | `NecessaryTileCount[]` | 进张及其剩余张数 |
| `shanten` | `integer` | 执行该候选后对应的向听数 |

#### `tile`

- 类型：`integer`
- 含义：
  - 14 张时：表示“如果切这张牌”
  - 13 张时：表示当前状态，常见值为 `-1`

#### `tenpai_prob`

- 类型：`number[]`
- 含义：
  - 从第 `t` 巡开始，到未来对应巡次时听牌的概率
- 说明：
  - 数组下标会与 `config.t_min..t_max` 对齐使用
  - UI 使用时应结合 `config.t_min` 和 `config.t_max` 读取

#### `win_prob`

- 类型：`number[]`
- 含义：
  - 从当前状态出发，到各巡的和了概率

#### `exp_score`

- 类型：`number[]`
- 含义：
  - 到各巡的期待得点
- 单位：
  - 点数

#### `necessary_tiles`

- 类型：`NecessaryTileCount[]`

结构：

```json
{
  "tile": 1,
  "count": 3
}
```

字段说明：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `tile` | `integer` | 进张牌编码 |
| `count` | `integer` | 该牌当前剩余张数 |

解释：

- 可以理解为“这手/这次舍牌之后，哪些牌是有效牌，以及各自还剩几张”

#### `shanten`

- 类型：`integer`
- 含义：
  - 当前候选分支对应的向听数

### 7.3 `searched`

- 类型：`integer`
- 含义：
  - 搜索过程中生成的图节点数量
- 用途：
  - 粗略评估这次计算复杂度

### 7.4 `time`

- 类型：`integer`
- 单位：
  - 微秒 `us`
- 含义：
  - 本次计算耗时

### 7.5 `config`

类型：

```json
{
  "t_min": 1,
  "t_max": 18,
  "sum": 70,
  "extra": 1,
  "shanten_type": 7,
  "calc_stats": true,
  "num_tiles": 14
}
```

字段说明：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `t_min` | `integer` | 计算起始巡目 |
| `t_max` | `integer` | 计算终止巡目 |
| `sum` | `integer` | 参与计算的剩余牌总数 |
| `extra` | `integer` | 允许扩展搜索的额外交换范围 |
| `shanten_type` | `integer` | 使用的向听类型标志 |
| `calc_stats` | `boolean` | 是否真的计算了概率和期待值 |
| `num_tiles` | `integer` | 当前输入牌数加副露折算后的总牌数 |

#### `calc_stats`

这个字段很重要：

- `true`：说明 `tenpai_prob / win_prob / exp_score` 有意义
- `false`：说明只做了轻量计算，通常只看 `necessary_tiles` 和 `shanten`

当前实现中，服务端会在总向听数大于 `3` 时关闭完整统计计算。

## 8. 失败响应常见错误

常见错误场景包括：

- JSON 格式不合法
- 缺少必填字段
- `version` 不匹配
- 某种牌总数超过 4 张
- 提供的 `wall` 比理论剩余张数还大
- 手牌张数非法
- 手牌已经是和牌形

失败示例：

```json
{
  "success": false,
  "request": {
    "...": "..."
  },
  "err_msg": "Invalid number of tiles."
}
```

## 9. 对 HUD 最有用的字段

如果你的目标是在 HUD 上显示推荐出牌，可以优先使用：

- `response.stats[].tile`
- `response.stats[].shanten`
- `response.stats[].necessary_tiles`
- `response.stats[].exp_score`
- `response.stats[].win_prob`
- `response.stats[].tenpai_prob`

一个常见排序策略是：

1. 先按某一巡的 `exp_score` 降序
2. 同分时按 `win_prob` 降序
3. 再按 `necessary_tiles` 总张数降序

## 10. 当前实现中的注意事项

以下内容不是理想接口设计，而是当前源码中的真实行为。

### 10.1 请求字段名应使用 `hand`

源码解析时实际读取的是：

- `hand`

不是：

- `hand_tiles`

因此在真正对接时，请使用 `hand`。

### 10.2 `enable_riichi` 当前会被强制开启

在期待值搜索实现中，代码会强制：

- `config.enable_riichi = true`

这意味着：

- 即便请求里传 `false`
- 实际期待值搜索仍会偏向“听牌后立直”的路线

### 10.3 `wall` 不传时会自动估算，但不够真实

自动估算只会考虑：

- 手牌
- 副露
- 宝牌指示牌

不会天然完整反映：

- 所有人弃牌河
- 对手暗手已知信息
- 其他公开信息

所以如果 crawler 能做牌数统计，强烈建议自己传 `wall`。

### 10.4 `stats` 的条目不是“具体牌实例”，而是“牌种”

例如手里有两张相同牌：

- 返回里不会区分“第一张 5p”还是“第二张 5p”
- 只会返回 `tile = 13` 这种牌种级结果

HUD 如果要高亮具体实体牌，需要自己做映射。

### 10.5 期待值功能依赖运行时资源文件

期待值相关计算除配置 JSON 外，还依赖：

- `uradora.bin`

如果运行环境缺少这个文件，期待值相关功能可能无法正常工作。

## 11. 建议的最小对接方案

如果你现在要先把 crawler 和算法连起来，建议先做最小版本请求：

- `enable_reddora`
- `enable_uradora`
- `enable_shanten_down`
- `enable_tegawari`
- `enable_riichi`
- `round_wind`
- `dora_indicators`
- `hand`
- `melds`
- `seat_wind`
- `version`

等最小链路跑通后，再补：

- `wall`

这样能最快看到 HUD 推荐效果。

## 12. 推荐的 HUD 展示文案映射

你可以把返回数据映射成这样的 HUD 内容：

- 推荐切：`tile`
- 切后向听：`shanten`
- 有效牌：`necessary_tiles` 的牌名列表
- 有效牌总数：`necessary_tiles[].count` 求和
- 第 N 巡听牌率：`tenpai_prob[N]`
- 第 N 巡和了率：`win_prob[N]`
- 第 N 巡期待值：`exp_score[N]`

如果只想做最基础 HUD，可以先展示：

- 推荐切牌
- 切后向听
- 有效牌种类数
- 有效牌总张数

如果想做增强版 HUD，再展示：

- 听牌率曲线
- 和了率曲线
- 期待值曲线

