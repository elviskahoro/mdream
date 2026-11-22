//! Strict Python-dict → [`HtmlToMarkdownOptions`] mapping.
//!
//! Every dict level is walked by hand with an explicit allowed-key check, so
//! an unknown key raises `ValueError` instead of being silently ignored —
//! `#[derive(FromPyObject]]` would skip unknown keys. This is the Python-side
//! twin of `assertEngineOptions` in `packages/js/src/option-shape.ts` and the
//! field-for-field mirror of `to_core_opts` in `crates/node/src/lib.rs`.
//!
//! Key casing is snake_case only. Divergence from NAPI (human-approved): the
//! `max_node_bytes` safety cap is exposed (`Option<usize>`, `0` = unlimited).

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyInt, PyList, PyString};

use mdream::get_tag_id;
use mdream::types::{
  CleanConfig, ExtractionConfig, FilterConfig, FrontmatterConfig, HtmlToMarkdownOptions,
  IsolateMainConfig, OutputFormat, PluginConfig, TagOverrideConfig, TailwindConfig,
};

/// Allowed keys per option level, sorted for the error messages.
const TOP_LEVEL_KEYS: &[&str] = &[
  "clean",
  "format",
  "max_node_bytes",
  "origin",
  "plugins",
  "wrap_width",
];
const CLEAN_KEYS: &[&str] = &[
  "empty_images",
  "empty_link_text",
  "empty_links",
  "fragments",
  "redundant_links",
  "self_link_headings",
  "urls",
];
const PLUGINS_KEYS: &[&str] = &[
  "extraction",
  "filter",
  "frontmatter",
  "isolate_main",
  "tag_overrides",
  "tailwind",
];
const FILTER_KEYS: &[&str] = &["exclude", "include", "process_children"];
const FRONTMATTER_KEYS: &[&str] = &["additional_fields", "meta_fields"];
const EXTRACTION_KEYS: &[&str] = &["selectors"];
const TAG_OVERRIDE_KEYS: &[&str] = &[
  "alias",
  "collapses_inner_white_space",
  "enter",
  "exit",
  "is_inline",
  "is_self_closing",
  "spacing",
];

/// Parses the public `options` dict into core options plus output format.
///
/// `None` yields the defaults. Unknown keys at any level, invalid `format`
/// values, and negative numerics raise `ValueError`; wrong value types raise
/// `TypeError`.
pub fn parse_options(
  options: Option<&Bound<'_, PyDict>>,
) -> PyResult<(HtmlToMarkdownOptions, OutputFormat)> {
  let Some(dict) = options else {
    return Ok((HtmlToMarkdownOptions::default(), OutputFormat::default()));
  };
  let mut opts = HtmlToMarkdownOptions::default();
  let mut format = None;
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "origin" => opts.origin = opt_string("origin", &value)?,
      "clean" => opts.clean = parse_clean(&value)?,
      "plugins" => opts.plugins = parse_plugins(&value)?,
      "wrap_width" => opts.wrap_width = opt_usize("wrap_width", &value)?,
      "format" => format = Some(parse_format(&value)?),
      "max_node_bytes" => opts.max_node_bytes = opt_usize("max_node_bytes", &value)?,
      _ => return Err(unknown_key(key, TOP_LEVEL_KEYS)),
    }
  }
  Ok((opts, format.unwrap_or_default()))
}

// ── Level parsers ──

fn parse_clean(value: &Bound<'_, PyAny>) -> PyResult<Option<CleanConfig>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value
    .cast::<PyDict>()
    .map_err(|_| type_error("clean", "a dict"))?;
  let mut clean = CleanConfig::default();
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "urls" => clean.urls = opt_bool("clean.urls", &value)?,
      "fragments" => clean.fragments = opt_bool("clean.fragments", &value)?,
      "empty_links" => clean.empty_links = opt_bool("clean.empty_links", &value)?,
      "redundant_links" => clean.redundant_links = opt_bool("clean.redundant_links", &value)?,
      "self_link_headings" => {
        clean.self_link_headings = opt_bool("clean.self_link_headings", &value)?;
      }
      "empty_images" => clean.empty_images = opt_bool("clean.empty_images", &value)?,
      "empty_link_text" => clean.empty_link_text = opt_bool("clean.empty_link_text", &value)?,
      _ => return Err(unknown_key(key, CLEAN_KEYS)),
    }
  }
  Ok(Some(clean))
}

fn parse_plugins(value: &Bound<'_, PyAny>) -> PyResult<Option<PluginConfig>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value
    .cast::<PyDict>()
    .map_err(|_| type_error("plugins", "a dict"))?;
  let mut plugins = PluginConfig::default();
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "filter" => plugins.filter = parse_filter(&value)?,
      "isolate_main" => {
        if opt_bool("plugins.isolate_main", &value)? {
          plugins.isolate_main = Some(IsolateMainConfig {});
        }
      }
      "frontmatter" => plugins.frontmatter = parse_frontmatter(&value)?,
      "tailwind" => {
        if opt_bool("plugins.tailwind", &value)? {
          plugins.tailwind = Some(TailwindConfig {});
        }
      }
      "extraction" => plugins.extraction = parse_extraction(&value)?,
      "tag_overrides" => plugins.tag_overrides = parse_tag_overrides(&value)?,
      _ => return Err(unknown_key(key, PLUGINS_KEYS)),
    }
  }
  Ok(Some(plugins))
}

fn parse_filter(value: &Bound<'_, PyAny>) -> PyResult<Option<FilterConfig>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value
    .cast::<PyDict>()
    .map_err(|_| type_error("plugins.filter", "a dict"))?;
  let mut filter = FilterConfig::default();
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "include" => filter.include = opt_string_list("plugins.filter.include", &value)?,
      "exclude" => filter.exclude = opt_string_list("plugins.filter.exclude", &value)?,
      "process_children" => {
        filter.process_children = maybe_bool("plugins.filter.process_children", &value)?;
      }
      _ => return Err(unknown_key(key, FILTER_KEYS)),
    }
  }
  Ok(Some(filter))
}

fn parse_frontmatter(value: &Bound<'_, PyAny>) -> PyResult<Option<FrontmatterConfig>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value
    .cast::<PyDict>()
    .map_err(|_| type_error("plugins.frontmatter", "a dict"))?;
  let mut frontmatter = FrontmatterConfig::default();
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "additional_fields" => {
        let fields = value
          .cast::<PyDict>()
          .map_err(|_| type_error("plugins.frontmatter.additional_fields", "a dict of strings"))?;
        let mut fields_out = Vec::with_capacity(fields.len());
        for (name, field) in fields.iter() {
          let name = key_str(&name)?;
          let Some(field_value) = opt_string(
            &format!("plugins.frontmatter.additional_fields.{name}"),
            &field,
          )?
          else {
            return Err(type_error(
              &format!("plugins.frontmatter.additional_fields.{name}"),
              "a non-empty string",
            ));
          };
          fields_out.push((name.to_string(), field_value));
        }
        frontmatter.additional_fields = Some(fields_out);
      }
      "meta_fields" => {
        frontmatter.meta_fields = opt_string_list("plugins.frontmatter.meta_fields", &value)?;
      }
      _ => return Err(unknown_key(key, FRONTMATTER_KEYS)),
    }
  }
  Ok(Some(frontmatter))
}

fn parse_extraction(value: &Bound<'_, PyAny>) -> PyResult<Option<ExtractionConfig>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value
    .cast::<PyDict>()
    .map_err(|_| type_error("plugins.extraction", "a dict"))?;
  let mut extraction = ExtractionConfig::default();
  for (key, value) in dict.iter() {
    let key = key_str(&key)?;
    match key {
      "selectors" => {
        let Some(selectors) = opt_string_list("plugins.extraction.selectors", &value)? else {
          return Err(type_error(
            "plugins.extraction.selectors",
            "a list of selector strings",
          ));
        };
        extraction.selectors = selectors;
      }
      _ => return Err(unknown_key(key, EXTRACTION_KEYS)),
    }
  }
  Ok(Some(extraction))
}

fn parse_tag_overrides(
  value: &Bound<'_, PyAny>,
) -> PyResult<Option<Vec<(String, TagOverrideConfig)>>> {
  if value.is_none() {
    return Ok(None);
  }
  let dict = value.cast::<PyDict>().map_err(|_| {
    type_error(
      "plugins.tag_overrides",
      "a dict of tag names to override dicts",
    )
  })?;
  let mut overrides = Vec::with_capacity(dict.len());
  for (tag_name, value) in dict.iter() {
    let tag_name = key_str(&tag_name)?.to_string();
    let dict = value
      .cast::<PyDict>()
      .map_err(|_| type_error(&format!("plugins.tag_overrides.{tag_name}"), "a dict"))?;
    let mut config = TagOverrideConfig::default();
    let mut has_field = false;
    for (key, value) in dict.iter() {
      let key = key_str(&key)?;
      let field = format!("plugins.tag_overrides.{tag_name}.{key}");
      match key {
        "enter" => config.enter = opt_string(&field, &value)?,
        "exit" => config.exit = opt_string(&field, &value)?,
        "spacing" => config.spacing = opt_spacing(&field, &value)?,
        "is_inline" => config.is_inline = maybe_bool(&field, &value)?,
        "is_self_closing" => config.is_self_closing = maybe_bool(&field, &value)?,
        "collapses_inner_white_space" => {
          config.collapses_inner_white_space = maybe_bool(&field, &value)?;
        }
        "alias" => {
          let Some(alias) = opt_string(&field, &value)? else {
            return Err(type_error(&field, "a built-in tag name"));
          };
          // Resolve the alias eagerly: an unknown name must raise, never
          // silently no-op (design-review note, attempt 3).
          config.alias_tag_id = Some(get_tag_id(&alias).ok_or_else(|| {
            PyValueError::new_err(format!("Unknown tag name '{alias}' in {field}"))
          })?);
        }
        _ => return Err(unknown_key(key, TAG_OVERRIDE_KEYS)),
      }
      has_field = true;
    }
    if has_field {
      overrides.push((tag_name, config));
    }
  }
  Ok(Some(overrides))
}

// ── Value parsers ──

fn key_str<'a, 'py>(key: &'a Bound<'py, PyAny>) -> PyResult<&'a str> {
  let string: &Bound<'py, PyString> = key
    .cast::<PyString>()
    .map_err(|_| PyTypeError::new_err("option keys must be strings"))?;
  string
    .to_str()
    .map_err(|_| PyTypeError::new_err("option keys must be valid UTF-8 strings"))
}

fn unknown_key(key: &str, valid: &[&str]) -> PyErr {
  PyValueError::new_err(format!(
    "Unknown option key '{key}'; valid keys are: {}",
    valid.join(", ")
  ))
}

fn type_error(name: &str, expected: &str) -> PyErr {
  PyTypeError::new_err(format!("'{name}' must be {expected}"))
}

fn opt_string(name: &str, value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
  if value.is_none() {
    return Ok(None);
  }
  let string = value
    .cast::<PyString>()
    .map_err(|_| type_error(name, "a string"))?;
  Ok(Some(
    string
      .to_str()
      .map_err(|_| type_error(name, "a valid UTF-8 string"))?
      .to_string(),
  ))
}

fn opt_bool(name: &str, value: &Bound<'_, PyAny>) -> PyResult<bool> {
  if value.is_none() {
    return Ok(false);
  }
  Ok(
    value
      .cast::<PyBool>()
      .map_err(|_| type_error(name, "a boolean"))?
      .is_true(),
  )
}

/// `None` (absent or explicit `None`) stays `None`; otherwise `Some(bool)`.
fn maybe_bool(name: &str, value: &Bound<'_, PyAny>) -> PyResult<Option<bool>> {
  if value.is_none() {
    return Ok(None);
  }
  Ok(Some(
    value
      .cast::<PyBool>()
      .map_err(|_| type_error(name, "a boolean"))?
      .is_true(),
  ))
}

/// `None` means absent → `0` (`wrap_width`, `max_node_bytes` defaults).
fn opt_usize(name: &str, value: &Bound<'_, PyAny>) -> PyResult<usize> {
  if value.is_none() {
    return Ok(0);
  }
  let long = value
    .cast::<PyInt>()
    .map_err(|_| type_error(name, "an integer"))?;
  let n: i64 = long
    .extract()
    .map_err(|_| PyValueError::new_err(format!("'{name}' is out of range")))?;
  usize::try_from(n)
    .map_err(|_| PyValueError::new_err(format!("'{name}' must be non-negative, got {n}")))
}

fn opt_string_list(name: &str, value: &Bound<'_, PyAny>) -> PyResult<Option<Vec<String>>> {
  if value.is_none() {
    return Ok(None);
  }
  let list = value
    .cast::<PyList>()
    .map_err(|_| type_error(name, "a list of strings"))?;
  let mut out = Vec::with_capacity(list.len());
  for item in list.iter() {
    let Some(string) = opt_string(name, &item)? else {
      return Err(type_error(name, "a list of strings"));
    };
    out.push(string);
  }
  Ok(Some(out))
}

fn opt_spacing(name: &str, value: &Bound<'_, PyAny>) -> PyResult<Option<[u8; 2]>> {
  if value.is_none() {
    return Ok(None);
  }
  let list = value
    .cast::<PyList>()
    .map_err(|_| type_error(name, "a pair of integers [before, after]"))?;
  if list.len() != 2 {
    return Err(PyValueError::new_err(format!(
      "'{name}' must have exactly two entries [before, after]"
    )));
  }
  let mut pair = [0u8; 2];
  for (slot, item) in pair.iter_mut().zip(list.iter()) {
    let long = item
      .cast::<PyInt>()
      .map_err(|_| type_error(name, "a pair of integers [before, after]"))?;
    let n: i64 = long
      .extract()
      .map_err(|_| PyValueError::new_err(format!("'{name}' is out of range")))?;
    *slot = u8::try_from(n)
      .map_err(|_| PyValueError::new_err(format!("'{name}' entries must be 0-255, got {n}")))?;
  }
  Ok(Some(pair))
}

fn parse_format(value: &Bound<'_, PyAny>) -> PyResult<OutputFormat> {
  if value.is_none() {
    return Ok(OutputFormat::default());
  }
  let string = value
    .cast::<PyString>()
    .map_err(|_| type_error("format", "a string"))?;
  match string
    .to_str()
    .map_err(|_| type_error("format", "a valid UTF-8 string"))?
  {
    "markdown" => Ok(OutputFormat::Markdown),
    "text" => Ok(OutputFormat::Text),
    "html" => Ok(OutputFormat::Html),
    other => Err(PyValueError::new_err(format!(
      "Invalid format '{other}'; expected 'markdown', 'text', or 'html'"
    ))),
  }
}
