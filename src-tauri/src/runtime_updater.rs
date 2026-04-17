use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Manager};

// ── Manifest / State 数据结构 ──────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct RuntimeChunk {
    pub name: String,
    pub version: String,
    pub sha256: String,
    pub size: u64,
    pub url: String,
    #[serde(default)]
    pub description: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct RuntimeManifest {
    pub schema_version: u32,
    pub runtime_version: String,
    #[serde(default)]
    pub variant: String,
    #[serde(default)]
    pub min_app_version: Option<String>,
    #[serde(default)]
    pub created_at: String,
    pub chunks: Vec<RuntimeChunk>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct InstalledChunkInfo {
    pub version: String,
    pub sha256: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct InstalledState {
    pub schema_version: u32,
    pub installed_at: String,
    pub runtime_version: String,
    #[serde(default)]
    pub variant: String,
    pub chunks: HashMap<String, InstalledChunkInfo>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct RuntimeUpdateInfo {
    pub available: bool,
    pub current_version: String,
    pub remote_version: String,
    pub chunks_to_update: Vec<RuntimeChunk>,
    pub total_download_size: u64,
    pub skip_chunks: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct DownloadProgress {
    pub chunk_name: String,
    pub downloaded: u64,
    pub total: u64,
    pub phase: String,
}

// ── 路径工具 ──────────────────────────────────────────────────────

pub fn state_file_path(app_handle: &AppHandle) -> Result<PathBuf, String> {
    let dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法获取应用数据目录: {}", e))?;
    Ok(dir.join("runtime_state.json"))
}

fn manifest_url_from_env() -> Option<String> {
    std::env::var("SACV_RUNTIME_MANIFEST_URL")
        .ok()
        .filter(|s| !s.trim().is_empty())
}

// ── 读写本地状态 ──────────────────────────────────────────────────

pub fn read_installed_state(app_handle: &AppHandle) -> Result<InstalledState, String> {
    let path = state_file_path(app_handle)?;
    if !path.exists() {
        return Ok(InstalledState::default());
    }
    let data = std::fs::read_to_string(&path)
        .map_err(|e| format!("读取 runtime_state.json 失败: {}", e))?;
    serde_json::from_str(&data)
        .map_err(|e| format!("解析 runtime_state.json 失败: {}", e))
}

pub fn write_installed_state(app_handle: &AppHandle, state: &InstalledState) -> Result<(), String> {
    let path = state_file_path(app_handle)?;
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let json = serde_json::to_string_pretty(state)
        .map_err(|e| format!("序列化 runtime_state.json 失败: {}", e))?;
    std::fs::write(&path, json)
        .map_err(|e| format!("写入 runtime_state.json 失败: {}", e))
}

// ── 拉取远端清单 ──────────────────────────────────────────────────

pub fn read_manifest_from_path(path: &Path) -> Result<RuntimeManifest, String> {
    let data = std::fs::read_to_string(path)
        .map_err(|e| format!("读取清单文件失败: {}", e))?;
    serde_json::from_str(&data).map_err(|e| format!("解析清单 JSON 失败: {}", e))
}

/// 根据清单中的 `url` 字段解析本地 zip 文件名（与清单同目录）。
/// 支持 `https://.../runtime-base-1.2.6.zip`、`runtime-base-1.2.6.zip` 等形式。
pub fn local_zip_filename(chunk: &RuntimeChunk) -> String {
    let url = chunk.url.trim();
    if url.starts_with("http://") || url.starts_with("https://") {
        if let Some(seg) = url.rsplit('/').next() {
            if !seg.is_empty() && seg.contains('.') {
                return seg.to_string();
            }
        }
    } else if !url.is_empty() {
        let p = Path::new(url);
        if let Some(name) = p.file_name().and_then(|s| s.to_str()) {
            return name.to_string();
        }
        return url.to_string();
    }
    format!("{}-{}.zip", chunk.name, chunk.version)
}

pub fn local_zip_path_for_chunk(manifest_dir: &Path, chunk: &RuntimeChunk) -> PathBuf {
    manifest_dir.join(local_zip_filename(chunk))
}

pub fn check_local_update(app_handle: &AppHandle, manifest_path: &str) -> Result<RuntimeUpdateInfo, String> {
    let path = PathBuf::from(manifest_path);
    if !path.is_file() {
        return Err(format!("清单文件不存在: {}", path.display()));
    }
    let local = read_installed_state(app_handle)?;
    let remote = read_manifest_from_path(&path)?;
    Ok(compute_update_plan(&local, &remote))
}

pub fn apply_local_update(app_handle: &AppHandle, manifest_path: &str) -> Result<RuntimeUpdateInfo, String> {
    let path = PathBuf::from(manifest_path);
    if !path.is_file() {
        return Err(format!("清单文件不存在: {}", path.display()));
    }
    let manifest_dir = path
        .parent()
        .ok_or_else(|| "无法解析清单所在目录".to_string())?;

    let local = read_installed_state(app_handle)?;
    let remote = read_manifest_from_path(&path)?;
    let plan = compute_update_plan(&local, &remote);

    if !plan.available {
        return Ok(plan);
    }

    let app_data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法获取应用数据目录: {}", e))?;
    let backend_dir = app_data_dir.join("superAutoCutVideoBackend");
    let _ = std::fs::create_dir_all(&backend_dir);

    let mut new_state = local.clone();
    new_state.schema_version = 1;
    new_state.runtime_version = remote.runtime_version.clone();
    new_state.variant = remote.variant.clone();

    for chunk in &plan.chunks_to_update {
        let zip_path = local_zip_path_for_chunk(manifest_dir, chunk);
        if !zip_path.is_file() {
            return Err(format!(
                "缺少分块文件「{}」，请与 runtime-manifest.json 放在同一文件夹。\n期望路径：{}",
                local_zip_filename(chunk),
                zip_path.display()
            ));
        }

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: 0,
                total: chunk.size,
                phase: "verifying".into(),
            },
        );

        let actual_hash = sha256_of_file(&zip_path)?;
        if actual_hash != chunk.sha256 {
            return Err(format!(
                "分块 {} 校验失败：清单要求 sha256={}，实际为 {}",
                chunk.name, chunk.sha256, actual_hash
            ));
        }

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: chunk.size,
                total: chunk.size,
                phase: "verifying".into(),
            },
        );

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: 0,
                total: chunk.size,
                phase: "extracting".into(),
            },
        );

        extract_chunk_zip(&zip_path, &backend_dir)?;

        new_state.chunks.insert(
            chunk.name.clone(),
            InstalledChunkInfo {
                version: chunk.version.clone(),
                sha256: chunk.sha256.clone(),
            },
        );

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: chunk.size,
                total: chunk.size,
                phase: "extracting".into(),
            },
        );
    }

    for chunk in &plan.skip_chunks {
        if let Some(existing) = local.chunks.get(chunk) {
            new_state.chunks.insert(chunk.clone(), existing.clone());
        }
    }

    new_state.installed_at = chrono_now_iso();
    write_installed_state(app_handle, &new_state)?;

    let _ = app_handle.emit(
        "runtime-update-progress",
        DownloadProgress {
            chunk_name: "all".into(),
            downloaded: plan.total_download_size,
            total: plan.total_download_size,
            phase: "done".into(),
        },
    );

    Ok(plan)
}

pub async fn fetch_remote_manifest(url: &str) -> Result<RuntimeManifest, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| format!("创建 HTTP 客户端失败: {}", e))?;

    let resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("请求远端清单失败: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("远端清单返回 HTTP {}", resp.status()));
    }

    let body = resp
        .text()
        .await
        .map_err(|e| format!("读取远端清单内容失败: {}", e))?;

    serde_json::from_str(&body)
        .map_err(|e| format!("解析远端清单 JSON 失败: {}", e))
}

// ── 计算更新计划 ──────────────────────────────────────────────────

pub fn compute_update_plan(local: &InstalledState, remote: &RuntimeManifest) -> RuntimeUpdateInfo {
    let mut to_update: Vec<RuntimeChunk> = Vec::new();
    let mut skip: Vec<String> = Vec::new();

    for chunk in &remote.chunks {
        if let Some(installed) = local.chunks.get(&chunk.name) {
            if installed.sha256 == chunk.sha256 {
                skip.push(chunk.name.clone());
                continue;
            }
        }
        to_update.push(chunk.clone());
    }

    let total_size: u64 = to_update.iter().map(|c| c.size).sum();

    RuntimeUpdateInfo {
        available: !to_update.is_empty(),
        current_version: local.runtime_version.clone(),
        remote_version: remote.runtime_version.clone(),
        chunks_to_update: to_update,
        total_download_size: total_size,
        skip_chunks: skip,
    }
}

// ── SHA256 校验 ────────────────────────────────────────────────────

fn sha256_of_file(path: &Path) -> Result<String, String> {
    let mut file = std::fs::File::open(path)
        .map_err(|e| format!("打开文件 {} 失败: {}", path.display(), e))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 64];
    loop {
        let n = file
            .read(&mut buf)
            .map_err(|e| format!("读取文件失败: {}", e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

// ── 下载单个 chunk ────────────────────────────────────────────────

async fn download_chunk_to_file(
    chunk: &RuntimeChunk,
    dest: &Path,
    app_handle: &AppHandle,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3600))
        .build()
        .map_err(|e| format!("创建 HTTP 客户端失败: {}", e))?;

    let resp = client
        .get(&chunk.url)
        .send()
        .await
        .map_err(|e| format!("下载 {} 失败: {}", chunk.name, e))?;

    if !resp.status().is_success() {
        return Err(format!(
            "下载 {} 返回 HTTP {}",
            chunk.name,
            resp.status()
        ));
    }

    let total = resp.content_length().unwrap_or(chunk.size);

    if let Some(dir) = dest.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let mut file = std::fs::File::create(dest)
        .map_err(|e| format!("创建文件 {} 失败: {}", dest.display(), e))?;

    let mut downloaded: u64 = 0;
    let mut stream = resp.bytes_stream();
    use futures_util::StreamExt;
    while let Some(item) = stream.next().await {
        let bytes = item.map_err(|e| format!("下载流读取失败: {}", e))?;
        file.write_all(&bytes)
            .map_err(|e| format!("写入文件失败: {}", e))?;
        downloaded += bytes.len() as u64;
        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded,
                total,
                phase: "downloading".into(),
            },
        );
    }

    file.flush()
        .map_err(|e| format!("flush 文件失败: {}", e))?;
    drop(file);

    let actual_hash = sha256_of_file(dest)?;
    if actual_hash != chunk.sha256 {
        let _ = std::fs::remove_file(dest);
        return Err(format!(
            "chunk {} 校验失败：期望 {} 实际 {}",
            chunk.name, chunk.sha256, actual_hash
        ));
    }

    Ok(())
}

// ── 解压 chunk zip 到目标目录 ──────────────────────────────────────

fn extract_chunk_zip(zip_path: &Path, dest_dir: &Path) -> Result<(), String> {
    let file = std::fs::File::open(zip_path)
        .map_err(|e| format!("打开 zip {} 失败: {}", zip_path.display(), e))?;

    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| format!("解析 zip 失败: {}", e))?;

    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("读取 zip 条目失败: {}", e))?;

        let out_path = match entry.enclosed_name() {
            Some(p) => dest_dir.join(p),
            None => continue,
        };

        if entry.is_dir() {
            let _ = std::fs::create_dir_all(&out_path);
        } else {
            if let Some(parent) = out_path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let mut out_file = std::fs::File::create(&out_path)
                .map_err(|e| format!("创建 {} 失败: {}", out_path.display(), e))?;
            std::io::copy(&mut entry, &mut out_file)
                .map_err(|e| format!("解压 {} 失败: {}", out_path.display(), e))?;
        }
    }

    Ok(())
}

// ── 公开 API：检查更新 ────────────────────────────────────────────

pub async fn check_update(app_handle: &AppHandle) -> Result<RuntimeUpdateInfo, String> {
    let url = manifest_url_from_env()
        .ok_or_else(|| "未配置运行时更新地址（环境变量 SACV_RUNTIME_MANIFEST_URL）".to_string())?;

    let local = read_installed_state(app_handle)?;
    let remote = fetch_remote_manifest(&url).await?;

    Ok(compute_update_plan(&local, &remote))
}

// ── 公开 API：下载并安装更新 ──────────────────────────────────────

pub async fn download_and_apply(app_handle: &AppHandle) -> Result<RuntimeUpdateInfo, String> {
    let url = manifest_url_from_env()
        .ok_or_else(|| "未配置运行时更新地址（环境变量 SACV_RUNTIME_MANIFEST_URL）".to_string())?;

    let local = read_installed_state(app_handle)?;
    let remote = fetch_remote_manifest(&url).await?;
    let plan = compute_update_plan(&local, &remote);

    if !plan.available {
        return Ok(plan);
    }

    let app_data_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法获取应用数据目录: {}", e))?;
    let backend_dir = app_data_dir.join("superAutoCutVideoBackend");
    let chunks_cache = app_data_dir.join("runtime_chunks_cache");
    let _ = std::fs::create_dir_all(&chunks_cache);
    let _ = std::fs::create_dir_all(&backend_dir);

    let mut new_state = local.clone();
    new_state.schema_version = 1;
    new_state.runtime_version = remote.runtime_version.clone();
    new_state.variant = remote.variant.clone();

    for chunk in &plan.chunks_to_update {
        let zip_file = chunks_cache.join(format!("{}-{}.zip", chunk.name, chunk.version));

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: 0,
                total: chunk.size,
                phase: "downloading".into(),
            },
        );

        download_chunk_to_file(chunk, &zip_file, app_handle).await?;

        let _ = app_handle.emit(
            "runtime-update-progress",
            DownloadProgress {
                chunk_name: chunk.name.clone(),
                downloaded: chunk.size,
                total: chunk.size,
                phase: "extracting".into(),
            },
        );

        extract_chunk_zip(&zip_file, &backend_dir)?;

        new_state.chunks.insert(
            chunk.name.clone(),
            InstalledChunkInfo {
                version: chunk.version.clone(),
                sha256: chunk.sha256.clone(),
            },
        );

        let _ = std::fs::remove_file(&zip_file);
    }

    for chunk in &plan.skip_chunks {
        if let Some(existing) = local.chunks.get(chunk) {
            new_state.chunks.insert(chunk.clone(), existing.clone());
        }
    }

    new_state.installed_at = chrono_now_iso();
    write_installed_state(app_handle, &new_state)?;

    let _ = app_handle.emit(
        "runtime-update-progress",
        DownloadProgress {
            chunk_name: "all".into(),
            downloaded: plan.total_download_size,
            total: plan.total_download_size,
            phase: "done".into(),
        },
    );

    Ok(plan)
}

// ── 公开 API：读取本地已安装信息 ──────────────────────────────────

pub async fn get_installed_info(app_handle: &AppHandle) -> Result<InstalledState, String> {
    read_installed_state(app_handle)
}

// 简单时间戳
fn chrono_now_iso() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    format!("{}Z", now.as_secs())
}
