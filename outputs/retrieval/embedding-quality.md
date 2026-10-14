# Embedding quality on the CS2 retrieval benchmark

Measured with `experiments/retrieval/eval_embeddings.py` on `experiments/retrieval/cs2_retrieval_benchmark.json`:
24 CS2 concepts (maps, utility, economy, roles), each with one English and one Chinese note (48 notes),
48 queries that paraphrase rather than copy the notes (24 English, 24 Chinese), and 6 off-topic queries
with no answer. Both notes of a concept count as relevant to its queries. Every model runs through the
app's own embedding code, so prefixes, normalisation, the hybrid blend and the floor calibration are
exactly what retrieval uses.

## What was tested here, and what was not

Hugging Face is blocked from the build sandbox, so the two models below came from other sources:

- **bge-small-zh-v1.5**: the onnx-community int8 export, from the `dsh-recall-models` npm package, with its
  WordPiece tokenizer from the same project. The app's list uses fastembed's fp32 build of the same model;
  int8 scores can differ slightly.
- **all-MiniLM-L6-v2**: Chroma's ONNX export. It is English-only and **not** in the app's list; it is here as a
  baseline that shows what goes wrong with a monolingual model.

The recommended multilingual models (Multilingual MiniLM, Qwen3-Embedding, multilingual-e5) could not be
downloaded in the sandbox. Run the script on your machine to add them to this report:

```powershell
pip install -e ".[local-embeddings]"
$env:PYTHONPATH='backend'
python experiments/retrieval/eval_embeddings.py --local sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --report outputs/retrieval/embedding-quality.md
python experiments/retrieval/eval_embeddings.py --local Qwen/Qwen3-Embedding-0.6B-Q --report outputs/retrieval/embedding-quality.md
python experiments/retrieval/eval_embeddings.py --app --report outputs/retrieval/embedding-quality.md   # whatever is saved in the app
```

## Findings

1. **Hybrid beats either signal alone.** With the default 65% meaning blend, Recall@1 rose from 0.58
   (keywords only) to 0.65 with bge-small-zh and 0.75 with MiniLM; vector-only was 0.58 and 0.56.
   The 65% default sits at or next to the best blend for both models.
2. **The first floor calibration was wrong, and is fixed.** It used similarity between random pairs of
   notes (95th percentile). Notes in one domain resemble each other far more than a short query
   resembles a note, so the floor landed at 0.72 for bge-small-zh while correct query-to-note matches average
   0.56: it would have discarded 96% of correct vector-only hits. Calibration now embeds 12 off-topic probe
   queries (different from the benchmark's off-topic queries) and takes the 75th percentile of their best match
   in the library. For bge-small-zh that gives 0.52: 67% of correct matches clear it and none of the off-topic
   queries do.
3. **Monolingual models fail on the other language.** MiniLM ranks English queries well (hybrid Recall@1 0.79)
   but cannot read Chinese: Chinese texts all look alike to it, so 67% of Chinese off-topic queries clear the
   floor. bge-small-zh has the opposite lean (vector-only Recall@1 0.42 for English, 0.75 for Chinese). Neither
   finds the other-language note well (other-language note in top 3: 0.04 or less with the blend), which is why
   the app recommends a multilingual model by default.
4. **Speed is not a concern.** Both small models embed a note in 2–5 ms on a 4-core CPU.

## Results

### test/bge-small-zh-v1.5-int8

512 dims · 2.1 ms per note on this CPU · calibrated floor 0.523

| Ranking | Recall@1 | Recall@3 | MRR | Other-language note in top 3 |
|---|---:|---:|---:|---:|
| Keyword only (BM25) | 0.58 | 0.77 | 0.70 | 0.08 |
| Hybrid, 35% meaning | 0.62 | 0.81 | 0.74 | 0.06 |
| Hybrid, 50% meaning | 0.62 | 0.81 | 0.74 | 0.06 |
| Hybrid, 65% meaning | 0.65 | 0.81 | 0.76 | 0.04 |
| Hybrid, 80% meaning | 0.65 | 0.83 | 0.75 | 0.02 |
| Vector only | 0.58 | 0.73 | 0.67 | 0.00 |

| Query language | Keyword R@1 | Hybrid R@1 | Vector R@1 | Off-topic above floor |
|---|---:|---:|---:|---:|
| English | 0.62 | 0.62 | 0.42 | 0% |
| Chinese | 0.54 | 0.67 | 0.75 | 0% |

At the calibrated floor, 67% of queries have their best relevant note above it and 0% of off-topic queries wrongly clear it. Mean cosine: relevant 0.562, best wrong note 0.550, off-topic query's top note 0.442.

Floor by probe percentile: p50: 0.501 (75% relevant / 0% off-topic above) · p75: 0.523 (67% relevant / 0% off-topic above) · p90: 0.539 (60% relevant / 0% off-topic above) · p100: 0.55 (56% relevant / 0% off-topic above). The earlier note-to-note calibration gave 0.719.

### test/all-MiniLM-L6-v2

384 dims · 5.0 ms per note on this CPU · calibrated floor 0.541

| Ranking | Recall@1 | Recall@3 | MRR | Other-language note in top 3 |
|---|---:|---:|---:|---:|
| Keyword only (BM25) | 0.58 | 0.77 | 0.70 | 0.08 |
| Hybrid, 35% meaning | 0.62 | 0.83 | 0.74 | 0.06 |
| Hybrid, 50% meaning | 0.65 | 0.88 | 0.76 | 0.04 |
| Hybrid, 65% meaning | 0.75 | 0.88 | 0.82 | 0.04 |
| Hybrid, 80% meaning | 0.71 | 0.92 | 0.80 | 0.00 |
| Vector only | 0.56 | 0.75 | 0.68 | 0.00 |

| Query language | Keyword R@1 | Hybrid R@1 | Vector R@1 | Off-topic above floor |
|---|---:|---:|---:|---:|
| English | 0.62 | 0.79 | 0.67 | 0% |
| Chinese | 0.54 | 0.71 | 0.46 | 67% |

At the calibrated floor, 50% of queries have their best relevant note above it and 33% of off-topic queries wrongly clear it. Mean cosine: relevant 0.547, best wrong note 0.534, off-topic query's top note 0.369.

Floor by probe percentile: p50: 0.366 (90% relevant / 50% off-topic above) · p75: 0.541 (50% relevant / 33% off-topic above) · p90: 0.591 (38% relevant / 17% off-topic above) · p100: 0.668 (19% relevant / 0% off-topic above). The earlier note-to-note calibration gave 0.65.

