# Alibaba Cloud Bailian for Home Assistant

把 [阿里云百炼](https://docs.bailian.console.aliyun.com/zh/model-studio/) 接到 Home Assistant Assist：对话（可控制已暴露实体）、语音识别（STT）、语音合成（TTS）。

最低 Home Assistant 版本：**2025.8.0**。

## 能力

| 平台 | 默认模型 | 接口 |
| --- | --- | --- |
| 对话 | `qwen3.8-flash` | OpenAI 兼容 `/chat/completions`，Function Calling 走 Assist API |
| STT | `qwen3-asr-flash` | DashScope 同步识别，本地音频 Base64，不依赖公网文件 URL |
| TTS | `qwen3-tts-flash` | DashScope HTTP 合成，默认音色 Cherry |

思考模式默认关闭，适合语音关灯这类短指令。

## 安装

### HACS（推荐）

1. HACS → Integrations → 自定义仓库，添加本仓库，类别选 Integration
2. 下载 **Alibaba Cloud Bailian**
3. 重启 Home Assistant
4. 设置 → 设备与服务 → 添加集成 → 搜索 **Alibaba Cloud Bailian**

### 手动安装

把 `custom_components/bailian` 复制到 Home Assistant 的 `custom_components/` 目录后重启。

## 配置

添加集成时**必须选择地域**，下拉框默认预选 **华北 2（北京）**。

需要准备：

- 与所选地域一致的 [百炼 API Key](https://docs.bailian.console.aliyun.com/zh/model-studio/get-api-key)
- 业务空间 ID：北京 / 新加坡 / 弗吉尼亚 / 中国香港可选；东京、法兰克福的专属域名必填

装好后到 **设置 → 语音助手**，把需要的引擎选成百炼。只做文字对话时，不必选择 STT / TTS。

只允许模型控制你在「暴露给助手」里勾选的实体。

## 只要对话、不要语音

对话代理始终创建。STT 和 TTS 是可选的：

- **添加集成的第二步**可以关掉「语音识别」或「语音合成」
- 之后在集成 **配置 → 选项** 里也能随时开关；关掉后对应实体会卸载，不会再出现在语音助手列表里
- Assist 管道可以混用：例如对话用百炼，TTS 继续用 Piper / 微软

常见组合：

| 需求 | 怎么配 |
| --- | --- |
| 只在网页/App 里打字控家 | 关掉 STT 和 TTS |
| 能听但不能说（用现有 Piper 播报） | 只开 STT，关掉 TTS |
| 只要百炼朗读，识别用本地 Whisper | 只开 TTS，关掉 STT |
| 完整中文语音助手 | STT + 对话 + TTS 都开 |

## 默认与可选项

集成选项里可以改：

- 对话模型、温度、最大 Token、是否开启思考
- STT 模型与识别上下文（可写设备名、场景名）
- TTS 模型与默认音色

地域、API Key、业务空间 ID 属于账号配置，改它们请走「重新配置 / 重新认证」，不要写进 YAML。

## 仓库结构

后续若要提交 Home Assistant 官方库，`custom_components/bailian/client.py` 会拆成独立的 PyPI 异步库。当前为了方便 HACS 安装，客户端先放在集成内部。

## 开发说明

- 全程 `aiohttp` 异步调用，不依赖官方同步 `dashscope` SDK
- 不使用 Token Plan / Coding Plan 域名（那是给编程工具用的）
- 第一期不做智能体工作流、Omni 全双工、声音复刻

## 许可证

Apache-2.0
