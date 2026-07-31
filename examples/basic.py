from pathlib import Path

from pylingual_web_batch import BatchConfig, BatchDecompiler

config = BatchConfig(
    input_dir=Path("./input"),
    output_dir=Path("./output"),
    concurrency=1,
    queue_limit=10,
)
print(BatchDecompiler(config).run())
