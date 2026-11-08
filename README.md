# 我想永远陪伴你

> GitHub：https://github.com/GM888888456/Astrbot_Amo_forever
>
> 反馈、Bug、建议请加 QQ 群：**1055679275**

## 5.2.1 日程日记连续性

- 每篇小时日记会读取上一小时日记并强制承接，不能出现“刚进门”下一小时“还没回来”这类矛盾；
- 面板“刷新日程”改为“重建日程”，会真正重建主干并清空当天日记缓存。

## 5.2.0 社区 PR 合并 + 天气提醒

- 合并 #10-#18：城市/语种随人格、livingmemory、私聊连发合并、天气提醒、Prompt 约束、主动消息去重等；
- 修复 `_dynamic_context` 的 NameError；
- 天气提醒按角色当前状态和最近聊天生成，禁止客服腔/天气播报腔。

## 5.1.1 位置随人格

- 日程城市/住址/公司/车辆默认留空，优先从人格提示词和世界观解析；都没有时自动随机生成并缓存。
- 天气城市留空时跟随日程城市。
- 修复日程一级标题被长文案挤成竖排的问题。

## 5.1.0 日程重构：主干生成 + 动态展开

- 不再预生成三级 10 分钟细节；每天只生成一次 24 小时主干。
- 面板只保留一级（深夜/上午/中午/晚上）和二级（每小时）卡片；点开某一小时，后端实时生成第一人称小日记。
- 晚上时段 18:00-24:00 闭环，最后一条 23:00-24:00。
- 情绪逐小时平滑，空间强制“先在路上再到达”，周末开车绑定“黑色奔驰 C 级”，带堵车/停车位细节。
- 休息日天气好时从 scenic_spots.json 选贵阳/贵州景区；工作日可能被临时外派到随机省份，休息日可能被老板叫去加班或朋友叫去聚餐。

## 5.0.2 升级公告（重要）

4.0.0 起插件标识就是 **`Astrbot_Amo_forever`**，5.0.2 继续保持这个标识，不再改回 `amo_forever`。

这样安装 5.0.2 会覆盖 4.0.x，而不是变成另一个插件。

同时，3.x 的旧标识 `amo_forever` 数据会自动迁移到新标识：

- 旧数据：`data/plugin_data/amo_forever/amo_forever.db`
- 新数据：`data/plugin_data/Astrbot_Amo_forever/amo_forever.db`
- 旧配置：`data/config/amo_forever_config.json`
- 新配置：`data/config/Astrbot_Amo_forever_config.json`

**插件目录必须是：**

```
data/plugins/Astrbot_Amo_forever/
```

不要再用 `amo_forever` 作为插件目录；旧目录只作为迁移来源，迁移完成后可以删除旧代码目录，但不要提前删除旧数据目录。

5.0.2：景区知识库改名为“旅游知识库-风景区”，旧名称自动迁移；重建景区会创建/更新新名称知识库。

<span style="color:red">**重要：如需更换语种，请不要在人格提示词中提及具体语种，否则会和这里的选择冲突。**</span>

记忆来源支持 **天使之魂（astrbot_plugin_angel_memory）** 和 **我会牢牢记住你（astrbot_plugin_memory_companion）**，用户画像页会自动列出并读取。

---

基于 AstrBot 的“我想永远陪伴你”。3.8.8 起**群聊只使用完整心流引擎**，**发送只使用完整本地分段引擎**，不需要再单独安装 `astrbot_plugin_xinliuchenjinban` 和 `astrbot_plugin_custome_segment_reply`。

## 它是怎么工作的

群聊：

```
用户消息
  → 心流引擎（五维评分 + 动态阈值 + 沉浸模式 + 防抖 + 群聊独立配置）
  → 达到条件时设置 event.is_at_or_wake_command = True
  → AstrBot 原生 LLM 生成回复（人格、上下文都走 AstrBot）
  → on_decorating_result 交给完整本地分段引擎
  → 按符号分段、成对符号保护、打字延迟、群聊引用
```

私聊：

```
健康 / 生理期 / 日程门控
  → 通过则走 AstrBot 原生回复
  → 完整本地分段引擎发送（私聊不引用）
```

没有修改 AstrBot 核心代码，也没有替换它的回复链路；心流只负责“要不要说”，分段只负责“怎么说”。

## 功能

- **完整心流（内置）**：五维评分、动态阈值、沉浸模式、判断暂停、防抖、群聊独立阈值、白名单、自定义评分规则、详细日志、心流命令。
- **完整本地分段（内置）**：强制分隔符、字数范围、超长处理、短尾合并、断句符号、标点保留、连续符号顺延、成对符号保护、排除关键词、超长跳过、固定/随机/按字/智能延迟、主动消息处理。
- **生理期**：28 天周期可配置，月经期、卵泡期、排卵期、黄体期；影响心情、体力、疼痛、回复概率与主动求安慰。
- **九维心情**：开心、平静、郁闷、生气、委屈、疲惫、焦虑、兴奋、依恋；直接影响语气。
- **世界观与日程**：基于 AstrBot 人格生成世界观，再由世界观生成每日日程；天气、健康、生理期共同参与。
- **天气**：和风天气；未配置 Key 时本地模拟。
- **长期记忆**：自动记录、事实提取、7/14 天/永久遗忘、关键词检索并注入回复；可切换为读取 `astrbot_plugin_private_companion` 的记忆。
- **用户档案**：自动建立，记录名字、称呼、生日、关系、好感；相恋仅管理员可设。
- **用户画像界面**：状态 / 用户画像 / 设置三个页签；可搜索、编辑画像、查看记忆、同步陪伴插件档案，直接调整关系（仇恨/抵触/普通/熟识/相恋）。
- **全部开关进 WebUI**：设置页加载完整 `_conf_schema.json`，布尔开关、数字、文本、列表/模板列表都可直接改，保存后写入插件配置并重建心流/分段引擎。
- **主动私聊**：概率、频率、每日上限；难受时找相恋的人撒娇，遇到有趣的事分享。
- **九维面板**：查看心情雷达、生理期、健康、天气、日程、阈值。

## 配置

配置项分为三组：

- 基础陪伴：`period_*`、`proactive_*`、`mem_*`、`weather_*` 等；
- 心流完整版：`hf_*`（原始心流配置名前面加 `hf_`）；
- 本地分段完整版：`seg_*`（原始分段配置名前面加 `seg_`）。

### 心流关键配置

| 配置 | 说明 |
|---|---|
| `hf_enable_heartflow` | 启用完整心流，默认开 |
| `hf_judge_provider_name` | 判断用小模型；留空使用当前会话主模型 |
| `hf_reply_threshold` | 心流基础阈值 0.0-1.0 |
| `hf_enable_dynamic_threshold` | 动态阈值，默认开 |
| `hf_dynamic_threshold_min/max` | 动态阈值上下限 |
| `hf_dynamic_activity_window` | 活跃度统计窗口（秒） |
| `hf_enable_debounce` | 防抖，默认开 |
| `hf_debounce_delay` / `hf_max_debounce_wait` | 防抖等待/最大等待 |
| `hf_immersive_mode_duration` | 沉浸模式持续秒数 |
| `hf_judge_rules` | 自定义五维评分规则 |
| `hf_group_threshold_configs` | 群聊独立阈值 |
| `hf_chat_whitelist` | 群聊白名单 |

### 分段关键配置

| 配置 | 说明 |
|---|---|
| `seg_enable` | 启用完整分段引擎，默认开 |
| `seg_force_split_symbols` | 强制分隔符列表 |
| `seg_min_length` / `seg_max_length` | 分段字数范围 |
| `seg_allow_exceed_max` / `seg_hard_max_limit` | 超长处理 |
| `seg_merge_short_tail` / `seg_short_tail_threshold` | 短尾合并 |
| `seg_split_symbols` | 断句符号列表 |
| `seg_keep_symbol` | 保留标点 |
| `seg_extend_to_trailing_symbols` | 连续符号顺延 |
| `seg_protect_paired_symbols` | `《》`、`“”`、`（）` 等内部不切 |
| `seg_exclude_keywords` | 命中则不分段 |
| `seg_delay_type` | `fixed` / `random` / `per_char` / `smart` |
| `seg_random_delay_range` | 随机延迟范围 |
| `seg_fixed_delay_seconds` | 固定延迟 |
| `seg_per_char_delay_seconds` | 按字延迟 |

> 分段是**符号列表**方案，不是正则。需要调断句符就改 `seg_split_symbols`；成对符号保护默认开启。

## 兼容 private companion 记忆

如果你同时装了 `astrbot_plugin_private_companion`（我会永远陪着你），可以把它的记忆作为本插件的记忆源：

| 配置 | 说明 |
|---|---|
| `memory_source` | `auto`（默认，优先陪伴插件，缺失回退本地）/ `companion`（只读陪伴插件，缺失时回退本地）/ `local`（只用本地） |
| `companion_memory_plugin_name` | 陪伴插件名，默认 `astrbot_plugin_private_companion` |
| `companion_memory_limit` | 最多读取几条陪伴记忆 |
| `companion_memory_include_profile` | 读取 `companion_memory.profile`（强记忆、边界、表达习惯、偏好、兴趣） |
| `companion_memory_include_important` | 读取 `worldbook_member_profiles.important_memories` |

读取范围：

- `data["users"][uid]["companion_memory"]["items"]` 的 `text` / `weight`；
- `companion_memory["profile"]` 里的 `strong_memories`、`boundaries`、`speaking_style`、`weak_preferences`、`interests`；
- `data["users"][uid]["important_memories"]`；
- `data["worldbook_member_profiles"][uid]["important_memories"]`。

只读，不修改陪伴插件的数据；读不到时自动回退本地记忆。

> 注意：陪伴插件本身也会回复消息。如果两个插件同时接管聊天，可能出现双回复；建议只保留一个负责回复，另一个作为记忆源。

## 用户画像与设置

- “用户画像”页：列出所有档案，支持搜索、编辑名字/称呼/生日/关系/好感/备注、查看记忆；
- “同步陪伴档案”会从 `astrbot_plugin_private_companion` 的 `users` 读取名字、生日、关系分数，补全本插件画像；
- 自动同步也在消息学习钩子里做，只补空字段，不覆盖你手动设置的关系；
- 关系可选：仇恨、抵触、普通、熟识、相恋（恋人）；相恋只允许管理员设置。

“设置”页会加载完整配置 schema，所有开关和参数都在里面；保存后写入插件配置并重建心流/分段引擎，立即生效。

> 不再内置默认管理员。请在 `admin_uids` 填自己的 QQ，或使用 AstrBot 全局 `admins_id`；留空则聊天指令没有管理员。

## 版本号规则

- 尾号只取偶数：0 / 2 / 4 / 6 / 8；
- 尾号到 8 后不再上十位，而是升 minor、尾号归 0：
  - 2.4.6 → 2.4.8 → 2.5.0 → 2.5.2 → 2.5.4 → 2.5.6 → 2.5.8 → 2.6.0
- 版本号中避开数字 1 和 7。

## 安装

1. **先卸载/停用**单独的心流插件和本地分段插件，避免重复触发：
   - `astrbot_plugin_xinliuchenjinban`
   - `astrbot_plugin_custome_segment_reply`
2. **先备份插件数据**（见下方“数据”），再删除旧插件**代码**目录：
   - `data/plugins/Astrbot_Amo_forever`（旧 4.x 代码）
   - `data/plugins/amo_forever`（旧 3.x 代码）
   - `data/plugins/astrbot_plugin_amo_forever`（如果有）
   
   **不要删除** `data/plugin_data/amo_forever`、`data/plugin_data/Astrbot_Amo_forever` 和两个 config，迁移要用；
3. 把本插件目录以 **`Astrbot_Amo_forever`** 这个名字放进 `data/plugins/`，或在 WebUI 上传 zip；
4. **重启 AstrBot**（只重载插件不够，旧 Web API 路由会残留）；
5. 打开插件配置，确认：
   - `hf_enable_heartflow` 开
   - `hf_judge_provider_name`（可选）
   - `seg_enable` 开
   - 天气 Key（可选）
6. 群聊发几条消息测试；私聊发 `/amo status` 测试。

## 指令

陪伴：

```
/amo help
/amo status
/amo mood
/amo profile [@人]
/amo memories [@人]
/amo period [set YYYY-MM-DD]
/amo health [set 状态]
/amo schedule [regen]
/amo weather [refresh]
/amo worldview [regen]
/amo threshold
/amo segment 一段文字
```

管理员：

```
/amo rel @人 仇恨|抵触|普通|熟识|相恋
/amo set @人 name|alias|birthday|notes|affection 值
/amo memo @人 内容 [0/1/2]
/amo forget 记忆ID
/amo say 内容
/amo clean
```

心流完整版命令：

```
/heartflow
/heartflow_debug
/heartflow_clear
/heartflow_log
/heartflow_reset
/heartflow_help
```

## 数据

- 配置：`data/config/Astrbot_Amo_forever_config.json`
- 数据：`data/plugin_data/Astrbot_Amo_forever/amo_forever.db`
- 3.x 旧配置：`data/config/amo_forever_config.json`
- 3.x 旧数据：`data/plugin_data/amo_forever/amo_forever.db`
- 面板：`views/dashboard/index.html`

记忆源为陪伴插件时，本插件仍保留本地 DB 作为回退；不会写入陪伴插件的数据。

升级前同时备份：

```
data/plugin_data/amo_forever/amo_forever.db
data/plugin_data/Astrbot_Amo_forever/amo_forever.db
data/config/amo_forever_config.json
data/config/Astrbot_Amo_forever_config.json
```

5.0.2 第一次启动会自动迁移 3.x 旧标识数据，并在日志里打印：

```
[amo] 已迁移旧版 amo_forever 数据: ... -> ...
[amo] 已迁移旧版 amo_forever 配置: ...（N 项）
[amo] 升级提示：插件标识保持 Astrbot_Amo_forever；旧 amo_forever 配置/数据已自动迁移。
```

迁移完成后，确认面板画像/记忆都在，再手动删除旧的 `data/plugin_data/amo_forever` 备份目录。

## 说明

- 需要 AstrBot 4.5.7 及以上；推荐 4.29.x。
- 群聊引用在 OneBot v11（NapCat / Lagrange 等）下最稳。
- 建议关闭 AstrBot 自带的“分段回复”和流式输出，避免和本插件分段叠加。
- 2.0.2 修复：插件重载后旧 Web API 指向已关闭数据库导致的 `Cannot operate on a closed database`；2.1.0 继续保留自动重连。
- 2.3.0：群聊只走完整心流；旧的五维门控、旧分段、旧防抖已从运行路径和配置中移除，避免和心流/分段抢判定。
- 2.3.1：加载时清理上一实例残留的 Web API 路由；旧路由不会再指向已关闭数据库的旧实例。安装后仍建议完全重启 AstrBot。
- 2.3.2 / 2.3.3：修复面板桥接返回值解包。AstrBot 的 plugin-page bridge 会把插件返回的 `data` 直接交给 iframe；面板现在接受这种无外壳对象，不再误报“桥接调用失败”。
- 2.4.1：天气缓存带城市/Key/Host 签名；在插件设置里改城市后会立即重取天气，不再继续显示旧城市。
- 2.4.2：原生插件配置页保存后自动重新读取配置文件，天气/管理员/日期等动态配置无需重载即可生效；WebUI 顶部显示“陪伴”。
- 2.4.3：记忆来源不再写死 private companion；用户画像页会列出已安装插件，可自动检测或手动选择记忆来源。
- 2.4.4：支持 `astrbot_plugin_memory_companion`（Memory Companion）。自动读取它的 `memory_companion.db`：用户画像从 `identities`/`memories` 同步，面板“查看记忆”直接显示它的长期记忆；旧默认 `astrbot_plugin_private_companion` 自动迁移为 `auto`。
- 2.4.5：修复 WebUI 在手机上可以左右滑动的问题；移动端表单/设置改成单列，所有卡片和输入限制在视口内。
- 2.4.6：和风天气响应做字典/空响应校验，接口异常时回退模拟天气，不再抛 `NoneType.get`；日志会打印 HTTP 状态和 code。
- 2.4.7：打字/分段延迟改为按回复字数动态计算（`dynamic`），旧 `fixed` 配置自动迁移；字数越多停顿越久，并叠加标点修正。
- 2.4.8：从 AstrBot 当前会话人格读取角色名（`use_persona_name`），写进世界观、日程、主动消息和 `<amo_state>`；人格名是 default 时从人格提示词提取。
- 2.4.9：设置分组改名为“状态 / 记忆 / 私聊”。
- 2.4.10：适配和风天气新 API Host。GeoAPI 从已停服的 `geoapi.qweather.com/v2` 改为 `<API Host>/geo/v2`；新增 `weather_geo_host`，旧公共域名会提示更换。
- 2.4.11：心流以当前人格名/可选别名为标准识别“在叫机器人”；命中后直接触发，不再被小模型误判成叫其他群友。
- 2.4.12：身份彻底以 AstrBot 人格为主；`bot_name` 默认留空，别名默认空，不再内置任何人的称呼。
- 2.5.0：反“自曝人机”。润色和最终发送都会拦截“我是AI/机器人/人机/程序”“人机也有用”等自曝，改成真人被质疑时的反驳/无语；`<amo_state>` 也加入真人身份约束。
- 2.5.2：修复“查看记忆”POST 请求被 404（未找到该路由）；`/memories`、`/profiles`、`/get_profile`、`/schedule` 现在同时接受 GET/POST。
- 2.5.4：今日日程自动补 00:00 到第一条安排之间的“睡觉”，旧缓存也会补齐，不再从 07:30 才开始。
- 2.5.6：打字延迟按每一段字数计算并补足；单段、第二段及后续分段都不会再“无延迟”。心流身份日志降为 DEBUG，只保留判定和延迟日志。
- 2.5.8：群聊最近 10 分钟不同发言人数达到阈值时自动引用原消息；主动私聊会读取最近私聊，看到“早安”会先回应，不再问“你还没起床吗”。
- 2.6.0：设置页二级下拉选项改成中文（语气、记忆来源、分段延迟类型）。
- 2.6.2：打字延迟默认改为 400ms/字（18 字约 8 秒），上限 20 秒；每段时间从上一段发送完成后再计算，不足才补。旧 55ms/4500ms/0.08s 默认值自动迁移。
- 2.6.4：睡眠/上班不再只是概率装死；同一人连续发 3 条或群里连续叫 3 次，会强制回复但心情变差、语气不耐烦，可能凶两句；私聊和群聊都生效。
- 2.6.6：新增关系网（仅管理员可编辑），关系会进入回复提示；被打扰时对亲近的人抱怨、对不熟的人直接怼；日程改为每小时一条，并在整点前 3 分钟细化下一小时。
- 2.6.8：日程三级树（大段/每小时/每 10 分钟）；主动私聊只找好友，按吃饭/休息/摸鱼/下班触发，未回复追问一次并降心情，多次未回复会抑郁；记住“叫我XX”和反复 @ 的称呼；反馈群 1055679275。
- 2.8.0：日程从状态页拆成顶栏“日程”页，改成折叠小列表；一级展开小时、二级展开 10 分钟。
- 2.8.2：重生日程/世界观等慢请求超时从 5 秒放宽到 120 秒；顶栏统一为“状态/日程/用户/关系/设置”。
- 2.8.4：日程改成真人节奏：通勤、到公司、开会、午饭、午休、下午茶、上厕所、摸鱼、下班通勤都有；三级每小时再拆 6 个 10 分钟小段。旧机械日程自动换成新版。
- 2.8.6：早上 7 点的 10 分钟细化成洗脸刷牙/换衣服/早餐/收拾包/出门；晚上 22 点细化成洗澡/吹头发/护肤/刷牙。
- 2.8.8：十维心情（新增暴躁）与更小雷达；群聊提到机器人/人机/AI 强制回怼；未回复 5 分钟追问、30 分钟降心情、多次抑郁；恋人休息时必触发主动私聊；方言库与贵州土家族地区用语替换；日程加入熬夜/工作失误/老板骂/扣工资/同事事件链。
- 2.9.0：Amo 更名为“核心”；身份质疑不再强制回怼，先由心流判定，通过后再结合上下文判断是不是在说自己。
- 面板优先使用 AstrBot 官方 bridge；iframe 内没有 bridge 时由面板直接走 postMessage 协议；顶层页面改用 `/api/v1/plugins/extensions/...` 读取。面板为浅色主题。
- 内置心流逻辑来自 `astrbot_plugin_xinliuchenjinban`，内置分段逻辑来自 `astrbot_plugin_custome_segment_reply`（作者 LinJohn8）；已适配为本插件内部引擎，保留其完整功能。
