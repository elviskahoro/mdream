# The GIL must be released for the whole conversion: while a worker thread
# converts a large document, the main thread must keep making progress.

import threading
import time

import mdream


# Fixtures grow adaptively (doubling the repeated word count, capped at ~8x
# the base size) until one conversion exceeds TIMING_FLOOR, so the test does
# not depend on machine speed: on fast hardware the base document converts
# in under 0.05s, which used to trip a fixed-size precondition ~1-in-3 runs
# even though the GIL was genuinely released.
WORD = "lorem ipsum dolor sit amet "
TIMING_FLOOR = 0.2  # seconds; a single conversion must run for well over this
ONE_SHOT_BASE_REPEATS = 1_000_000
STREAM_BASE_REPEATS = 500_000


def _grow_until_slow(base_repeats, run_once):
    """Returns (document, single-run duration); doubles the word count,
    capped at ~8x the base, until one run exceeds TIMING_FLOOR."""
    max_repeats = base_repeats * 8
    repeats = base_repeats
    while True:
        document = "<p>" + (WORD * repeats) + "</p>"
        duration = run_once(document)
        if duration > TIMING_FLOOR or repeats >= max_repeats:
            return document, duration
        repeats *= 2


def _one_shot(document):
    start = time.perf_counter()
    mdream.html_to_markdown(document)
    return time.perf_counter() - start


def _stream_round(document):
    start = time.perf_counter()
    s = mdream.MarkdownStream()
    s.process_chunk(document)
    s.finish()
    return time.perf_counter() - start


_one_shot_fixture = None
_stream_fixture = None


def one_shot_fixture():
    """(html, single-run duration) for a document slow enough to time."""
    global _one_shot_fixture
    if _one_shot_fixture is None:
        _one_shot_fixture = _grow_until_slow(ONE_SHOT_BASE_REPEATS, _one_shot)
    return _one_shot_fixture


def stream_fixture():
    """(chunk, single-round duration) for a stream round slow enough to time."""
    global _stream_fixture
    if _stream_fixture is None:
        _stream_fixture = _grow_until_slow(STREAM_BASE_REPEATS, _stream_round)
    return _stream_fixture


BUCKET = 0.01  # seconds per bucket of main-thread progress
EDGE_MARGIN = 0.02  # drop the first/last 20ms, where GIL hand-off is legitimate


def iterations_while_worker_converts(convert):
    """Runs `convert` in a worker thread and returns main-thread loop
    iterations that happened strictly inside the conversion interval.

    `convert(done)` must call `done["start"]()` immediately before the
    conversion and `done["stop"]()` immediately after it. The main thread
    timestamps every iteration into 10ms buckets, and only buckets fully
    inside (start + margin, stop - margin) count. That excludes scheduling
    delay before the conversion starts and slack after it returns, so a
    conversion that holds the GIL yields ~0 interior iterations."""
    state = {}
    go = threading.Event()

    def mark(key):
        def _mark():
            state[key] = time.perf_counter()

        return _mark

    state["start_fn"] = mark("start")
    state["stop_fn"] = mark("stop")

    def worker():
        go.wait()
        convert(state)

    thread = threading.Thread(target=worker)
    thread.start()
    go.set()

    buckets = {}
    deadline = time.perf_counter() + 30  # hard cap, never reached in practice
    while "stop" not in state and time.perf_counter() < deadline:
        now = time.perf_counter()
        start = state.get("start")
        if start is not None:
            index = int((now - start) / BUCKET)
            buckets[index] = buckets.get(index, 0) + 1
    thread.join()

    start, stop = state["start"], state["stop"]
    lo = EDGE_MARGIN
    hi = (stop - start) - EDGE_MARGIN
    interior = sum(
        count
        for index, count in buckets.items()
        if index * BUCKET >= lo and (index + 1) * BUCKET <= hi
    )
    return interior


def test_one_shot_conversion_releases_the_gil():
    html, single = one_shot_fixture()

    def convert(state):
        state["start_fn"]()
        mdream.html_to_markdown(html)
        state["stop_fn"]()

    iterations = iterations_while_worker_converts(convert)
    # A conversion holding the GIL blocks the main thread completely for its
    # whole duration; the floor below is orders of magnitude under the count
    # an unblocked main thread reaches (~millions of iterations).
    assert iterations >= 10_000, (
        f"main thread managed only {iterations} interior iterations during a "
        f"{single:.2f}s conversion - conversion appears to hold the GIL"
    )


def test_stream_process_chunk_releases_the_gil():
    chunk, single = stream_fixture()

    def convert(state):
        s = mdream.MarkdownStream()
        state["start_fn"]()
        s.process_chunk(chunk)
        s.finish()
        state["stop_fn"]()

    iterations = iterations_while_worker_converts(convert)
    assert iterations >= 10_000, (
        f"main thread managed only {iterations} interior iterations during a "
        f"{single:.2f}s stream round - process_chunk appears to hold the GIL"
    )
