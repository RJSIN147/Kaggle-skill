# Image, text and audio competitions

Template: `deep` (PyTorch, `train.py`, a T4 GPU script kernel by default). Keep GPU runs
short: the 30 h/week quota is shared with the user's other work.

## The AI block

- `MODE` (`"image"` / `"text"`), `EPOCHS`, `BATCH_SIZE`, `LR`, `NUM_WORKERS`.
- `load_tables(data_dir)` → `(train, test)` DataFrames (metadata, image ids, text).
- `assign_folds(train, y)` — the CV scheme (group by patient/author when rows repeat).
- `load_item(row, split)` → an HxWxC `uint8` image (image) or a string (text). The default
  reads 28×28 pixel columns (digit-recognizer); real image comps read files or HDF5 by id
  from `DATA_DIR`.
- `make_transform(split)` → numpy → tensor (augment only on `"train"`).
- `make_model(n_outputs)` → a fresh `nn.Module`. **Internet is off by default**: prefer
  pretrained weights from Kaggle Models attached in `experiment.json` → `sources.models`
  (e.g. `timm/tf-efficientnet/pyTorch/tf-efficientnet-b0/1`), mounted at
  `/kaggle/input/models/<owner>/<model>/<framework>/<variation>/<version>/`.
  Datasets mount at `/kaggle/input/datasets/<owner>/<slug>/`. If the weights are not on
  Kaggle, set `runtime.internet: true` and download them (kx warns and records it). That
  is fine for csv_upload competitions and for a code competition's **training** stage
  (save the weights into the output for the inference stage); a code competition's
  submitted kernel must have internet off (see `code-competition.md`).
- Text: implement `collate(batch)` to tokenize and return `(x, targets)` with `x` a
  tensor; the harness calls `collate(None)` to detect it, so return a non-None value for
  `None`. A hashing bag-of-words model needs no weights (hash with `zlib.crc32`, not the
  per-process salted `hash()`, or an infer kernel maps words differently); a transformer
  needs its weights attached as a model source.

## What the harness guarantees

- Mixed precision (`torch.autocast`: fp16 on GPU, bf16 on CPU) with a `GradScaler`.
- A checkpoint every epoch in `/kaggle/working/checkpoints/fold<k>/`; finished folds keep
  `model.pt` and their OOF/test predictions.
- A **time budget** (85 % of `runtime.limit_s`): the run stops itself before Kaggle would,
  ends COMPLETE, and kx records FAILED(runtime_limit, resumable). `kx run exp-NNN --resume`
  pushes a new version that mounts the previous output (`/kaggle/input/<own-slug>/`) and
  continues from the last checkpoint. A kernel Kaggle hard-stops (CANCEL_ACKNOWLEDGED) is
  not resumable: Kaggle refuses a kernel with no COMPLETE version as a source.
- OOF and test predictions in `kx-preds/1` (probabilities), so runs can be blended.

## Two-stage pipelines

`kx new --idea "…" --hypothesis "…" --after exp-NNN` scaffolds a `deep-infer` stage: it
copies the upstream AI block, inherits its folds and model sources, and at `kx run` it is
pushed **only after** the upstream is COMPLETE and recorded. It reads the upstream's
`checkpoints/fold<k>/model.pt` from `/kaggle/input/notebooks/<owner>/<slug>/`, writes the
submission, and kx records which upstream run it consumed (manifest nonce match). Use this
for code competitions: train with GPU, infer (internet off) for the scoring rerun.

## Joining

Some competitions (e.g. ISIC 2024, nlp-getting-started) refuse a kernel data source until
the user accepts the rules; kx returns `needs_user` with the rules URL.
