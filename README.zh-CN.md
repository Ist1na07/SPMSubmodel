# SPM 单点与长键难度

[English](README.md) · [研究与验证报告](docs/research.zh-CN.md)

本项目为 osu!mania 4K、6K、7K 谱面计算两项整谱难度。RC 难度先将所有长键改为头部单点，再在混合谱面中提高单点区域的权重；LN 难度衡量含长键区域的综合难度，并在长键区域只占全谱少量内容时降低结果。同一次调用也返回原始 SPM 难度和未经分段调制的头部单点难度。

实现使用 [SPM Rating](https://github.com/Ist1na07/SPMRating) 提交 `a914a405d8e9a77f94c0518567c37511b0b7ac05` 的 detailed 或 compact 模型。该提交的上游版本为 **1.2.0-rc3** 候选版；本项目评估时尚无 1.2.0 正式标签。上游检出位于 `SPMRating/`。RC/LN 实现调用了上游内部接口，替换该目录后需要重新检查兼容性和评估结果。

## 运行

在本目录使用 Python 3.13：

```bash
git submodule update --init --recursive
python -m pip install -r SPMRating/requirements.txt
python -m unittest discover -s tests -v
```

```python
from rcln import rate_file, rate_content

scores = rate_file("chart.osu", model="detail", rate=1.0, scale="raw")
print(scores["spm"], scores["rc"], scores["ln"], scores["rc_head_only"], scores["ln_coverage"])

with open("chart.osu", encoding="utf-8-sig") as f:
    same = rate_content(f.read(), model="detail", scale="reference")
```

`rate_notes` 也接受上游解析得到的 Notes 对象。`model` 可选 `detail` 或 `compact`。数据集评估和 LN 覆盖率阈值使用 detailed 模型；compact 已通过恒等性测试，但尚未单独用这些数据集校准。可以传入 `cancel` 回调，在小数时间的不同相位之间停止计算。输入至少需要两个有效实体头部，并遵循上游对重复物件和冲突物件的处理规则。

默认 `raw` 尺度与上游 Python 接口的原生输出一致。`reference` 对三个分数应用**同一套上游逐键数标定**：7K 的参考尺度对齐所给 7K 标注，4K 与 6K 分别使用各自的标注尺度。比较时应保持键数、模型、倍率和尺度一致。`ln_coverage` 是平滑后长键在场信号覆盖的聚合物量比例，不是长键头部占比。

`rc_head_only` 是所有长键替换为头部单点后，独立计算的 SPM 分数。`rc` 使用同一条头部单点难度曲线，再调整各段对整谱分数的权重。它可能上升或下降，取决于哪个区域更难。纯单点谱上两者都等于 `spm`；长键几乎覆盖全谱时，调制逐渐减弱，结果趋近头部单点分数。

目前接口计算整谱。小数原始时间使用上游的共享相位处理；不同小数时间很多时可能需要多次计算。分段难度留待后续研究。

## 复现评估

数据集和段位谱面不随仓库分发。复现评估时，请将对应输入放入 `dataset/` 和 `maps/`。结果以 JSON Lines 格式保存在本地 `results/` 并支持续跑；若要完全重算，先移走或删除对应结果文件。输入失败会记录在结果中。

```bash
python evaluation/run.py 7k
python evaluation/run.py 4k
python evaluation/run.py 6k
python evaluation/run.py courses
python evaluation/report.py
python evaluation/calibrate.py
python evaluation/experiment_rc.py
```

要计算 compact 结果，可在每条评分命令后加 `--model compact`；报告脚本目前汇总 detailed 模型。算法定义、指标、样本数量、局限和段位比较见研究报告。上游源代码的 MIT 许可证和声明保留在 `SPMRating/`。
