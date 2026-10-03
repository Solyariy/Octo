from tenacity import RetryCallState

from src.utils.logs import Logger


def tenacity_log_before(retry_state: RetryCallState):
    Logger.info(
            "Sending request",
            args=retry_state.args,
            kwargs=retry_state.kwargs,
            attempt=retry_state.attempt_number,
            increase_depth=1
    )


def tenacity_log_before_sleep(retry_state: RetryCallState):
    Logger.warning(
            "Failed retry",
            args=retry_state.args,
            kwargs=retry_state.kwargs,
            attempt=retry_state.attempt_number,
            error=retry_state.outcome.exception()
    )


def tenacity_log_after(retry_state: RetryCallState):
    if retry_state.outcome.failed:
        Logger.error(
                "Failed to scrap",
                args=retry_state.args,
                kwargs=retry_state.kwargs,
                attempt=retry_state.attempt_number,
                error=retry_state.outcome.exception()
        )
    else:
        Logger.info(
                "Successfully scraped",
                args=retry_state.args,
                kwargs=retry_state.kwargs,
                attempt=retry_state.attempt_number,
                result=retry_state.outcome.result()
        )
