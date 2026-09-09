"""Small route-report fixture adapted from LaneOrchestrator live reports."""


MODELS = {"gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}


def implementation_summary(task_id, model, reasoning_effort, passed):
    if model not in MODELS:
        raise ValueError("unsupported model")
    if reasoning_effort not in EFFORTS:
        raise ValueError("unsupported reasoning effort")
    selection = {"model": model, "reasoning_effort": reasoning_effort}
    return {"task_id": task_id, "stage": "implementation", "passed": bool(passed), **selection}


def review_summary(task_id, model, reasoning_effort, verdict):
    if model not in MODELS:
        raise ValueError("unsupported model")
    if reasoning_effort not in EFFORTS:
        raise ValueError("unsupported reasoning effort")
    selection = {"model": model, "reasoning_effort": reasoning_effort}
    return {"task_id": task_id, "stage": "review", "verdict": verdict, **selection}
