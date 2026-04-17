//! UTF-8 BOM：PowerShell `Set-Content -Encoding UTF8` 等工具常在 JSON 前写入 BOM，serde_json 无法直接解析。

#[inline]
pub fn trim_utf8_bom(s: &str) -> &str {
    s.trim_start_matches('\u{FEFF}').trim()
}
