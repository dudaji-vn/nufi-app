"""KoELECTRA-small NER fine-tuning on corpus4everyone (CMP-315).

corpus4everyone train 117K 데이터로 KoELECTRA-small-v3-modu-ner를
full fine-tuning 하여 KR_LOCATION/KR_PERSON recall을 개선한다.

사용법:
  python3 scripts/train_koelectra_ner.py                       # 기본 학습
  python3 scripts/train_koelectra_ner.py --epochs 5            # 에폭 지정
  python3 scripts/train_koelectra_ner.py --max-train-rows 1000 # 소량 테스트
  python3 scripts/train_koelectra_ner.py --output-dir ./my_model

학습 완료 후 ONNX-INT8 변환:
  M5_NER_MODEL_ID=<output_dir> python3 scripts/export_onnx_int8.py

벤치마크:
  python3 scripts/bench_external_korean.py --backend onnx-int8

런타임 의존: torch, transformers, datasets, seqeval.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL_ID = os.environ.get("M5_NER_MODEL_ID", "Leo97/KoELECTRA-small-v3-modu-ner")
DATASET_ID = "datasciathlete/corpus4everyone-korean-NER"

# corpus4everyone NER 태그 (문자 단위 BIO). 모델의 기존 31-label 체계와 동일.
LABEL_LIST = [
    "O",
    "B-PS", "I-PS", "B-FD", "I-FD", "B-TR", "I-TR",
    "B-AF", "I-AF", "B-OG", "I-OG", "B-LC", "I-LC",
    "B-CV", "I-CV", "B-DT", "I-DT", "B-TI", "I-TI",
    "B-QT", "I-QT", "B-EV", "I-EV", "B-AM", "I-AM",
    "B-PT", "I-PT", "B-MT", "I-MT", "B-TM", "I-TM",
]
LABEL2ID = {l: i for i, l in enumerate(LABEL_LIST)}
ID2LABEL = {i: l for i, l in enumerate(LABEL_LIST)}

# corpus4everyone 원본 태그 인덱스 → LABEL_LIST 재매핑
# 원본: B-PS,(0) I-PS,(1) B-FD,(2) I-FD,(3) ... O(30)
RAW_TAG_NAMES = [
    "B-PS,", "I-PS,", "B-FD,", "I-FD,", "B-TR,", "I-TR,",
    "B-AF,", "I-AF,", "B-OG,", "I-OG,", "B-LC,", "I-LC,",
    "B-CV,", "I-CV,", "B-DT,", "I-DT,", "B-TI,", "I-TI,",
    "B-QT,", "I-QT,", "B-EV,", "I-EV,", "B-AM,", "I-AM,",
    "B-PT,", "I-PT,", "B-MT,", "I-MT,", "B-TM,", "I-TM,",
    "O",
]
# raw tag index → model label id
RAW_TO_LABEL_ID = {}
for idx, raw in enumerate(RAW_TAG_NAMES):
    clean = raw.rstrip(",")
    RAW_TO_LABEL_ID[idx] = LABEL2ID.get(clean, LABEL2ID["O"])


def load_corpus4everyone(split: str, max_rows: int = 0):
    """HuggingFace datasets로 corpus4everyone 로드."""
    from datasets import load_dataset

    ds = load_dataset(DATASET_ID, split=split)
    if max_rows > 0:
        ds = ds.select(range(min(max_rows, len(ds))))
    return ds


def tokenize_and_align(examples, tokenizer, max_length: int = 128):
    """문자 단위 토큰을 서브워드 토큰으로 변환하고 레이블을 정렬한다.

    corpus4everyone은 문자 단위 토큰/태그이므로, 먼저 문자열을 재구성한 뒤
    tokenizer로 서브워드 분할하고, 문자-서브워드 매핑으로 레이블을 전파한다.
    """
    texts = ["".join(toks) for toks in examples["tokens"]]
    all_char_labels = []
    for ner_tags in examples["ner_tags"]:
        char_labels = [RAW_TO_LABEL_ID.get(t, 0) for t in ner_tags]
        all_char_labels.append(char_labels)

    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=max_length,
        padding=False,
        return_offsets_mapping=True,
        is_split_into_words=False,
    )

    labels_batch = []
    for i, offsets in enumerate(tokenized["offset_mapping"]):
        char_labels = all_char_labels[i]
        labels = []
        for start, end in offsets:
            if start == end:
                # special token ([CLS], [SEP], [PAD])
                labels.append(-100)
            else:
                # 서브워드의 첫 문자 위치 레이블 사용
                if start < len(char_labels):
                    labels.append(char_labels[start])
                else:
                    labels.append(0)  # O
        labels_batch.append(labels)

    tokenized["labels"] = labels_batch
    # offset_mapping은 학습에 불필요
    del tokenized["offset_mapping"]
    return tokenized


def compute_metrics(eval_pred):
    """seqeval 기반 NER 메트릭 계산."""
    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=-1)

    true_labels = []
    pred_labels = []

    for pred_seq, label_seq in zip(predictions, labels):
        true_seq = []
        pred_seq_clean = []
        for p, l in zip(pred_seq, label_seq):
            if l == -100:
                continue
            true_seq.append(ID2LABEL.get(l, "O"))
            pred_seq_clean.append(ID2LABEL.get(p, "O"))
        true_labels.append(true_seq)
        pred_labels.append(pred_seq_clean)

    f1 = f1_score(true_labels, pred_labels, average="weighted")
    precision = precision_score(true_labels, pred_labels, average="weighted")
    recall = recall_score(true_labels, pred_labels, average="weighted")

    # PS/LC별 개별 메트릭
    report = classification_report(true_labels, pred_labels, output_dict=True)
    result = {
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }
    for tag in ["PS", "LC"]:
        if tag in report:
            result[f"{tag}_f1"] = round(report[tag]["f1-score"], 4)
            result[f"{tag}_recall"] = round(report[tag]["recall"], 4)
            result[f"{tag}_precision"] = round(report[tag]["precision"], 4)

    return result


def main():
    parser = argparse.ArgumentParser(description="KoELECTRA NER fine-tuning (CMP-315)")
    parser.add_argument("--model-id", default=MODEL_ID, help="베이스 모델 (기본: KoELECTRA-small-v3-modu-ner)")
    parser.add_argument("--output-dir", default=str(ROOT / "models" / "koelectra-ner-finetuned"),
                        help="학습 모델 저장 경로")
    parser.add_argument("--epochs", type=int, default=3, help="학습 에폭 수")
    parser.add_argument("--batch-size", type=int, default=32, help="배치 크기")
    parser.add_argument("--lr", type=float, default=5e-5, help="학습률")
    parser.add_argument("--max-length", type=int, default=128, help="최대 토큰 길이")
    parser.add_argument("--max-train-rows", type=int, default=0, help="학습 데이터 제한 (0=전체)")
    parser.add_argument("--max-val-rows", type=int, default=0, help="검증 데이터 제한 (0=전체)")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="워밍업 비율")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="가중치 감쇠")
    parser.add_argument("--fp16", action="store_true", default=True, help="FP16 혼합 정밀도")
    parser.add_argument("--no-fp16", action="store_true", help="FP16 비활성화")
    args = parser.parse_args()

    use_fp16 = args.fp16 and not args.no_fp16

    import torch
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # 1. 모델 & 토크나이저 로드
    print(f"\n[1/4] 모델 로드: {args.model_id}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    model = AutoModelForTokenClassification.from_pretrained(
        args.model_id,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    print(f"  파라미터: {sum(p.numel() for p in model.parameters()):,}")

    # 2. 데이터셋 로드 & 토크나이징
    print(f"\n[2/4] 데이터셋 로드: {DATASET_ID}")
    train_ds = load_corpus4everyone("train", max_rows=args.max_train_rows)
    val_ds = load_corpus4everyone("validation", max_rows=args.max_val_rows)
    print(f"  train: {len(train_ds)}건, validation: {len(val_ds)}건")

    print("  토크나이징...")
    train_tokenized = train_ds.map(
        lambda ex: tokenize_and_align(ex, tokenizer, args.max_length),
        batched=True,
        remove_columns=train_ds.column_names,
        desc="Tokenize train",
    )
    val_tokenized = val_ds.map(
        lambda ex: tokenize_and_align(ex, tokenizer, args.max_length),
        batched=True,
        remove_columns=val_ds.column_names,
        desc="Tokenize val",
    )

    # 3. 학습
    print(f"\n[3/4] 학습 시작 (epochs={args.epochs}, batch={args.batch_size}, lr={args.lr})")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        fp16=use_fp16 and device == "cuda",
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=100,
        report_to="none",
        dataloader_num_workers=2,
    )

    data_collator = DataCollatorForTokenClassification(tokenizer, padding=True)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_tokenized,
        eval_dataset=val_tokenized,
        data_collator=data_collator,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    start = time.time()
    train_result = trainer.train()
    elapsed = time.time() - start
    print(f"\n학습 완료: {elapsed:.0f}s")
    print(f"  train_loss: {train_result.training_loss:.4f}")

    # 4. 최종 평가 & 저장
    print(f"\n[4/4] 최종 평가 & 모델 저장")
    metrics = trainer.evaluate()
    print(f"  eval metrics: {json.dumps(metrics, indent=2, ensure_ascii=False)}")

    # 최적 모델 저장
    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(str(best_dir))
    print(f"\n모델 저장: {best_dir}")

    # 메트릭 저장
    metrics_file = output_dir / "train_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump({
            "model_id": args.model_id,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "train_rows": len(train_ds),
            "val_rows": len(val_ds),
            "elapsed_seconds": round(elapsed, 1),
            "train_loss": round(train_result.training_loss, 4),
            "eval_metrics": metrics,
        }, f, indent=2, ensure_ascii=False)
    print(f"메트릭 저장: {metrics_file}")

    # 다음 단계 안내
    print(f"\n{'='*60}")
    print("다음 단계:")
    print(f"  1. ONNX-INT8 변환:")
    print(f"     M5_NER_MODEL_ID={best_dir} python3 scripts/export_onnx_int8.py")
    print(f"  2. 벤치마크:")
    print(f"     python3 scripts/bench_external_korean.py --backend onnx-int8")
    print(f"  3. 내부 골드셋 회귀:")
    print(f"     python3 scripts/bench_m5.py --backend onnx-int8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
