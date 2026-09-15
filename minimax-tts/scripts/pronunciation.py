"""Global pronunciation dictionary for MiniMax T2A v2.

维护原则：
- 用户明确指定的读法可直接落实，并记录日期与来源；不重复要求 A/B/C 审批。
- 未指定且确有歧义的词先做短样核对；只检查受影响术语，不重配整篇。
- 显示文本与朗读文本分开；型号/分辨率和普通数量不能用同一拆读规则。
"""

import re

# ====================================================================
# 1. pronunciation_dict —— MiniMax API 参数，用于英文术语/混合字母词
#    TTS 遇到"原词"时按"替换拼写"朗读（保留原拼写在字幕/文本里）
#    格式："原词/替换拼写"
# ====================================================================
DEFAULT_PRONUNCIATION_DICT = [
    # ---- 机器学习激活函数 ----
    "ReLU/rayloo",           # /ˈreɪluː/  2026-04-18 A/B/C 选定 B（rayloo 单词化）
    # "tanh/tan h",          # TODO 待 A/B/C 验证
    # "AdamW/adam w",        # TODO 待 A/B/C 验证
    # "LayerNorm/layer norm",# TODO 待 A/B/C 验证
    # "Softmax/soft max",    # TODO 待 A/B/C 验证

    # ---- ML/AI 缩写词 ----
    "CNN/C N N",             # 缩写逐字母读，字母之间保留间隔
    "RNN/R N N",             # 缩写逐字母读，字母之间保留间隔
    "LSTM/L S T M",          # 缩写逐字母读，字母之间保留间隔
    "SVM/S V M",             # 缩写逐字母读，字母之间保留间隔

    # ---- 框架/库名 ----
    # "PyTorch/pie torch",    # TODO 待验证
    # "TensorFlow/tensor flow", # TODO 待验证
    # "HuggingFace/hugging face", # TODO 待验证
]


# ====================================================================
# 2. TEXT_REPLACEMENTS —— 脚本预处理（TTS 调用前）的字符串替换
#    适合数字、符号、公式——改成自然中文读法
# ====================================================================
TEXT_REPLACEMENTS = {
    # ---- 科学记数法（MiniMax 可能漏读负号或念字母 e） ----
    "1e-3": "零点零零一",
    "1e-4": "零点零零零一",
    "1e-5": "十的负五次方",
    "1e-6": "十的负六次方",
    "2e-3": "零点零零二",
    "5e-4": "零点零零零五",

    # ---- 代码片段（TTS 对 dot notation 处理不稳） ----
    # "loss.backward()": "loss 点 backward",  # 待决定是否默认替换
}


def apply_text_replacements(text: str) -> str:
    """按 TEXT_REPLACEMENTS 做串行替换。"""
    for orig, repl in TEXT_REPLACEMENTS.items():
        text = text.replace(orig, repl)
    # 2026-09-07: 用户明确指定 1080p 读作“幺零八零 P”。
    # 仅匹配独立分辨率标记，不拆读金额、页数或包含该片段的型号。
    text = re.sub(r"(?<![A-Za-z0-9_])1080[ \t]*[pP](?![A-Za-z0-9_])", "幺零八零 P", text)
    return text


def merge_pronunciation_dict(extra=None) -> list:
    """合并全局字典 + caller 传入的 per-script 字典。

    caller 的字典**追加**（不覆盖）在默认字典后面。
    如果 caller 传的某个原词与默认字典冲突，MiniMax 的行为未文档化，
    当前先追加，以 caller 的意图为后置优先（同一个 tone 数组里多条，MiniMax 具体语义要实测）。
    """
    result = list(DEFAULT_PRONUNCIATION_DICT)
    if extra:
        result.extend(extra)
    return result
