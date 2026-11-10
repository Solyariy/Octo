from enum import StrEnum


class Platform(StrEnum):
    # supported
    THREADS = "threads"
    INSTAGRAM = "instagram"

    # scraper only: named by `ScraperStatusError`, not accepted by `/save`
    YOUTUBE = "youtube"

    # todo
    # TELEGRAM = "telegram"
    # TIKTOK = "tiktok"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    IN_PROCESS = "in_process"
    SUCCESS = "success"
    FAILED = "failed"


class Modality(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
