# 阿里云百炼与 Home Assistant 集成

[![GitHub stars](https://img.shields.io/github/stars/sevenmade/homeassistant-bailian.svg?style=social&label=Stars)](https://github.com/sevenmade/homeassistant-bailian/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/sevenmade/homeassistant-bailian.svg?style=social&label=Fork)](https://github.com/sevenmade/homeassistant-bailian/network/members)
[![GitHub watchers](https://img.shields.io/github/watchers/sevenmade/homeassistant-bailian.svg?style=social&label=Watch)](https://github.com/sevenmade/homeassistant-bailian/watchers)
[![GitHub followers](https://img.shields.io/github/followers/sevenmade.svg?style=social&label=Follow)](https://github.com/sevenmade?tab=followers)

[![GitHub issues](https://img.shields.io/github/issues/sevenmade/homeassistant-bailian.svg)](https://github.com/sevenmade/homeassistant-bailian/issues)
[![GitHub license](https://img.shields.io/github/license/sevenmade/homeassistant-bailian.svg)](https://github.com/sevenmade/homeassistant-bailian/blob/main/LICENSE)
[![GitHub last commit](https://img.shields.io/github/last-commit/sevenmade/homeassistant-bailian.svg)](https://github.com/sevenmade/homeassistant-bailian/commits)
[![GitHub repo size](https://img.shields.io/github/repo-size/sevenmade/homeassistant-bailian.svg)](https://github.com/sevenmade/homeassistant-bailian)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.8%2B-41BDF5.svg)](https://www.home-assistant.io/)

---

## 简介

把 [阿里云百炼](https://docs.bailian.console.aliyun.com/zh/model-studio/) 接到 Home Assistant Assist，用千问大模型做对话控家，并用百炼做语音识别（STT）和语音合成（TTS）。

支持的能力：

1. **对话** — 默认 `qwen3.8-flash`，走 OpenAI 兼容接口。可调用 Home Assistant Assist 工具，控制已暴露给助手的实体。思考模式默认关闭，适合「关灯」这类短指令。
2. **语音识别（STT，可选）** — 默认 `qwen3-asr-flash`。Assist 送来的本地音频用 Base64 同步转写，不需要公网文件 URL。
3. **语音合成（TTS，可选）** — 默认 `qwen3-tts-flash`，默认音色 `Cherry`。

对话始终启用。如果不需要听或说，安装时可关掉 STT / TTS，Assist 也可以混用其他引擎（例如识别用 Whisper、播报用 Piper）。

最低 Home Assistant 版本：**2025.8.0**。

## 安装

### 通过 HACS 安装

1. 确保已安装 [HACS](https://hacs.xyz/)。

2. 点击下面的按钮，在 Home Assistant 中打开本仓库：

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sevenmade&repository=homeassistant-bailian&category=integration)

   或手动添加：HACS → 集成 → 自定义仓库，填入：

   `https://github.com/sevenmade/homeassistant-bailian`

   类别选择 **Integration**。

3. 下载 **Alibaba Cloud Bailian**，然后**重启 Home Assistant**。

4. 打开 **设置 → 设备与服务**，点击右下角 **添加集成**，搜索 `Alibaba Cloud Bailian` 或 `百炼` 并添加。

5. 填写配置（地域为必选，默认预选北京）：

   - **地域**：必须与 API Key 所在地域一致，Key 不能跨地域使用
   - **API Key**：在 [百炼控制台](https://docs.bailian.console.aliyun.com/zh/model-studio/get-api-key) 创建
   - **业务空间 ID**：北京 / 新加坡 / 弗吉尼亚 / 中国香港可选；东京、法兰克福的专属域名必填

6. 下一步选择是否启用语音引擎：

   - 启用语音识别（STT）
   - 启用语音合成（TTS）

   只做文字对话时，两项都可以关掉。之后仍可在集成选项里改。

7. 在 **选择模型** 一步里下拉选择对话 / STT / TTS 模型。也可以手动输入百炼控制台里的模型 ID。已添加的集成：打开该集成 → **配置**，同样可以改模型。

8. 打开 **设置 → 语音助手**，编辑助手：

   - 对话代理选 **Alibaba Cloud Bailian**
   - 如已启用，语音转文字、文字转语音也可选百炼
   - 到 **语音助手 → 公开**，只勾选允许模型控制的实体

9. 完成。

### 手动安装

1. 将 `custom_components/bailian` 复制到 Home Assistant 配置目录的 `custom_components/` 下。
2. 重启 Home Assistant。
3. 按上面第 4 步起添加集成。

## 配置说明

地域、API Key、业务空间 ID 属于账号配置。更换 Key 请走重新认证，不要写进 YAML。

集成 **选项** 里可以改：

- 是否允许控制 Home Assistant（Assist API）
- 对话指令、对话模型、温度、最大 Token、思考模式
- STT 模型与识别上下文（可写入设备名、场景名，提高听写准确率）
- TTS 模型与默认音色
- 是否启用 STT / TTS

### 推荐模型

| 类型 | 默认 | 可选 |
| --- | --- | --- |
| 对话 | `qwen3.8-flash` | `qwen3.7-plus`、`qwen3.8-max`、`qwen-plus`、`qwen-flash`、`qwen-turbo` |
| STT | `qwen3-asr-flash` | `qwen3-asr-flash-2026-02-10`、`qwen3-asr-flash-2025-09-08` |
| TTS | `qwen3-tts-flash` | `qwen3-tts-instruct-flash`、`qwen3-tts-vc-flash`、`qwen-audio-3.0-tts-flash`、`cosyvoice-v3-flash` |

TTS 音色会先列出当前 API Key 下**复刻 / 设计的自建音色**（标注「自建」），再列出系统音色（`Cherry`、`Serena` 等）。也可手动填写音色 ID。选用自建音色时，合成会自动改用该音色绑定的模型（例如 CosyVoice 复刻音色走 `cosyvoice-v3-flash`，千问声音复刻走 `qwen3-tts-vc-flash`）。

文档：

- [百炼产品简介](https://docs.bailian.console.aliyun.com/zh/model-studio/)
- [获取 API Key](https://docs.bailian.console.aliyun.com/zh/model-studio/get-api-key)
- [文本生成 / 对话](https://docs.bailian.console.aliyun.com/zh/model-studio/text-generation-model.md)
- [语音识别](https://docs.bailian.console.aliyun.com/zh/model-studio/asr-model.md)
- [语音合成](https://docs.bailian.console.aliyun.com/zh/model-studio/tts-model.md)
- [声音复刻](https://help.aliyun.com/zh/model-studio/voice-cloning-api-references)

## 只要对话、不要语音

| 需求 | 怎么配 |
| --- | --- |
| 只在网页 / App 里打字控家 | 关掉 STT 和 TTS |
| 能听，播报用现有 Piper | 只开 STT |
| 识别用本地 Whisper，只要百炼朗读 | 只开 TTS |
| 完整中文语音助手 | STT + 对话 + TTS 都开 |

Assist 管道可以混用：对话用百炼，STT / TTS 用其他引擎。

## 说明

- 全程异步 HTTP 调用，不依赖官方同步 `dashscope` SDK
- 不要使用 Token Plan / Coding Plan 的域名和 Key（那是给编程工具用的，不能当 Home Assistant 后端）
- 当前不做百炼智能体工作流、Omni 全双工语音；自建音色只支持选择账号里已复刻 / 已设计的，不在 Home Assistant 里创建

## 许可证

[Apache-2.0](LICENSE)
