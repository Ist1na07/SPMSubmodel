# SPM 单点与长键难度

[English](README.md) · [研究与验证报告](docs/research.zh-CN.md)

同一次调用可得到 osu!mania 4K、6K、7K 谱面的三个整谱分数：原始 SPM、头部单点排列的 RC 难度，以及长键区域的 LN 难度。两个分支沿用 SPM 的难度引擎和逐行聚合，只调整各行对分数的贡献。

子模块固定在 [SPM Rating v1.3.0 修订版 2](https://github.com/Ist1na07/SPMRating/tree/4cbccb5de77e592d201d475041c67aa339ba544a)，分支评分直接调用其原生引擎接口。

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
print(scores["spm"], scores["rc"], scores["ln"], scores["ln_coverage"])

with open("chart.osu", encoding="utf-8-sig") as f:
    same = rate_content(f.read(), model="detail", scale="reference")
```

`rate_notes` 也接受上游解析得到的 Notes 对象。`model` 可选 `detail`、`compact` 或 `detail-4k`。数据集指标使用 `detail`。谱面至少需有两个实体头部，重复和冲突物件遵循上游处理规则。

默认 `raw` 与上游 Python 接口的原生尺度一致。`reference` 对三个分数应用该键数对应的上游分段线性标定。纯单点谱的 RC 等于 SPM，原生 LN 为零；参考尺度下，这个零值也会经过标定。`ln_coverage` 表示附近有长键支撑的参与物量占比。

`rc` 根据局部长键和头部单点难度连续调整行权重。所有谱面使用同一套权重规则。

目前接口计算整谱。小数原始时间使用上游的共享相位处理；不同小数时间很多时可能需要多次计算。分段难度留待后续研究。

## 复现评估

数据集和段位谱面不随仓库分发。复现评估时，请将对应输入放入 `dataset/` 和 `maps/`。结果以 JSON Lines 格式保存在本地 `results/` 并支持续跑；若要完全重算，先移走或删除对应结果文件。输入失败会记录在结果中。

```bash
python evaluation/run.py 7k
python evaluation/run.py 4k
python evaluation/run.py 6k
python evaluation/run.py courses
python evaluation/report.py
```

要计算 compact 结果，可在每条评分命令后加 `--model compact`；报告脚本目前汇总 detailed 模型。算法定义、指标、样本数量、局限和段位比较见研究报告。上游源代码的 MIT 许可证和声明保留在 `SPMRating/`。
