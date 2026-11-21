//! Rust-side checks for the option mapping and panic guard, plus the ignored
//! generator that (re)writes the committed pytest expectations in
//! `tests/expected.py` by running the core crate directly.

use std::ffi::CString;

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use mdream::types::{HtmlToMarkdownOptions, OutputFormat, PluginConfig};
use mdream::{get_tag_id, html_to_format_result};

use super::options::parse_options;
use super::stream::MarkdownStream;
use super::{catch_panic, convert};

// ── Option mapping ──

fn dict_of<'py>(py: Python<'py>, src: &str) -> Bound<'py, PyDict> {
  let code = CString::new(src).expect("valid dict literal");
  py.eval(&code, None, None)
    .expect("valid dict literal")
    .cast_into::<PyDict>()
    .expect("options must be a dict")
}

#[test]
fn none_options_yield_defaults() {
  Python::attach(|_py| {
    let (opts, format) = parse_options(None).expect("default options");
    assert!(opts.origin.is_none());
    assert_eq!(opts.wrap_width, 0);
    assert_eq!(opts.max_node_bytes, 0);
    assert!(opts.clean.is_none());
    assert!(opts.plugins.is_none());
    assert_eq!(format, OutputFormat::Markdown);
  });
}

#[test]
fn unknown_top_level_key_is_rejected() {
  Python::attach(|py| {
    let err = parse_options(Some(&dict_of(py, r#"{"nope": 1}"#))).unwrap_err();
    assert!(err.is_instance_of::<PyValueError>(py), "{err}");
    let msg = err.to_string();
    assert!(msg.contains("Unknown option key 'nope'"), "{msg}");
    assert!(
      msg.contains("valid keys are: clean, format, max_node_bytes, origin, plugins, wrap_width"),
      "{msg}"
    );
  });
}

#[test]
fn unknown_key_at_every_level_is_rejected() {
  Python::attach(|py| {
    for (src, valid) in [
      (
        r#"{"clean": {"nope": True}}"#,
        "empty_images, empty_link_text, empty_links, fragments, redundant_links, self_link_headings, urls",
      ),
      (
        r#"{"plugins": {"nope": 1}}"#,
        "extraction, filter, frontmatter, isolate_main, tag_overrides, tailwind",
      ),
      (
        r#"{"plugins": {"filter": {"nope": 1}}}"#,
        "exclude, include, process_children",
      ),
      (
        r#"{"plugins": {"frontmatter": {"nope": 1}}}"#,
        "additional_fields, meta_fields",
      ),
      (r#"{"plugins": {"extraction": {"nope": 1}}}"#, "selectors"),
      (
        r#"{"plugins": {"tag_overrides": {"x": {"nope": 1}}}}"#,
        "alias, collapses_inner_white_space, enter, exit, is_inline, is_self_closing, spacing",
      ),
    ] {
      let err = parse_options(Some(&dict_of(py, src))).unwrap_err();
      assert!(err.is_instance_of::<PyValueError>(py), "{src}: {err}");
      let msg = err.to_string();
      assert!(msg.contains("Unknown option key 'nope'"), "{src}: {msg}");
      assert!(msg.contains(valid), "{src}: {msg}");
    }
  });
}

#[test]
fn bad_format_and_negative_numbers_are_value_errors() {
  Python::attach(|py| {
    {
      let src = r#"{"format": "pdf"}"#;
      let err = parse_options(Some(&dict_of(py, src))).unwrap_err();
      assert!(err.is_instance_of::<PyValueError>(py), "{src}: {err}");
      assert!(err.to_string().contains("Invalid format 'pdf'"), "{src}");
    }
    for src in [r#"{"wrap_width": -5}"#, r#"{"max_node_bytes": -1}"#] {
      let err = parse_options(Some(&dict_of(py, src))).unwrap_err();
      assert!(err.is_instance_of::<PyValueError>(py), "{src}: {err}");
      assert!(err.to_string().contains("non-negative"), "{src}");
    }
  });
}

#[test]
fn wrong_value_types_are_type_errors() {
  Python::attach(|py| {
    for src in [
      r#"{"origin": 5}"#,
      r#"{"wrap_width": "80"}"#,
      r#"{"clean": "all"}"#,
      r#"{"plugins": []}"#,
      r#"{"clean": {"urls": "yes"}}"#,
      r#"{"plugins": {"filter": {"include": "h1"}}}"#,
    ] {
      let err = parse_options(Some(&dict_of(py, src))).unwrap_err();
      assert!(err.is_instance_of::<PyTypeError>(py), "{src}: {err}");
    }
    let err = parse_options(Some(&dict_of(py, r#"{1: "origin"}"#))).unwrap_err();
    assert!(err.is_instance_of::<PyTypeError>(py), "{err}");
  });
}

#[test]
fn tag_override_alias_resolves_eagerly() {
  Python::attach(|py| {
    let (opts, _) = parse_options(Some(&dict_of(
      py,
      r#"{"plugins": {"tag_overrides": {"my-em": {"alias": "em"}}}}"#,
    )))
    .expect("options should parse");
    let overrides = opts
      .plugins
      .expect("plugins")
      .tag_overrides
      .expect("overrides");
    let config = overrides
      .iter()
      .find(|(name, _)| name == "my-em")
      .map(|(_, config)| config)
      .expect("override present");
    assert_eq!(config.alias_tag_id, get_tag_id("em"));

    let err = parse_options(Some(&dict_of(
      py,
      r#"{"plugins": {"tag_overrides": {"x": {"alias": "not-a-tag"}}}}"#,
    )))
    .unwrap_err();
    assert!(err.is_instance_of::<PyValueError>(py), "{err}");
    assert!(
      err.to_string().contains("Unknown tag name 'not-a-tag'"),
      "{err}"
    );
  });
}

#[test]
fn full_options_dict_maps_field_for_field() {
  Python::attach(|py| {
    let (opts, format) = parse_options(Some(&dict_of(
      py,
      r#"{
        "origin": "https://example.com",
        "wrap_width": 20,
        "max_node_bytes": 4096,
        "format": "text",
        "clean": {"urls": True, "fragments": True},
        "plugins": {
          "filter": {"exclude": ["nav"], "process_children": True},
          "isolate_main": True,
          "frontmatter": {"additional_fields": {"custom": "kept"}, "meta_fields": ["author"]},
          "tailwind": True,
          "extraction": {"selectors": ["h1", "h2"]},
          "tag_overrides": {"my-em": {"alias": "em", "spacing": [1, 2]}},
        },
      }"#,
    )))
    .expect("options should parse");
    assert_eq!(opts.origin.as_deref(), Some("https://example.com"));
    assert_eq!(opts.wrap_width, 20);
    assert_eq!(opts.max_node_bytes, 4096);
    assert_eq!(format, OutputFormat::Text);
    let clean = opts.clean.expect("clean");
    assert!(clean.urls && clean.fragments);
    assert!(!clean.empty_links);
    let plugins = opts.plugins.expect("plugins");
    let filter = plugins.filter.expect("filter");
    assert_eq!(filter.exclude.as_deref(), Some(&["nav".to_string()][..]));
    assert_eq!(filter.process_children, Some(true));
    assert!(plugins.isolate_main.is_some());
    assert!(plugins.tailwind.is_some());
    let frontmatter = plugins.frontmatter.expect("frontmatter");
    assert_eq!(
      frontmatter.additional_fields.as_deref(),
      Some(&[("custom".to_string(), "kept".to_string())][..])
    );
    assert_eq!(
      frontmatter.meta_fields.as_deref(),
      Some(&["author".to_string()][..])
    );
    let extraction = plugins.extraction.expect("extraction");
    assert_eq!(extraction.selectors, ["h1".to_string(), "h2".to_string()]);
    let overrides = plugins.tag_overrides.expect("tag_overrides");
    let config = overrides
      .iter()
      .find(|(name, _)| name == "my-em")
      .map(|(_, config)| config)
      .expect("override present");
    assert_eq!(config.spacing, Some([1, 2]));
    assert_eq!(config.alias_tag_id, get_tag_id("em"));
  });
}

// ── Panic guard ──

#[test]
fn panics_become_runtime_errors() {
  let prev = std::panic::take_hook();
  std::panic::set_hook(Box::new(|_| {}));
  let err = catch_panic::<_, ()>(|| panic!("boom brace")).unwrap_err();
  std::panic::set_hook(prev);
  Python::attach(|py| {
    assert!(
      err.is_instance_of::<pyo3::exceptions::PyRuntimeError>(py),
      "{err}"
    );
  });
}

// ── Smoke: one-shot and streaming through the binding layer ──

#[test]
fn one_shot_convert_and_stream_join() {
  Python::attach(|py| {
    let html = String::from("<h1>Hi</h1><p>Some <strong>bold</strong> text.</p>");
    let result = convert(py, html.clone(), None).expect("convert");
    assert_eq!(result.markdown, "# Hi\n\nSome **bold** text.");
    assert!(!result.truncated);

    let mut stream = MarkdownStream::new(None).expect("stream");
    let split = 8;
    let mut streamed = stream
      .process_chunk(py, html[..split].to_string())
      .expect("chunk");
    streamed.push_str(
      &stream
        .process_chunk(py, html[split..].to_string())
        .expect("chunk"),
    );
    streamed.push_str(&stream.finish(py).expect("finish"));
    assert_eq!(streamed, result.markdown);
  });
}

// ── Expected-output generator for the pytest suite ──

/// mdream core commit the committed expectations were first generated from
/// (the worktree HEAD this crate's parity suite pins).
const CORE_COMMIT: &str = "59245077";

enum CaseOpts {
  Default,
  Origin(&'static str),
  Frontmatter,
}

struct Case {
  name: &'static str,
  html: &'static str,
  opts: CaseOpts,
}

const CASES: &[Case] = &[
  Case {
    name: "headings",
    html: "<h1>Title</h1><h2>Section</h2><h3>Sub</h3><h4>Deep</h4><h5>Deeper</h5><h6>Deepest</h6>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "emphasis",
    html: "<p>Some <strong>bold</strong>, <em>italic</em>, <del>struck</del>, and <code>inline code</code> text.</p>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "links_images",
    html: "<p>See <a href=\"https://example.com/page\">the guide</a> and <a href=\"/relative\">a relative link</a>.</p><p><img src=\"/images/logo.png\" alt=\"Logo\" /></p>",
    opts: CaseOpts::Origin("https://example.com/docs/"),
  },
  Case {
    name: "nested_lists",
    html: "<ul><li>alpha</li><li>beta<ol><li>one</li><li>two<ul><li>deep</li></ul></li></ol></li><li>gamma</li></ul>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "table_alignment",
    html: "<table><tr><th align=\"left\">L</th><th align=\"center\">C</th><th align=\"right\">R</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "table_colspan",
    html: "<table><tr><td colspan=\"2\">wide</td></tr><tr><td>a</td><td>b</td></tr></table>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "code_blocks",
    html: "<pre><code class=\"language-rust\">fn main() {\n    println!(\"hi\");\n}</code></pre><p>after</p>",
    opts: CaseOpts::Default,
  },
  Case {
    name: "frontmatter",
    html: "<html><head><title>Page Title</title><meta name=\"description\" content=\"A test page\"></head><body><h1>Body</h1><p>Text.</p></body></html>",
    opts: CaseOpts::Frontmatter,
  },
];

fn core_opts(opts: &CaseOpts) -> HtmlToMarkdownOptions {
  match opts {
    CaseOpts::Default => HtmlToMarkdownOptions::default(),
    CaseOpts::Origin(origin) => HtmlToMarkdownOptions::default().with_origin(*origin),
    CaseOpts::Frontmatter => {
      HtmlToMarkdownOptions::default().with_plugins(PluginConfig::frontmatter())
    }
  }
}

fn py_options_literal(opts: &CaseOpts) -> String {
  match opts {
    CaseOpts::Default => "None".to_string(),
    CaseOpts::Origin(origin) => format!("{{'origin': {}}}", py_str(origin)),
    CaseOpts::Frontmatter => "{'plugins': {'frontmatter': {}}}".to_string(),
  }
}

/// Renders a Rust string as a single-quoted Python literal.
fn py_str(s: &str) -> String {
  let mut out = String::with_capacity(s.len() + 2);
  out.push('\'');
  for c in s.chars() {
    match c {
      '\'' => out.push_str("\\'"),
      '\\' => out.push_str("\\\\"),
      '\n' => out.push_str("\\n"),
      '\r' => out.push_str("\\r"),
      '\t' => out.push_str("\\t"),
      c => out.push(c),
    }
  }
  out.push('\'');
  out
}

/// Regenerates `crates/python/tests/expected.py`. Ignored by default; run
/// alongside core output changes, like the cross-engine parity fixtures:
///
/// ```text
/// cargo test -p mdream-python --lib generate_expected -- --ignored --nocapture
/// ```
#[test]
#[ignore = "regenerates crates/python/tests/expected.py; run explicitly"]
fn generate_expected() {
  let mut out = String::new();
  out.push_str("\"\"\"Committed expected outputs for the pytest parity suite.\n\n");
  out.push_str("Generated once by running the mdream core crate directly (through the\n");
  out.push_str("generator in crates/python/src/tests.rs); regenerate alongside core\n");
  out.push_str("output changes, like the cross-engine parity fixtures.\n\n");
  out.push_str("Provenance:\n");
  out.push_str(&format!("- mdream core commit: {CORE_COMMIT}\n"));
  out.push_str("- generator: crates/python/src/tests.rs `generate_expected` (ignored test)\n\n");
  out.push_str("Regenerate with:\n");
  out.push_str(
    "    cargo test -p mdream-python --lib generate_expected -- --ignored --nocapture\n\n",
  );
  out.push_str("Each case: (name, html, options, expected_markdown, expected_frontmatter).\n");
  out.push_str("\"\"\"\n\n");
  out.push_str("CASES = [\n");
  for case in CASES {
    let opts = core_opts(&case.opts);
    let result = html_to_format_result(case.html, opts, OutputFormat::Markdown);
    let frontmatter = match result.frontmatter {
      Some(entries) => {
        let items: Vec<String> = entries
          .iter()
          .map(|(k, v)| format!("{}: {}", py_str(k), py_str(v)))
          .collect();
        format!("{{{}}}", items.join(", "))
      }
      None => "None".to_string(),
    };
    out.push_str(&format!(
      "    ({}, {}, {}, {}, {}),\n",
      py_str(case.name),
      py_str(case.html),
      py_options_literal(&case.opts),
      py_str(&result.markdown),
      frontmatter
    ));
  }
  out.push_str("]\n");

  let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/expected.py");
  std::fs::write(&path, out).expect("write tests/expected.py");
  println!("wrote {}", path.display());
}
