# 用自己的参考声音准备本地配音

这是分享适配说明，不含作者的音色配置。需要 Apple Silicon Mac、支持 MPS 的运行环境与自己的已授权录音。选取背景干净、语句完整的一段，先从约 3–10 秒开始试验，内容转写须与声音一致。不得拿无权使用的他人声音进行克隆。

1. 将自己的参考录音转成 WAV，保存为 `~/.config/voice-clone/reference.wav`。不要覆盖已有音色，除非你明确决定更换。
2. 在同目录创建 `profile.json`，内容如下。把转写占位与哈希占位换成自己的内容。样例参数只用于开始测试，不代表适合所有说话者。

```json
{
  "reference_text": "你的录音里实际说的完整文字",
  "reference_sha256": "你的 reference.wav 文件的 SHA256",
  "preprocess_prompt": false,
  "steps": 32,
  "seed": 42,
  "sentence_pause_ms": 450,
  "question_pause_ms": 550,
  "paragraph_pause_ms": 800,
  "local_pronunciation_overrides": {}
}
```

3. 让 Agent 在本机计算该文件 SHA256 填入；声音与文本只留本机。限制目录和文件访问权限，不把它们加入仓库或分享包。
4. 运行 `python3 scripts/setup_runtime.py --ensure`（从此 Skill 目录执行）。安装器只有发现上述两个文件后才会准备本地模型；缺文件会报告 `missing_private_reference`。没有 MPS 的系统不会安装这条本地模型路线。
5. 显式设置 `VOICE_CLONE_PROVIDER=omnivoice`，用短句调用 `scripts/tts_cued.py` 或 `scripts/tts_cli.py`，听过结果后再整批生成。失败请排查实际原因，不要静默替换你的音色。

模型权重和依赖的下载来源与固定版本在 `scripts/setup_runtime.py`、`scripts/requirements-mps.lock`；安装需要网络与足够磁盘。`setup_runtime.py` 不带 `--ensure` 不安装，但会记录本机状态，因此不属于零写入预检。实际配音必须在本机验证，分享包仅提供准备路径。
