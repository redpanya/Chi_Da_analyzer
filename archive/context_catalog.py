"""검증할 로컬 GGUF의 고정 배포본. 임의 경로나 실행 코드는 받지 않는다."""
MODELS = {
    'gemma-4-E4B-it-Q4_K_M': {
        'name': 'gemma-4-E4B-it-Q4_K_M', 'size': 4977171584,
        'sha256': '85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87',
        'url': 'https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/bfc15c382204943c3a8fff0c750b94ae2364d7a3/gemma-4-E4B-it-Q4_K_M.gguf',
    },
    'Qwen3.5-4B-Q4_K_M': {
        'name': 'Qwen3.5-4B-Q4_K_M', 'size': 2740937888,
        'sha256': '00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4',
        'url': 'https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf',
    },
    'Qwen3.5-9B-Q4_K_M': {
        'name': 'Qwen3.5-9B-Q4_K_M', 'size': 5680522464,
        'sha256': '03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8',
        'url': 'https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q4_K_M.gguf',
    },
}
