# LaMoGen 验收案例（非通用模板）

仅分析 LaMoGen 或验收此案例时读。以下是核验问题，不是预置答案；题目提到数字不代表数字属实。

优先用户提供的 LanoGen.md、LaMoGen.md 或对应 PDF，读 Method、图 2、实验，再找同版本官方补充。无文件则请求，不生成假报告。版本/正文/补充冲突并列。

以 full 生成独立报告、证据清单，逐项判“证据支持并解释完整”“缺少来源但明确披露”“解释不合格”。未公开不等于失败；跳过可得机制须修正。

## 12 项检查

1. 字符串输入，逐帧数值运动序列输出；说明 T、D 与渲染动作区别。
2. HumanML3D 表示、帧数/帧率、维度及构成；263 要上下文证据，表格小数不算。
3. Labanotation/LabanLite 的 event-wise → frame-wise 与时间展开。
4. 3D → 符号：关节/坐标、动态/静止、Direction/Level、Orientation/Bend/Moving-effort、离散边界/单位、区间聚合，缺失规则逐项未知。
5. Conceptual/Detail Symbols 的内容与作用。
6. 符号、ID、码本向量、multi-hot、Embedding 的区别，多激活组合及形状。
7. Encoder/Decoder、训练参数、重建与速度损失，不把软约束说成物理连续性保证。
8. 数据库字段、CLIP 角色、匹配/排序/Top-K、Top-3 依据和返回示例；区分检索数量、R-precision Top-3、性能排名。
9. Conceptual Description 真实格式与回转符号规则；区分 CD 语义查表索引与身体属性码本索引，不把“无歧义”主张当成全部边界规则已公开。示意 JSON 不当成作者协议。
10. Augmentor 条件、完整 multi-hot 目标、概率、自回归历史、mask、EOS、BCE；核验概率如何二值化，以及正文条件式的 masked 概念历史、完整生成历史、当前概念计划接入是否明确一致，不用惯用自回归实现补空白。
11. Text → RAG → LLM → Conceptual Description → LabanLite → Detail Augmentation → Codebook → Motion Decoder → Motion Features；教学中间值不能称真实日志。
12. 实验/消融、创新和语义控制/自然度权衡；oracle/Human 与普通推理分开。

## 失败模式

只写“CLIP 检索 → LLM 符号 → Decoder 动作”；无证据默认余弦/阈值 0.5/fps/263；JSON 或教学矩阵冒充真数据；multi-hot 当互斥 softmax；ID 当在线 VQ 聚类；oracle 当部署结果；速度损失当无脚滑保证；遇指标冲突静默修正。

合格回答可以是“转换需 A/B/C，已验证 A/B，C 原文未说明，因此真实中间值未知”，但不能绕过转换。
