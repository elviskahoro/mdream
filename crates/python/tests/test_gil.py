# The GIL must be released for the whole conversion: while a worker thread
# converts a large document, the main thread must keep making progress.

import threading
import time

import mdream


# Large enough that one conversion runs for well over the counting floor
# (~0.2s single-threaded on current hardware).
HTML = "<p>" + ("lorem ipsum dolor sit amet " * 1_000_000) + "</p>"
CHUNK = "<p>" + ("lorem ipsum dolor sit amet " * 500_000) + "</p>"


def one_shot_duration():
    start = time.perf_counter()
    mdream.html_to_markdown(HTML)
    return time.perf_counter() - start


def stream_round_duration():
    start = time.perf_counter()
    s = mdream.MarkdownStream()
    s.process_chunk(CHUNK)
    s.finish()
    return time.perf_counter() - start


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
    single = one_shot_duration()
    assert single > 0.05, f"test input too small: one conversion took {single:.4f}s"

    def convert(done):
        done["md"] = mdream.html_to_markdown(HTML)
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
    single = stream_round_duration()
    assert single > 0.05, f"test input too small: one stream round took {single:.4f}s"

    def convert(done):
        s = mdream.MarkdownStream()
        s.process_chunk(CHUNK)
        s.finish()
        done["done"] = True

    iterations = iterations_while_worker_converts(convert)
    assert iterations >= 100_000, (
        f"main thread managed only {iterations} iterations during a "
        f"{single:.2f}s stream round - process_chunk appears to hold the GIL"
    )
