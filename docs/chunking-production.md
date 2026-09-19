# Chunking v3 生产说明

## 策略

`RuleChunker` 使用结构优先的递归切分：标题/编号条款 → 段落 → 列表与表格行 →
中英文句子 → 边界感知硬切。主题前缀计入 768 字符硬上限，overlap 也受预算约束。
每个 chunk 写入 `chunker_version`、`chunk_index`、`chunk_length`、来源和页码。

小块合并优先使用配置的 embedding；模型不可用时采用确定性的词法相似度回退，
保证离线构建结果可重复。分块与向量模型是两个独立环节，构建清单会分别记录版本。

## 生产门禁

构建在写入索引前执行以下门禁：

- chunk 长度不超过配置硬上限；
- 小于 100 字符的块不超过 2%；
- 完全重复块不超过 0.5%；
- 标点异常开头不超过 2%；
- 英文/中文异常结尾不超过 8%；
- 100% chunk 具有版本、顺序和长度元数据；
- 加载失败或无文本文件不超过候选文件的 1%。

向量索引使用 staging collection：完成向量生成、批量写入和条数校验后才替换线上集合。
BM25 和 JSON 清单使用临时文件原子替换。主 embedding 不可用时切换到配置的灾备模型，
集合元数据记录实际使用的模型；E5 模型自动使用 `passage:` 和 `query:` 前缀。

## 验证命令

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate_chunking.py --strict
python scripts/verify_indexes.py --strict
```

`verify_indexes.py` 检查 BM25、Chroma 和清单的条数与 chunk ID 全量一致性，并运行固定的
20 条领域检索回归集。当前门槛为 BM25 Recall@5 ≥ 80%，向量 Recall@5 ≥ 65%。
延迟门槛为 BM25 P95 ≤ 500ms、CPU 向量检索 P95 ≤ 2000ms（含编码，不含首次模型加载）。

## 发布和回滚

只有上述三条命令全部通过才应发布。`chunks_cache.json` 中的
`chunker_code_sha256`、`corpus_fingerprint`、真实运行参数、质量报告和加载报告用于审计。
上线前应保留上一版整个 `indexes` 目录；回滚必须整体恢复 BM25、Chroma 和清单，不能只替换
其中一种索引。
