# 月隐村 · 六人狼人杀

一名真人和五位独立模型玩家同桌。Python 3.9 或更新版本，仅使用标准库。

## 启动

在项目目录运行 `python3 server.py`，打开 http://127.0.0.1:8765/ 。默认通过本机已登录的 Codex CLI 调用模型，每个座位单独请求。使用前需要本机 `codex` 命令可用并已登录。模型错误会显示在页面，原局面保留，可重新提交。

对局存在内存中，刷新可恢复本标签页对局，重启服务会清空对局。长发言按座位顺序生成，一轮可能需要几分钟。

## 玩家与发言

每局抽取五种不重复的性格模板，本局保持稳定。模板包含性格、表达方式、观察偏好、怀疑倾向、说服方式和盲点，独立于身份。

每位模型只收到自己的身份、查验、狼人队友（仅狼人）、公开事件、本轮已有发言和自己的历史发言。按座次逐位调用，前一位完整发言写入后才生成下一位。发言目标为 300～600 字，回应具体观点，解释公开立场和改观依据。网页支持分段长发言，真人最多输入 1600 字。

## 模型接入

兼容已有环境变量。设置 `WOLF_MODEL` 时，默认走 Chat Completions HTTP 服务。

```bash
export WOLF_BASE_URL='https://你的服务地址/v1'
export WOLF_MODEL='你的模型名称'
read -rsp 'API Key: ' WOLF_API_KEY
export WOLF_API_KEY
python3 server.py
```

也可以复制 `players.example.json` 为自己的配置文件，设置 `WOLF_PLAYERS_FILE` 指向该文件。`default` 是公共默认设置，`seats` 以显示座号 `2` 至 `6` 覆盖各自模型。一个 HTTP 玩家示例为下方对象，密钥只写环境变量名称。

```json
{"provider":"openai","model":"你的模型名称","base_url":"https://你的服务地址/v1","api_key_env":"PLAYER_2_API_KEY"}
```

接口集中在 `players.py`，`request_player(seat_index, messages, max_tokens=...)` 返回包含 `speech` 或 `target` 的 JSON 对象，失败抛出 `PlayerError`。座位内部编号为 0 至 5。同一模型可以承担多个座位，各座位的上下文独立。

## 接口与验证

POST `/api/new` 用空 JSON 创建对局。GET `/api/game` 恢复视图。POST `/api/action` 提交 `revision`、`target` 或 `speech`。后两项请求携带 Authorization Bearer 令牌。旧 revision 返回 409，模型错误返回 502，整轮状态回滚。

运行 `python3 -m unittest -v test_game.py` 检查上下文传递、信息隔离、旧数据性格兼容和失败回滚。

后续微信小程序可复用 JSON 接口，上线需要可访问的 HTTPS 后端。当前服务监听本机地址。
