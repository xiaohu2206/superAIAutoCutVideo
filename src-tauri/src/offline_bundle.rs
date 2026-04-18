//! 离线更新：网盘下载后，通过「总清单」解析后端 runtime-manifest 与可选 NSIS 壳安装包路径。

use serde::Serialize;
use std::path::PathBuf;

#[derive(Serialize, Clone, Debug)]
#[serde(rename_all = "camelCase")]
pub struct OfflineBundleResolved {
    pub backend_manifest_path: String,
    pub shell_installer_path: Option<String>,
}

const BUNDLE_MANIFEST_FILENAME: &str = "offline-bundle-manifest.json";

/// 仅接受文件名为 `offline-bundle-manifest.json` 的总清单（与 runtime-manifest.json 分离开）。
pub fn resolve_offline_update_bundle(selected_path: String) -> Result<OfflineBundleResolved, String> {
    let path = PathBuf::from(&selected_path);
    if !path.is_file() {
        return Err(format!("文件不存在: {}", selected_path));
    }
    let name_ok = path
        .file_name()
        .and_then(|n| n.to_str())
        .map(|n| n.eq_ignore_ascii_case(BUNDLE_MANIFEST_FILENAME))
        .unwrap_or(false);
    if !name_ok {
        return Err(format!(
            "仅允许选择名为「{}」的文件（请勿直接选择 runtime-manifest.json）",
            BUNDLE_MANIFEST_FILENAME
        ));
    }

    let text =
        std::fs::read_to_string(&path).map_err(|e| format!("读取清单失败: {}", e))?;
    let text = crate::json_util::trim_utf8_bom(&text);
    let v: serde_json::Value =
        serde_json::from_str(text).map_err(|e| format!("JSON 解析失败: {}", e))?;

    if v.get("backend_runtime_manifest")
        .and_then(|x| x.as_str())
        .is_some()
    {
        let schema = v
            .get("schema_version")
            .and_then(|x| x.as_u64())
            .unwrap_or(0);
        if schema != 1 {
            return Err(format!(
                "不支持的 offline_bundle schema_version: {}（需要 1）",
                schema
            ));
        }
        let backend_rel = v
            .get("backend_runtime_manifest")
            .and_then(|x| x.as_str())
            .ok_or_else(|| "backend_runtime_manifest 无效".to_string())?;
        let dir = path
            .parent()
            .ok_or_else(|| "无法解析清单所在目录".to_string())?;
        let backend = dir.join(backend_rel);
        if !backend.is_file() {
            return Err(format!(
                "未找到后端清单（请与 zip 放在同一文件夹）: {}",
                backend.display()
            ));
        }
        let shell_installer_path = match v.get("shell_installer").and_then(|x| x.as_str()) {
            Some(s) if !s.trim().is_empty() => {
                let sp = dir.join(s.trim());
                if !sp.is_file() {
                    return Err(format!("未找到壳安装包: {}", sp.display()));
                }
                Some(sp.to_string_lossy().to_string())
            }
            _ => None,
        };

        return Ok(OfflineBundleResolved {
            backend_manifest_path: backend.to_string_lossy().to_string(),
            shell_installer_path,
        });
    }

    Err(
        "总清单格式无效：需要 schema_version 为 1，且包含 backend_runtime_manifest 字段".into(),
    )
}

/// 启动本机已下载的 Windows 安装包（由用户从网盘放入同一目录）。
pub fn launch_local_shell_installer(installer_path: String) -> Result<(), String> {
    let p = PathBuf::from(&installer_path);
    if !p.is_file() {
        return Err(format!("安装包不存在: {}", installer_path));
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new(&p)
            .spawn()
            .map_err(|e| format!("启动安装程序失败: {}", e))?;
        return Ok(());
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = p;
        Err("当前平台不支持启动该安装包".into())
    }
}
