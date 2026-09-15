# 让 Agent 调用科研专家团：分享包

日期：2026-09-14。来源：Software Demo Video 上游 1.3.5 与共享配音入口 MiniMax TTS 上游 2.1.3 的分享适配。历史案例的 CLI 记录明确使用过 1.3.2，早期还有 1.3.1；本包不是当时原包，也不附原始会话、数据或录屏。

这个 Skill 把“看懂界面、真的提交任务、发现问题后继续操作、录制与制作演示”交给具备 Computer Use 的 Agent。科研专家团由你自己的 WorkBuddy 提供；安装此包不会凭空增加专家或开通账号。

## 先试一次专家团任务

把压缩包解压，将 `software-demo-video` 和 `minimax-tts` 两个文件夹放在同一个父目录，保持文件夹名称。让你正在使用、支持 Computer Use 的 Agent 阅读 `software-demo-video/SKILL.md`，即可在当前会话使用。希望长期安装时，将这两个文件夹加入所用 Agent 的技能目录；若已有同名技能，先备份并比较，不要直接覆盖。安装方法由你的 Agent 确认可用目录；本包不运行自动安装程序。

电脑需要已安装并登录 WorkBuddy，账号能看到科研专家团，Agent 已获辅助功能、屏幕访问和相关操作授权。桌面版界面可能变化，交给 Agent 看当前页面定位，不照抄历史坐标。

可以直接给 Agent 这段委托，把材料和输出位置换成自己的：

> 使用 software-demo-video 中的真实操作流程，先只完成科研专家团任务，不录视频。打开我的 WorkBuddy，保留我当前选好的模型，从“专家团”进入“科研专家团”并实际召集。我提供的数据是［选择你的文件］，目标是［用一句话描述想研究什么］。先让团队说明分工、查看数据并提出研究思路和大纲；把不合理的方向反馈给团队调整，再继续分析和撰写。过程中检查每个角色实际做了什么，发现缺漏就把具体问题交回团队处理。最后交付团队完成的稿件、关键过程截图，以及哪些问题已经改好、哪些仍需我判断。截图隐藏账号、私人历史和本机路径。不要停在介绍页就说完成。

这条委托只需要 WorkBuddy 与 Computer Use；**不需要先安装录屏、配音或 Remotion 依赖**。如果软件弹出真正需要本人处理的登录、付费或权限步骤，Agent 应停在相应边界。关键研究决策也可以明确要求先让你选择。

## 再把过程做成视频

> 使用 software-demo-video，完整操作我的 WorkBuddy 科研专家团，使用我提供的数据和研究目标。把召集团队、提交材料、第一轮结果、发现问题、反馈与修订、最后交付这些关键过程录下来。用真实操作画面制作一段有重点放大、鼠标点击提示、中文字幕和配音的讲解视频，剪掉或标明等待，保留有助理解的试错过程。只录目标窗口，不录系统音频或麦克风。配音使用我自己的已授权音色，先验证短句，再制作全片。交付 MP4、匹配的 SRT 字幕和简短说明。

录制与制作环境：macOS 15+、Xcode Command Line Tools、Python 3、Node.js/npm、FFmpeg/ffprobe，以及 Agent 当前可用的 Computer Use 连接。窗口录制仍会共享键盘鼠标焦点，录制时不要同时操作目标桌面。其他系统可以利用配音或剪辑代码，但本包的窗口录制器只适用于 macOS。

让 Agent 先运行无录制预检：

```bash
python3 software-demo-video/scripts/preflight.py --json
```

它只检查本机工具、依赖目录和配音键名是否存在，不安装依赖、不录屏、不合成声音。`end_to_end_verified: false` 是正常的：真实端到端验证必须等你本机实际运行。

用于渲染的依赖随模板锁定版本，尚未打包下载：

```bash
cd software-demo-video/assets/remotion-template
npm ci
```

正式素材装配成 `project` 后也要在生成的项目目录执行 `npm ci`。如果使用其他已准备的依赖目录，设置 `SOFTWARE_DEMO_NODE_MODULES` 指向该目录的 `node_modules`，供预检识别。采集、装配、预览与验收的详细命令见 [主 Skill](software-demo-video/SKILL.md) 和其引用文件。

## 配音如何准备

随包附带完整配音代码，**没有任何人的声音、账号、密钥或私人 profile**。选择以下一条自己有权使用的线路：

- **已有 MiniMax 国际版音色**：将自己的 `MINIMAX_TTS_API_KEY` 与 `MINIMAX_VOICE_ID` 配置在本机受限文件 `~/.config/voice-clone/secrets.env`，或通过环境变量注入；不要放进聊天或分享包。显式设置 `VOICE_CLONE_PROVIDER=minimax`。使用自己的账号额度，不会替你创建新音色。
- **Apple Silicon 本地 OmniVoice**：用自己的已授权参考录音制作 `~/.config/voice-clone/reference.wav`，转写录音内容，并按 [本地配音准备](minimax-tts/LOCAL-VOICE.md) 创建自己的 profile。随后运行下方依赖准备命令。模型和运行环境需要网络下载及磁盘空间。
- **不需要克隆声音**：经你选择，可以显式设置 `VOICE_CLONE_PROVIDER=edge` 使用在线普通音色。它不是本人的声音。没有 API key，但需要网络服务可用。

```bash
python3 minimax-tts/scripts/setup_runtime.py --ensure
```

此命令**会安装依赖并写入本机运行环境**，缺少 FFmpeg 时可能调用 `brew` 或 `apt-get`；`ffmpeg` 和 `ffprobe` 需要能从 PATH 找到。在准备好自己的配置并决定采用的路线后再运行。运行目录是 `~/.local/share/voice-clone`。配音不需要连接作者的任何服务。生产任务必须显式设置上述 provider；若指定路线不能用就报错。代码保留上游的 `auto` 默认回退能力，因此不要省略 provider 设置：只有你同意更换路线和普通音色时才选择 `auto`。

`secrets.env` 的每行必须带 `export`，例如（只在自己电脑上替换占位值）：

```bash
export MINIMAX_TTS_API_KEY="<your-authorized-api-key>"
export MINIMAX_VOICE_ID="<your-authorized-voice-id>"
export VOICE_CLONE_PROVIDER="minimax"
```

不要把真实值写入分享文件或发到聊天。

生成配音时，先从剪辑规格生成 cue，再调用随包入口：

```bash
python3 software-demo-video/scripts/make_tts_spec.py edit-spec.json tts-spec.json
python3 minimax-tts/scripts/tts_cued.py tts-spec.json audio
```

以上文件名是你自己的任务文件，不是随包示例成片。`make_tts_spec.py` 输出的每段文字对应后续测量得到的音频时间，交给装配程序同步。先用一句话验证所选音色和停顿，再合成整篇。

## 包里有与没有什么

包含录屏源码、剪辑/核验脚本、Remotion 模板与锁文件、规格 schema、测试、工作流说明，以及配音依赖源码和准备脚本。不含录音样本、原始数据、用户会话、账号配置、模型权重、node_modules 或成片。本包完成了静态检查和现有程序测试；没有在读者电脑上替你登录、授权、录屏或合成声音，因此不能保证所有机器解压即运行。

选用的第三方组件有各自许可：OmniVoice 源码的 Apache 2.0 不代表整个音频 tokenizer/模型栈无商业限制，详见 [配音 Skill](minimax-tts/SKILL.md) 的许可说明；Remotion 的使用条件也须按自己的使用场景核对。本包不重新授予第三方模型和服务的权利。
