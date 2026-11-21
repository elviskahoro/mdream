#![deny(clippy::all)]

//! Python bindings for the mdream HTML-to-Markdown engine.
//!
//! Thin PyO3 wrapper exposing the Rust engine to CPython, mirroring the NAPI
//! binding (`crates/node`) option for option. The GIL is released for the
//! whole of every conversion, and Rust panics never cross the FFI boundary.

mod options;
mod stream;

use std::collections::HashMap;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use mdream::types::{
  ExtractedElement as CoreExtractedElement, MdreamResult as CoreMdreamResult, OutputFormat,
};

use options::parse_options;

/// One element matched by the `plugins.extraction` selectors.
#[allow(unsafe_code)]
#[derive(Clone)]
#[pyclass(name = "ExtractedElement", get_all)]
pub struct ExtractedElementPy {
  /// Selector that matched the element.
  pub selector: String,
  /// Lowercase tag name of the matched element.
  pub tag_name: String,
  /// Visible text content of the element.
  pub text_content: String,
  /// Element attributes.
  pub attributes: HashMap<String, String>,
}

/// Rich conversion result: markdown plus plugin-collected data.
#[allow(unsafe_code)]
#[derive(Clone)]
#[pyclass(name = "MdreamResult", get_all)]
pub struct MdreamResultPy {
  /// Converted output in the requested format.
  pub markdown: String,
  /// Elements matched by `plugins.extraction`, when the plugin is on.
  pub extracted: Option<Vec<ExtractedElementPy>>,
  /// Metadata collected by `plugins.frontmatter`, when the plugin is on.
  pub frontmatter: Option<HashMap<String, String>>,
  /// Whether `max_node_bytes` fired. `False` guarantees the output matches an
  /// uncapped conversion.
  pub truncated: bool,
}

pub(crate) fn extracted_to_py(
  extracted: Option<Vec<CoreExtractedElement>>,
) -> Option<Vec<ExtractedElementPy>> {
  extracted.map(|elems| {
    elems
      .into_iter()
      .map(|e| ExtractedElementPy {
        selector: e.selector,
        tag_name: e.tag_name,
        text_content: e.text_content,
        attributes: e.attributes.into_iter().collect(),
      })
      .collect()
  })
}

fn result_to_py(result: CoreMdreamResult) -> MdreamResultPy {
  MdreamResultPy {
    markdown: result.markdown,
    extracted: extracted_to_py(result.extracted),
    frontmatter: result.frontmatter.map(|v| v.into_iter().collect()),
    truncated: result.truncated,
  }
}

/// Runs `f`, turning a Rust panic into `RuntimeError("mdream internal error:
/// ...")` so it never crosses the FFI boundary. Mirrors `catch_panic` in
/// `crates/node/src/lib.rs`.
fn catch_panic<F, T>(f: F) -> PyResult<T>
where
  F: FnOnce() -> T,
{
  match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
    Ok(value) => Ok(value),
    Err(payload) => Err(PyRuntimeError::new_err(panic_message(&payload))),
  }
}

fn panic_message(payload: &Box<dyn std::any::Any + Send>) -> String {
  let detail = if let Some(s) = payload.downcast_ref::<&str>() {
    (*s).to_string()
  } else if let Some(s) = payload.downcast_ref::<String>() {
    s.clone()
  } else {
    "unknown panic".to_string()
  };
  format!("mdream internal error: {detail}")
}

/// Convert HTML to Markdown in a single pass.
///
/// The GIL is released for the whole conversion.
#[allow(unsafe_code)]
#[pyfunction]
#[pyo3(signature = (html, options=None))]
pub fn html_to_markdown<'py>(
  py: Python<'py>,
  html: String,
  options: Option<&Bound<'py, PyDict>>,
) -> PyResult<String> {
  let (opts, format) = parse_options(options)?;
  let result = catch_panic(|| py.detach(|| mdream::html_to_format_result(&html, opts, format)))?;
  Ok(result.markdown)
}

/// Convert HTML to readable plain text in a single pass.
///
/// The GIL is released for the whole conversion.
#[allow(unsafe_code)]
#[pyfunction]
#[pyo3(signature = (html, options=None))]
pub fn html_to_text<'py>(
  py: Python<'py>,
  html: String,
  options: Option<&Bound<'py, PyDict>>,
) -> PyResult<String> {
  let (opts, _) = parse_options(options)?;
  let result =
    catch_panic(|| py.detach(|| mdream::html_to_format_result(&html, opts, OutputFormat::Text)))?;
  Ok(result.markdown)
}

/// Convert HTML with a rich result: markdown, extracted elements, frontmatter,
/// and the `truncated` flag. The `format` option selects the output format.
///
/// The GIL is released for the whole conversion.
#[allow(unsafe_code)]
#[pyfunction]
#[pyo3(signature = (html, options=None))]
pub fn convert<'py>(
  py: Python<'py>,
  html: String,
  options: Option<&Bound<'py, PyDict>>,
) -> PyResult<MdreamResultPy> {
  let (opts, format) = parse_options(options)?;
  let result = catch_panic(|| py.detach(|| mdream::html_to_format_result(&html, opts, format)))?;
  Ok(result_to_py(result))
}

/// Python extension module `mdream._mdream`.
#[allow(unsafe_code)]
#[pymodule]
fn _mdream(m: &Bound<'_, PyModule>) -> PyResult<()> {
  m.add_function(wrap_pyfunction!(html_to_markdown, m)?)?;
  m.add_function(wrap_pyfunction!(html_to_text, m)?)?;
  m.add_function(wrap_pyfunction!(convert, m)?)?;
  m.add_class::<stream::MarkdownStream>()?;
  m.add_class::<MdreamResultPy>()?;
  m.add_class::<ExtractedElementPy>()?;
  Ok(())
}

#[cfg(test)]
mod tests;
