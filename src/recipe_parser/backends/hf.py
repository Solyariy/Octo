"""transformers backends. Audio and frames are passed as arrays/PIL images, never paths, so
torchcodec (deliberately uninstalled) is never needed."""

import numpy as np
import torch
from PIL import Image
from transformers import (
    AutoModelForImageTextToText,
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
)

from src.recipe_parser.backends.base import (
    FrameReader,
    TextGenerator,
    Transcriber,
    restrict_language,
)
from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.prompts import ASR_LANGUAGES, OCR_PROMPT, PADDLE_OCR_PROMPT, Message
from src.settings import main_settings
from src.utils.models import pick_device

OCR_MAX_NEW_TOKENS = 256


def generation_device() -> tuple[torch.device, torch.dtype]:
    """`pick_device`, but half precision on MPS: float32 would double the memory of 2-4B models."""
    device, dtype = pick_device()
    if device.type == "mps":
        return device, torch.bfloat16
    return device, dtype


def _hf_kwargs(model: ParserModelsEnum) -> dict:
    return dict(
        cache_dir=main_settings.MODELS_PATH,
        token=main_settings.HF_AUTH_TOKEN.get_secret_value(),
        **model.get_spec().load_kwargs,
    )


def _free_torch_cache(device: torch.device) -> None:
    if device.type == "mps":
        torch.mps.empty_cache()
    elif device.type == "cuda":
        torch.cuda.empty_cache()


class HfWhisperTranscriber(Transcriber):
    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        self.device, self.dtype = generation_device()
        self.model = None
        self.processor = None

    def _load(self) -> None:
        kwargs = _hf_kwargs(self.info)
        self.processor = AutoProcessor.from_pretrained(self.repo, **kwargs)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.repo,
            dtype=self.dtype,
            **kwargs,
        ).to(self.device)
        self.model.eval()

    def _unload(self) -> None:
        self.model = None
        self.processor = None

    def _free_device_memory(self) -> None:
        _free_torch_cache(self.device)

    def _detect_language(self, input_features: torch.Tensor) -> str:
        """Whisper's language-token logits, compared only between English and Ukrainian."""
        config = self.model.generation_config
        start = torch.full(
            (1, 1),
            config.decoder_start_token_id,
            device=self.device,
            dtype=torch.long,
        )
        with torch.no_grad():
            logits = self.model(
                input_features=input_features[:, :, :3000],
                decoder_input_ids=start,
                use_cache=False,
            ).logits[0, -1]
        scores = {lang: logits[config.lang_to_id[f"<|{lang}|>"]].item() for lang in ASR_LANGUAGES}
        return restrict_language(max(scores, key=scores.get))

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        self.load()
        if audio.size == 0:
            return ""
        long_form = audio.shape[0] > 30 * sample_rate
        inputs = self.processor(
            audio,
            sampling_rate=sample_rate,
            return_tensors="pt",
            truncation=not long_form,
            padding="longest" if long_form else "max_length",
            return_attention_mask=True,
        )
        input_features = inputs.input_features.to(self.device, dtype=self.dtype)
        if input_features.shape[-1] < 3000:
            input_features = torch.nn.functional.pad(
                input_features,
                (0, 3000 - input_features.shape[-1]),
            )
        language = self._detect_language(input_features)
        with torch.no_grad():
            tokens = self.model.generate(
                input_features=input_features,
                attention_mask=inputs.attention_mask.to(self.device),
                language=language,
                task="transcribe",
                return_timestamps=long_form,
            )
        return self.processor.batch_decode(tokens, skip_special_tokens=True)[0].strip()


class HfChatModel(TextGenerator, FrameReader):
    """Any `AutoModelForImageTextToText` chat model (Qwen3.5, Gemma 4, PaddleOCR-VL).

    Serves both roles: `generate` for text-only recipe JSON, `read_frame` for OCR.
    """

    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        self.device, self.dtype = generation_device()
        self.model = None
        self.processor = None

    @property
    def is_paddle(self) -> bool:
        return "PaddleOCR" in self.repo

    def _load(self) -> None:
        kwargs = _hf_kwargs(self.info)
        self.processor = AutoProcessor.from_pretrained(self.repo, **kwargs)
        if type(self.processor).__module__.startswith("mlx_vlm"):
            # mlx-vlm patches AutoProcessor process-wide once its model modules are imported.
            raise RuntimeError(
                f"{self.info.value}: AutoProcessor returned an mlx-vlm processor; do not mix "
                "mlx-vlm and transformers chat models in one process"
            )
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.repo,
            dtype=self.dtype,
            **kwargs,
        ).to(self.device)
        self.model.eval()

    def _unload(self) -> None:
        self.model = None
        self.processor = None

    def _free_device_memory(self) -> None:
        _free_torch_cache(self.device)

    def _run(self, conversation: list[dict], max_new_tokens: int) -> str:
        inputs = self.processor.apply_chat_template(
            conversation,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            enable_thinking=False,
        ).to(self.device)
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        new_tokens = output[0, inputs["input_ids"].shape[-1] :]
        return self.processor.decode(new_tokens, skip_special_tokens=True).strip()

    def generate(self, messages: list[Message], max_new_tokens: int) -> str:
        self.load()
        conversation = [
            {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
            for m in messages
        ]
        return self._run(conversation, max_new_tokens)

    def read_frame(self, image: Image.Image) -> str:
        self.load()
        prompt = PADDLE_OCR_PROMPT if self.is_paddle else OCR_PROMPT
        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        return self._run(conversation, OCR_MAX_NEW_TOKENS)
