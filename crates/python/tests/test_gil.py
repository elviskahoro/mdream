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


def iterations_while_worker_converts(convert):
    """Runs `convert` in a worker thread; counts main-thread loop iterations
    strictly while the conversion is in flight."""
    ready = threading.Event()
    go = threading.Event()
    done = {}

    def worker():
        ready.set()
        go.wait()
        convert(done)

    thread = threading.Thread(target=worker)
    thread.start()
    ready.wait()
    go.set()

    iterations = 0
    deadline = time.perf_counter() + 30  # hard cap, never reached in practice
    while "done" not in done and time.perf_counter() < deadline:
        iterations += 1
    thread.join()
    return iterations


def test_one_shot_conversion_releases_the_gil():
    html, single = one_shot_fixture()

    def convert(done):
        done["md"] = mdream.html_to_markdown(html)
        done["done"] = True

    iterations = iterations_while_worker_converts(convert)
    # A conversion holding the GIL blocks the main thread completely for its
    # whole duration; the floor below is orders of magnitude under the count
    # an unblocked main thread reaches (~millions of iterations).
    assert iterations >= 100_000, (
        f"main thread managed only {iterations} iterations during a "
        f"{single:.2f}s conversion - conversion appears to hold the GIL"
    )


def test_stream_process_chunk_releases_the_gil():
    chunk, single = stream_fixture()

    def convert(done):
        s = mdream.MarkdownStream()
        s.process_chunk(chunk)
        s.finish()
        done["done"] = True

    iterations = iterations_while_worker_converts(convert)
    assert iterations >= 100_000, (
        f"main thread managed only {iterations} iterations during a "
        f"{single:.2f}s stream round - process_chunk appears to hold the GIL"
    )
