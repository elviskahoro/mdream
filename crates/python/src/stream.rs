//! Streaming API: the Python spelling of the NAPI `MarkdownStream` class.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::PyDict;

use mdream::MarkdownStreamProcessor;

use crate::options::parse_options;
use crate::{catch_panic, extracted_to_py};

/// Streaming HTML-to-Markdown converter.
///
/// Feed chunks of HTML with `process_chunk`, then call `finish` for the
/// remaining output. Joining the chunk outputs equals the one-shot
/// conversion. The GIL is released around every core call.
#[allow(unsafe_code)]
#[pyclass]
pub struct MarkdownStream {
  inner: MarkdownStreamProcessor,
}

#[allow(unsafe_code)]
#[pymethods]
impl MarkdownStream {
  #[new]
  #[pyo3(signature = (options=None))]
  pub(crate) fn new(options: Option<&Bound<'_, PyDict>>) -> PyResult<Self> {
    let (opts, format) = parse_options(options)?;
    Ok(Self {
      inner: MarkdownStreamProcessor::new_with_format(opts, format),
    })
  }

  /// Process one chunk of HTML, returning the output it completed.
  pub(crate) fn process_chunk(&mut self, py: Python<'_>, chunk: String) -> PyResult<String> {
    catch_panic(|| py.detach(|| self.inner.process_chunk(&chunk)))
  }

  /// Flush remaining output. Plugin data is complete after this returns.
  pub(crate) fn finish(&mut self, py: Python<'_>) -> PyResult<String> {
    catch_panic(|| py.detach(|| self.inner.finish()))
  }

  /// Whether `max_node_bytes` has fired so far. `False` guarantees the output
  /// matches an uncapped conversion.
  #[getter]
  fn truncated(&self) -> bool {
    self.inner.truncated()
  }

  /// Frontmatter and extracted elements collected so far:
  /// `{"extracted": [...], "frontmatter": {...}}`. Complete once `finish()`
  /// has returned. Extracted elements drain on each call.
  fn take_data<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let extracted = extracted_to_py(self.inner.take_extracted());
    let frontmatter: Option<HashMap<String, String>> =
      self.inner.frontmatter().map(|v| v.into_iter().collect());
    let data = PyDict::new(py);
    data.set_item("extracted", extracted)?;
    data.set_item("frontmatter", frontmatter)?;
    Ok(data)
  }
}
