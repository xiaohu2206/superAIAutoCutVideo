# `globalPathSearch/runner.py` 操作清单

> 目标：对 Step4.5 的重排序候选（`output/copywriting_to_shots_rerank.json`）做 Step4.8 全局路径搜索，输出全局最优镜头路径（默认 `output/copywriting_to_shots_global_path.json`）。

## I/O 与配置

- 读取 `config.json`（`step4_8_global_path_search` 配置段）
- 解析输入/输出路径（相对路径转项目根目录绝对路径）
- 读取输入 JSON（要求包含非空 `results` 数组）
- 写出输出 JSON（含 `meta`、`results`、`global_paths`）

## 候选准备

- 从每条文案的 `matches` 中构建候选矩阵（按 `final_score/score/rerank_score/embedding_score` 排序并截断 `candidate_top_k`）

## 路径搜索（Beam Search）

- 用第 1 条文案的候选初始化多条路径（每条路径记录 `shots`、累计 `score`、`used_shot_ids`）
- 按文案序列逐步扩展路径
  - 动态 Beam 宽度（early/mid/late 三段式）
  - 默认禁止镜头重复（可配置），若导致无法扩展则退化允许重复以保证搜索继续
  - 逐段累加「基分 + 衔接分」得到路径局部累计分
- 仅保留每一步得分最高的 Top-N 路径（beam）

## 评分规则（局部 + 全局）

- 计算基分：优先 `final_score`，否则 `score/rerank_score/embedding_score`
- 计算衔接分（相邻镜头）
  - 时间轴回退惩罚（当前镜头起点早于上一镜头终点时渐进扣分）
  - 场景标签一致性（从 `summary` 解析室内/室外/昼夜等 tag，一致奖励/不一致惩罚）
- 计算全局调整（整条路径）
  - 时间线 zigzag 拉扯惩罚（“大幅前跳→明显回跳”或“回跳→大幅前跳”的三段模式）
  - 场景切换过密惩罚（tag 切换次数超过阈值）
  - 节奏离群惩罚（镜头时长过长/过短离群数量过多）
- 计算路径总分：\text{pathtotal}=\sum(\text{base}+\text{transition})+\text{globaladjustment}

## 回溯优化（refine）

- 对 Beam 得到的候选路径做逐位置替换尝试（每段在 `refine_candidate_top_k` 范围内尝试更换）
- 若替换后全局总分更高则接受
- 支持镜头去重约束（与搜索阶段一致）

## 日志输出（评分拆解）

- 输出选中路径的逐段候选对比（Top 候选的加分/扣分项摘要）
- 输出整条路径的全局项加分/扣分汇总
- 校验 `refine_global_score` 与分解得到的 `path_total` 一致性（误差阈值告警）

## 结果组装

- 为每条文案写入本次全局路径选中的镜头
  - 给被选镜头标记 `global_path_selected=true`
  - 可配置是否保留原有其它 `matches`（`keep_all_matches`）
  - 写入 `global_path.selected_shot_id/selected_score`
- 输出 `global_paths`（Top 路径的 rank、global_score、shot_ids）

