// AI智能视频剪辑桌面应用 - Tauri Rust桥接层
// 负责启动Python后端、文件系统访问和前后端通信桥接

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use rand::rngs::OsRng;
use rand::RngCore;
use serde::{Deserialize, Serialize};
#[cfg(target_os = "windows")]
use std::io::{Read, Write};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State};

mod json_util;
mod offline_bundle;
mod runtime_updater;
#[cfg(target_os = "windows")]
use sha2::{Digest, Sha256};
#[cfg(target_os = "windows")]
use zip::ZipArchive;

// Windows: 隐藏子进程窗口（CREATE_NO_WINDOW）
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn apply_windows_no_window(cmd: Command) -> Command {
    #[cfg(target_os = "windows")]
    {
        let mut cmd = cmd;
        cmd.creation_flags(CREATE_NO_WINDOW);
        return cmd;
    }
    #[cfg(not(target_os = "windows"))]
    {
        cmd
    }
}

#[cfg(target_os = "windows")]
fn kill_all_backend_processes() {
    // 强制结束所有后端进程（包括可能残留的 PyInstaller 子进程）
    let mut cmd = Command::new("taskkill");
    cmd.args(["/F", "/IM", "superAutoCutVideoBackend.exe", "/T"]);
    let _ = apply_windows_no_window(cmd).status();
}

#[derive(Serialize, Deserialize, Clone)]
struct BackendReadyPayload {
    port: u16,
    boot_token: Option<String>,
}

// 应用状态结构
struct AppState {
    backend_process: Arc<Mutex<Option<Child>>>,
    backend_port: Arc<Mutex<u16>>,
    backend_starting: Arc<AtomicBool>,
    backend_boot_token: Arc<Mutex<Option<String>>>,
    /// 后端 HTTP 就绪后缓存（防止 frontend 尚未 listen 时丢失 backend-ready 事件）
    pending_backend_ready: Arc<Mutex<Option<BackendReadyPayload>>>,
    app_is_quitting: Arc<AtomicBool>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            backend_process: Arc::new(Mutex::new(None)),
            backend_port: Arc::new(Mutex::new(0)),
            backend_starting: Arc::new(AtomicBool::new(false)),
            backend_boot_token: Arc::new(Mutex::new(None)),
            pending_backend_ready: Arc::new(Mutex::new(None)),
            app_is_quitting: Arc::new(AtomicBool::new(false)),
        }
    }
}

/// 确保 `backend_starting` 在 `start_backend` 任意返回路径上都会被复位（避免卡死在「正在启动中」）。
struct BackendStartingLease<'a> {
    flag: &'a AtomicBool,
}

impl<'a> BackendStartingLease<'a> {
    fn begin(state: &'a AppState) -> Self {
        Self {
            flag: &state.backend_starting,
        }
    }
}

impl Drop for BackendStartingLease<'_> {
    fn drop(&mut self) {
        self.flag.store(false, Ordering::SeqCst);
    }
}

const BACKEND_IDENTIFIER: &str = "super-auto-cut-video-backend";

// 后端状态响应
#[derive(Serialize, Deserialize, Debug)]
struct BackendStatus {
    running: bool,
    port: u16,
    pid: Option<u32>,
    boot_token: Option<String>,
}

#[derive(Serialize, Debug)]
struct BackendResourceStatus {
    resource_dir: String,
    resource_root: String,
    zip_path: String,
    zip_exists: bool,
    zip_size: u64,
    extract_dir: String,
    extract_dir_exists: bool,
    backend_exe_path: String,
    backend_exe_exists: bool,
    nested_backend_exe_path: String,
    nested_backend_exe_exists: bool,
    ready: bool,
    message: String,
}

#[cfg(target_os = "windows")]
#[derive(Serialize, Clone)]
struct BackendExtractProgress {
    phase: String,
    extracted: u64,
    total: u64,
    current_file: String,
    current_index: u64,
    total_files: u64,
}

fn emit_backend_ready(app_handle: &AppHandle, port: u16, boot_token: Option<String>) {
    let payload = BackendReadyPayload {
        port,
        boot_token: boot_token.clone(),
    };
    {
        let state = app_handle.state::<AppState>();
        *state.pending_backend_ready.lock().unwrap() = Some(payload.clone());
    }
    let _ = app_handle.emit("backend-ready", payload);
}

fn backend_ready_status(
    app_handle: &AppHandle,
    port: u16,
    pid: Option<u32>,
    boot_token: Option<String>,
) -> BackendStatus {
    emit_backend_ready(app_handle, port, boot_token.clone());
    BackendStatus {
        running: true,
        port,
        pid,
        boot_token,
    }
}

// 文件选择结果
#[derive(Serialize, Deserialize)]
struct FileSelection {
    path: Option<String>,
    cancelled: bool,
}

fn backend_ready_wait_secs(is_dev_mode: bool) -> u64 {
    if is_dev_mode {
        90
    } else {
        360
    }
}

async fn probe_backend_ready(host: &str, port: u16) -> bool {
    if port == 0 {
        return false;
    }
    let url = format!("http://{}:{}/api/hello", host, port);
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_millis(1200))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    client
        .get(&url)
        .send()
        .await
        .map(|resp| resp.status().is_success())
        .unwrap_or(false)
}

async fn wait_for_backend_ready(host: &str, port: u16, total_wait_secs: u64) -> bool {
    let url = format!("http://{}:{}/api/hello", host, port);
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_millis(3000))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };

    let attempts = total_wait_secs * 4; // 250ms * 4 per second
    for _ in 0..attempts {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => return true,
            _ => {
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        }
    }
    false
}

fn generate_boot_token() -> String {
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push_str(&format!("{:02x}", b));
    }
    out
}

async fn discover_existing_backend(
    host: &str,
    require_token: bool,
) -> Option<(u16, Option<String>)> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_millis(600))
        .build()
        .ok()?;
    let ranges: &[(u16, u16)] = &[(8000, 8101), (18000, 18101)];
    for (start, end) in ranges {
        for p in *start..*end {
            let url = format!("http://{}:{}/api/server/info", host, p);
            let resp = match client.get(&url).send().await {
                Ok(r) => r,
                Err(_) => continue,
            };
            if !resp.status().is_success() {
                continue;
            }
            let v: serde_json::Value = match resp.json().await {
                Ok(v) => v,
                Err(_) => continue,
            };
            let data = match v.get("data") {
                Some(d) => d,
                None => continue,
            };
            let identifier = match data.get("identifier").and_then(|s| s.as_str()) {
                Some(s) => s,
                None => continue,
            };
            if identifier != BACKEND_IDENTIFIER {
                continue;
            }
            let reported_port = data
                .get("port")
                .and_then(|n| n.as_u64())
                .and_then(|n| u16::try_from(n).ok())
                .unwrap_or(p);
            let boot_token = data
                .get("boot_token")
                .and_then(|t| t.as_str())
                .map(|t| t.to_string())
                .filter(|t| !t.is_empty());
            if require_token && boot_token.is_none() {
                continue;
            }
            return Some((reported_port, boot_token));
        }
    }
    None
}

async fn check_backend_on_port(
    host: &str,
    port: u16,
    timeout_ms: u64,
    require_token: bool,
) -> Option<(u16, Option<String>)> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .build()
        .ok()?;
    let url = format!("http://{}:{}/api/server/info", host, port);
    let resp = client.get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: serde_json::Value = resp.json().await.ok()?;
    let data = v.get("data")?;
    let identifier = data.get("identifier").and_then(|s| s.as_str())?;
    if identifier != BACKEND_IDENTIFIER {
        return None;
    }
    let reported_port = data
        .get("port")
        .and_then(|n| n.as_u64())
        .and_then(|n| u16::try_from(n).ok())
        .unwrap_or(port);
    let boot_token = data
        .get("boot_token")
        .and_then(|t| t.as_str())
        .map(|t| t.to_string())
        .filter(|t| !t.is_empty());
    if require_token && boot_token.is_none() {
        return None;
    }
    Some((reported_port, boot_token))
}

async fn discover_existing_backend_quick(
    host: &str,
    require_token: bool,
) -> Option<(u16, Option<String>)> {
    if let Some(p) = parse_backend_port_from_log() {
        if let Some(found) = check_backend_on_port(host, p, 200, require_token).await {
            return Some(found);
        }
    }
    for p in [18000u16, 8000u16] {
        if let Some(found) = check_backend_on_port(host, p, 200, require_token).await {
            return Some(found);
        }
    }
    None
}

fn parse_backend_port_from_log() -> Option<u16> {
    let log_path = std::env::temp_dir().join("super_auto_cut_backend.log");
    let content = std::fs::read_to_string(&log_path).ok()?;
    let needles = [
        "Uvicorn running on http://127.0.0.1:",
        "[stdout] Uvicorn running on http://127.0.0.1:",
        "[stderr] Uvicorn running on http://127.0.0.1:",
    ];
    for needle in &needles {
        if let Some(pos) = content.rfind(needle) {
            let start = pos + needle.len();
            let bytes = content.as_bytes();
            let mut i = start;
            let mut num: u16 = 0;
            while i < bytes.len() {
                let c = bytes[i];
                if c.is_ascii_digit() {
                    num = num.saturating_mul(10).saturating_add((c - b'0') as u16);
                    i += 1;
                } else {
                    break;
                }
            }
            if num > 0 {
                return Some(num);
            }
        }
    }
    if let Some(pos) = content.rfind("http://127.0.0.1:") {
        let line_start = content[..pos].rfind('\n').map(|i| i + 1).unwrap_or(0);
        let line_end = content[pos..].find('\n').map(|i| pos + i).unwrap_or(content.len());
        let line = &content[line_start..line_end];
        let lower = line.to_lowercase();
        if lower.contains("running on") || lower.contains("listening on") || lower.contains("serving on") {
            let start = pos + "http://127.0.0.1:".len();
            let bytes = content.as_bytes();
            let mut i = start;
            let mut num: u16 = 0;
            while i < bytes.len() {
                let c = bytes[i];
                if c.is_ascii_digit() {
                    num = num.saturating_mul(10).saturating_add((c - b'0') as u16);
                    i += 1;
                } else {
                    break;
                }
            }
            if num > 0 {
                return Some(num);
            }
        }
    }
    None
}

#[cfg(target_os = "windows")]
async fn ensure_ffmpeg_binaries(resource_dir: &PathBuf) -> Result<(), String> {
    let ffmpeg_path = resource_dir.join("ffmpeg.exe");
    let ffprobe_path = resource_dir.join("ffprobe.exe");
    if ffmpeg_path.exists() && ffprobe_path.exists() {
        return Ok(());
    }
    if let (Ok(ff_in_path), Ok(fp_in_path)) = (which::which("ffmpeg.exe"), which::which("ffprobe.exe")) {
        if let Err(e) = std::fs::create_dir_all(&resource_dir) {
            return Err(format!("创建资源目录失败: {}", e));
        }
        if let Err(e) = std::fs::copy(&ff_in_path, &ffmpeg_path) {
            return Err(format!("复制ffmpeg失败 {:?} -> {:?}: {}", ff_in_path, ffmpeg_path, e));
        }
        if let Err(e) = std::fs::copy(&fp_in_path, &ffprobe_path) {
            return Err(format!("复制ffprobe失败 {:?} -> {:?}: {}", fp_in_path, ffprobe_path, e));
        }
        return Ok(());
    }
    let url = std::env::var("FFMPEG_WIN_ZIP_URL").ok().unwrap_or_else(|| {
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip".to_string()
    });
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|e| format!("创建下载客户端失败: {}", e))?;
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("下载FFmpeg压缩包失败: {}", e))?;
    if !resp.status().is_success() {
        return Err(format!("下载FFmpeg压缩包返回状态异常: {}", resp.status()));
    }
    let bytes = resp
        .bytes()
        .await
        .map_err(|e| format!("读取FFmpeg压缩包内容失败: {}", e))?;
    let cursor = std::io::Cursor::new(bytes);
    let mut archive =
        ZipArchive::new(cursor).map_err(|e| format!("解析FFmpeg压缩包失败: {}", e))?;

    let mut found_ffmpeg = false;
    let mut found_ffprobe = false;

    for i in 0..archive.len() {
        let mut file = archive
            .by_index(i)
            .map_err(|e| format!("读取压缩包文件失败: {}", e))?;
        let name = file.name().to_string();
        let is_ffmpeg = name.ends_with("/bin/ffmpeg.exe")
            || name.ends_with("\\bin\\ffmpeg.exe")
            || name.ends_with("ffmpeg.exe");
        let is_ffprobe = name.ends_with("/bin/ffprobe.exe")
            || name.ends_with("\\bin\\ffprobe.exe")
            || name.ends_with("ffprobe.exe");

        if is_ffmpeg || is_ffprobe {
            let out_path = if is_ffmpeg {
                ffmpeg_path.clone()
            } else {
                ffprobe_path.clone()
            };
            // 确保资源目录存在
            if let Err(e) = std::fs::create_dir_all(&resource_dir) {
                return Err(format!("创建资源目录失败: {}", e));
            }
            let mut out_file = std::fs::File::create(&out_path)
                .map_err(|e| format!("创建文件失败 {:?}: {}", out_path, e))?;
            let mut buf = Vec::new();
            file.read_to_end(&mut buf)
                .map_err(|e| format!("读取压缩包条目失败: {}", e))?;
            out_file
                .write_all(&buf)
                .map_err(|e| format!("写入文件失败 {:?}: {}", out_path, e))?;
            if is_ffmpeg {
                found_ffmpeg = true;
            } else {
                found_ffprobe = true;
            }
        }
        if found_ffmpeg && found_ffprobe {
            break;
        }
    }

    if !found_ffmpeg || !found_ffprobe {
        return Err("压缩包中未找到 ffmpeg.exe 或 ffprobe.exe".to_string());
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn zip_mtime_and_size(zip_path: &std::path::Path) -> Option<(String, u64)> {
    let meta = std::fs::metadata(zip_path).ok()?;
    let mt = meta.modified().ok()?;
    let d = mt.duration_since(std::time::UNIX_EPOCH).ok()?;
    let mtime = format!("{}.{}", d.as_secs(), d.subsec_nanos());
    Some((mtime, meta.len()))
}

#[cfg(target_os = "windows")]
enum BackendZipStamp {
    None,
    /// 旧版仅记录 zip 修改时间（单行）
    LegacyMtime(String),
    Full {
        version: String,
        mtime: String,
        size: u64,
        /// 仅扫描 zip 中央目录得到的指纹（杀毒/复制可能导致 mtime 变化但内容不变）
        index_sha256: Option<String>,
    },
}

#[cfg(target_os = "windows")]
fn parse_backend_zip_stamp(content: &str) -> BackendZipStamp {
    fn looks_like_sha256_hex(s: &str) -> bool {
        s.len() == 64 && s.chars().all(|c| c.is_ascii_hexdigit())
    }
    let lines: Vec<&str> = content
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .collect();
    match lines.len() {
        0 => BackendZipStamp::None,
        1 => BackendZipStamp::LegacyMtime(lines[0].to_string()),
        _ => {
            let size = lines
                .get(2)
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(0);
            let index_sha256 = lines
                .get(3)
                .copied()
                .filter(|s| looks_like_sha256_hex(s))
                .map(|s| s.to_string());
            BackendZipStamp::Full {
                version: lines[0].to_string(),
                mtime: lines[1].to_string(),
                size,
                index_sha256,
            }
        }
    }
}

/// 仅遍历 zip 条目元数据（不解压正文），用于判断 zip 是否实质变化。
#[cfg(target_os = "windows")]
fn zip_index_sha256(zip_path: &std::path::Path) -> Result<String, String> {
    let file =
        std::fs::File::open(zip_path).map_err(|e| format!("打开 zip 失败: {}", e))?;
    let mut archive =
        ZipArchive::new(file).map_err(|e| format!("解析 zip 失败: {}", e))?;
    let mut rows: Vec<(String, u32, u64, u64)> = Vec::with_capacity(archive.len());
    for i in 0..archive.len() {
        let f = archive
            .by_index(i)
            .map_err(|e| format!("读取 zip 条目失败: {}", e))?;
        rows.push((
            f.name().to_string(),
            f.crc32(),
            f.size(),
            f.compressed_size(),
        ));
    }
    rows.sort_by(|a, b| a.0.cmp(&b.0));
    let mut hasher = Sha256::new();
    for (name, crc, sz, csz) in rows {
        hasher.update(name.as_bytes());
        hasher.update(&[0u8]);
        hasher.update(crc.to_le_bytes());
        hasher.update(sz.to_le_bytes());
        hasher.update(csz.to_le_bytes());
    }
    Ok(format!("{:x}", hasher.finalize()))
}

#[cfg(target_os = "windows")]
fn write_backend_zip_stamp(
    stamp_path: &std::path::Path,
    app_version: &str,
    mtime: &str,
    size: u64,
    index_sha256: Option<&str>,
) {
    let text = match index_sha256 {
        Some(s) => format!("{}\n{}\n{}\n{}", app_version, mtime, size, s),
        None => format!("{}\n{}\n{}", app_version, mtime, size),
    };
    let _ = std::fs::write(stamp_path, text);
}

#[cfg(target_os = "windows")]
fn emit_backend_extract_progress(
    app_handle: &AppHandle,
    phase: &str,
    extracted: u64,
    total: u64,
    current_file: &str,
    current_index: u64,
    total_files: u64,
) {
    let _ = app_handle.emit(
        "backend-extract-progress",
        BackendExtractProgress {
            phase: phase.to_string(),
            extracted,
            total,
            current_file: current_file.to_string(),
            current_index,
            total_files,
        },
    );
}

#[cfg(target_os = "windows")]
fn extract_backend_zip_with_progress(
    app_handle: &AppHandle,
    zip_path: &std::path::Path,
    out_dir: &std::path::Path,
) -> Result<(), String> {
    let file = std::fs::File::open(zip_path).map_err(|e| format!("打开后端ZIP包失败: {}", e))?;
    let mut zip = ZipArchive::new(file).map_err(|e| format!("解析后端ZIP包失败: {}", e))?;
    let mut total: u64 = 0;
    let mut total_files: u64 = 0;
    for i in 0..zip.len() {
        let file = zip
            .by_index(i)
            .map_err(|e| format!("读取ZIP条目失败: {}", e))?;
        if !file.name().ends_with('/') {
            total = total.saturating_add(file.size());
            total_files = total_files.saturating_add(1);
        }
    }

    emit_backend_extract_progress(app_handle, "start", 0, total, "", 0, total_files);

    let mut extracted: u64 = 0;
    let mut file_index: u64 = 0;
    let mut last_emit_at = std::time::Instant::now();
    let mut last_emit_bytes: u64 = 0;
    let mut buffer = vec![0u8; 1024 * 1024];

    for i in 0..zip.len() {
        let mut entry = zip
            .by_index(i)
            .map_err(|e| format!("读取ZIP条目失败: {}", e))?;
        let enclosed = match entry.enclosed_name() {
            Some(p) => p.to_owned(),
            None => continue,
        };
        let out_path = out_dir.join(enclosed);

        if entry.name().ends_with('/') {
            std::fs::create_dir_all(&out_path)
                .map_err(|e| format!("创建后端目录失败 {:?}: {}", out_path, e))?;
            continue;
        }

        file_index = file_index.saturating_add(1);
        if let Some(parent) = out_path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("创建后端目录失败 {:?}: {}", parent, e))?;
        }

        let current_file = entry.name().to_string();
        emit_backend_extract_progress(
            app_handle,
            "extracting",
            extracted,
            total,
            &current_file,
            file_index,
            total_files,
        );

        let mut out_file = std::fs::File::create(&out_path)
            .map_err(|e| format!("创建后端文件失败 {:?}: {}", out_path, e))?;
        loop {
            let read = entry
                .read(&mut buffer)
                .map_err(|e| format!("读取后端ZIP内容失败 {}: {}", current_file, e))?;
            if read == 0 {
                break;
            }
            out_file
                .write_all(&buffer[..read])
                .map_err(|e| format!("写入后端文件失败 {:?}: {}", out_path, e))?;
            extracted = extracted.saturating_add(read as u64);

            let should_emit = extracted.saturating_sub(last_emit_bytes) >= 16 * 1024 * 1024
                || last_emit_at.elapsed() >= Duration::from_millis(500);
            if should_emit {
                emit_backend_extract_progress(
                    app_handle,
                    "extracting",
                    extracted,
                    total,
                    &current_file,
                    file_index,
                    total_files,
                );
                last_emit_at = std::time::Instant::now();
                last_emit_bytes = extracted;
            }
        }
    }

    emit_backend_extract_progress(
        app_handle,
        "done",
        total,
        total,
        "",
        total_files,
        total_files,
    );
    Ok(())
}

#[cfg(target_os = "windows")]
fn ensure_backend_executable_available(
    _app_handle: &AppHandle,
    resource_root: &PathBuf,
) -> Result<PathBuf, String> {
    // 解压到安装目录侧 resources（与 superAutoCutVideoBackend.zip 同目录），不再使用 %APPDATA%
    let extracted_backend_dir = resource_root.join("superAutoCutVideoBackend");
    let nested_backend_dir = extracted_backend_dir.join("superAutoCutVideoBackend");
    let zip_path = resource_root.join("superAutoCutVideoBackend.zip");
    let stamp_path = extracted_backend_dir.join(".backend_zip_stamp");
    let app_version = _app_handle.package_info().version.to_string();

    let is_valid_backend_root = |root: &std::path::Path| -> Option<PathBuf> {
        let exe = root.join("superAutoCutVideoBackend.exe");
        if !exe.exists() {
            return None;
        }
        let internal_dll = root.join("_internal").join("python311.dll");
        if internal_dll.exists() {
            Some(exe)
        } else {
            None
        }
    };

    if !zip_path.exists() {
        return Ok(extracted_backend_dir.join("superAutoCutVideoBackend.exe"));
    }

    let (want_mtime, want_size) = match zip_mtime_and_size(&zip_path) {
        Some(v) => v,
        None => {
            return Ok(extracted_backend_dir.join("superAutoCutVideoBackend.exe"));
        }
    };

    let stamp_raw = std::fs::read_to_string(&stamp_path).unwrap_or_default();
    let stamp = parse_backend_zip_stamp(&stamp_raw);

    let zip_fingerprint_matches = match &stamp {
        BackendZipStamp::Full { mtime, size, .. } => *mtime == want_mtime && *size == want_size,
        BackendZipStamp::LegacyMtime(m) => *m == want_mtime,
        BackendZipStamp::None => false,
    };

    let preserved_index_sha = match &stamp {
        BackendZipStamp::Full {
            index_sha256: Some(s), ..
        } => Some(s.as_str()),
        _ => None,
    };

    if zip_fingerprint_matches {
        if let Some(exe) = is_valid_backend_root(&extracted_backend_dir) {
            let need_stamp_update = match &stamp {
                BackendZipStamp::Full { version, .. } => version != &app_version,
                BackendZipStamp::LegacyMtime(_) => true,
                BackendZipStamp::None => true,
            };
            if need_stamp_update {
                let _ = std::fs::create_dir_all(&extracted_backend_dir);
                write_backend_zip_stamp(
                    &stamp_path,
                    &app_version,
                    &want_mtime,
                    want_size,
                    preserved_index_sha,
                );
            }
            return Ok(exe);
        }
        if let Some(exe) = is_valid_backend_root(&nested_backend_dir) {
            let need_stamp_update = match &stamp {
                BackendZipStamp::Full { version, .. } => version != &app_version,
                BackendZipStamp::LegacyMtime(_) => true,
                BackendZipStamp::None => true,
            };
            if need_stamp_update {
                let _ = std::fs::create_dir_all(&extracted_backend_dir);
                write_backend_zip_stamp(
                    &stamp_path,
                    &app_version,
                    &want_mtime,
                    want_size,
                    preserved_index_sha,
                );
            }
            return Ok(exe);
        }
    }

    // mtime/size 可能因杀毒扫描、同步盘等变化；若 stamp 中已有索引指纹且解压目录仍完整，则跳过整包解压
    if !zip_fingerprint_matches {
        if let BackendZipStamp::Full {
            index_sha256: Some(stored_sha),
            ..
        } = &stamp
        {
            if let Some(exe) = is_valid_backend_root(&extracted_backend_dir)
                .or_else(|| is_valid_backend_root(&nested_backend_dir))
            {
                if let Ok(computed) = zip_index_sha256(&zip_path) {
                    if computed == *stored_sha {
                        let _ = std::fs::create_dir_all(&extracted_backend_dir);
                        write_backend_zip_stamp(
                            &stamp_path,
                            &app_version,
                            &want_mtime,
                            want_size,
                            Some(stored_sha.as_str()),
                        );
                        return Ok(exe);
                    }
                }
            }
        }
    }

    if extracted_backend_dir.exists() {
        let _ = std::fs::remove_dir_all(&extracted_backend_dir);
    }

    let _ = std::fs::create_dir_all(&extracted_backend_dir);

    let mut zip_extract_ok = false;
    match extract_backend_zip_with_progress(_app_handle, &zip_path, &extracted_backend_dir) {
        Ok(()) => {
            zip_extract_ok = true;
        }
        Err(e) => {
            emit_backend_extract_progress(_app_handle, "fallback", 0, want_size, "", 0, 0);
            eprintln!("内置ZIP解压失败，尝试 PowerShell Expand-Archive: {}", e);
        }
    }
    if !zip_extract_ok {
        let zip_s = zip_path.to_string_lossy().to_string();
        let out_dir_s = extracted_backend_dir.to_string_lossy().to_string();
        let zip_q = zip_s.replace('\'', "''");
        let out_q = out_dir_s.replace('\'', "''");
        let cmd = format!(
            "Expand-Archive -LiteralPath '{}' -DestinationPath '{}' -Force",
            zip_q, out_q
        );
        let status = Command::new("powershell")
            .creation_flags(0x08000000)
            .arg("-NoLogo")
            .arg("-NoProfile")
            .arg("-NonInteractive")
            .arg("-WindowStyle")
            .arg("Hidden")
            .arg("-Command")
            .arg(cmd)
            .status()
            .map_err(|e| format!("调用 PowerShell 解压失败: {}", e))?;
        if !status.success() {
            return Err(format!(
                "解压后端ZIP包失败: zip={} out={} code={:?}",
                zip_path.to_string_lossy(),
                extracted_backend_dir.to_string_lossy(),
                status.code()
            ));
        }
        emit_backend_extract_progress(_app_handle, "done", want_size, want_size, "", 0, 0);
    }

    let index_sha = zip_index_sha256(&zip_path).ok();
    write_backend_zip_stamp(
        &stamp_path,
        &app_version,
        &want_mtime,
        want_size,
        index_sha.as_deref(),
    );

    if let Some(exe) = is_valid_backend_root(&extracted_backend_dir) {
        return Ok(exe);
    }
    if let Some(exe) = is_valid_backend_root(&nested_backend_dir) {
        return Ok(exe);
    }
    if extracted_backend_dir.exists() {
        let _ = std::fs::remove_dir_all(&extracted_backend_dir);
    }

    Err("解压后未找到 superAutoCutVideoBackend.exe".to_string())
}

fn append_log_line(path: PathBuf, line: &str) {
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        use std::io::Write;
        let _ = writeln!(file, "{}", line);
    }
}

fn resolve_backend_resource_root(app_handle: &AppHandle) -> (PathBuf, PathBuf) {
    let resource_dir = match app_handle.path().resource_dir() {
        Ok(p) => p,
        Err(_) => {
            let exe_dir_fallback = std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|d| d.to_path_buf()));
            if let Some(dir) = exe_dir_fallback {
                dir.join("resources")
            } else {
                std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from(".")).join("resources")
            }
        }
    };
    let resource_root = {
        let sub = resource_dir.join("resources");
        if sub.exists() { sub } else { resource_dir.clone() }
    };
    (resource_dir, resource_root)
}

fn inspect_backend_resource_status(app_handle: &AppHandle) -> BackendResourceStatus {
    let (resource_dir, resource_root) = resolve_backend_resource_root(app_handle);
    let zip_path = resource_root.join("superAutoCutVideoBackend.zip");
    let extract_dir = resource_root.join("superAutoCutVideoBackend");
    let backend_exe_path = if cfg!(target_os = "windows") {
        extract_dir.join("superAutoCutVideoBackend.exe")
    } else {
        extract_dir.join("superAutoCutVideoBackend")
    };
    let nested_backend_exe_path = if cfg!(target_os = "windows") {
        extract_dir
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend.exe")
    } else {
        extract_dir
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
    };

    let zip_exists = zip_path.is_file();
    let zip_size = std::fs::metadata(&zip_path).map(|m| m.len()).unwrap_or(0);
    let extract_dir_exists = extract_dir.is_dir();
    let backend_exe_exists = backend_exe_path.is_file();
    let nested_backend_exe_exists = nested_backend_exe_path.is_file();
    let ready = backend_exe_exists || nested_backend_exe_exists;
    let message = if ready {
        "后端可执行文件已就绪".to_string()
    } else if zip_exists {
        "后端ZIP已复制到resources，等待解压或正在解压".to_string()
    } else if extract_dir_exists {
        "解压目录存在，但未找到后端可执行文件".to_string()
    } else {
        "未找到后端ZIP，也未找到已解压的后端目录".to_string()
    };

    BackendResourceStatus {
        resource_dir: resource_dir.to_string_lossy().to_string(),
        resource_root: resource_root.to_string_lossy().to_string(),
        zip_path: zip_path.to_string_lossy().to_string(),
        zip_exists,
        zip_size,
        extract_dir: extract_dir.to_string_lossy().to_string(),
        extract_dir_exists,
        backend_exe_path: backend_exe_path.to_string_lossy().to_string(),
        backend_exe_exists,
        nested_backend_exe_path: nested_backend_exe_path.to_string_lossy().to_string(),
        nested_backend_exe_exists,
        ready,
        message,
    }
}

fn is_port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).map(|_l| ()).is_ok()
}

fn choose_backend_port(is_dev_mode: bool) -> u16 {
    if is_dev_mode {
        let preferred = 8000;
        if is_port_available(preferred) {
            return preferred;
        }
        for p in preferred..=preferred + 100 {
            if is_port_available(p) {
                return p;
            }
        }
        for p in 18000..=18100 {
            if is_port_available(p) {
                return p;
            }
        }
        preferred
    } else {
        for p in 18000..=18100 {
            if is_port_available(p) {
                return p;
            }
        }
        for p in 8000..=8100 {
            if is_port_available(p) {
                return p;
            }
        }
        TcpListener::bind(("127.0.0.1", 0))
            .ok()
            .and_then(|l| l.local_addr().ok())
            .map(|a| a.port())
            .unwrap_or(18000)
    }
}

// Tauri命令：启动Python后端
#[tauri::command]
async fn start_backend(
    state: State<'_, AppState>,
    app_handle: AppHandle,
) -> Result<BackendStatus, String> {
    let early_log_path = std::env::temp_dir().join("super_auto_cut_backend.log");
    let _ = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&early_log_path);
    append_log_line(early_log_path.clone(), "[meta] start_backend invoked");

    let host = "127.0.0.1";
    let is_dev_mode =
        cfg!(debug_assertions) || std::env::var("TAURI_DEV").ok().as_deref() == Some("1");
    let ready_wait_secs = backend_ready_wait_secs(is_dev_mode);

    // 最早期并发启动防护：若已有启动流程进行中，则等待其更新状态，避免重复拉起
    if state.backend_starting.swap(true, Ordering::SeqCst) {
        for _ in 0..(ready_wait_secs * 4) {
            tokio::time::sleep(Duration::from_millis(250)).await;
            let port = *state.backend_port.lock().unwrap();
            let boot_token = state.backend_boot_token.lock().unwrap().clone();
            let has_process = {
                let process_guard = state.backend_process.lock().unwrap();
                process_guard.is_some()
            };
            if port != 0 && probe_backend_ready(host, port).await {
                println!(
                    "[backend] 启动中（复用已有启动流程）：http://127.0.0.1:{}",
                    port
                );
                return Ok(backend_ready_status(
                    &app_handle,
                    port,
                    None,
                    boot_token,
                ));
            }
            if !has_process && port == 0 {
                break;
            }
        }
        append_log_line(
            early_log_path.clone(),
            "[meta] start_backend rejected: another start still in progress",
        );
        return Err("后端正在启动中，请稍后重试".to_string());
    }

    let _starting_lease = BackendStartingLease::begin(&state);

    // 先短暂持锁检查和清理状态，避免并发重复启动
    let existing_running = {
        let mut process_guard = state.backend_process.lock().unwrap();
        if let Some(ref mut child) = *process_guard {
            match child.try_wait() {
                Ok(Some(_)) => {
                    *process_guard = None;
                    None
                }
                Ok(None) => Some((
                    *state.backend_port.lock().unwrap(),
                    state.backend_boot_token.lock().unwrap().clone(),
                    child.id(),
                )),
                Err(_) => {
                    *process_guard = None;
                    None
                }
            }
        } else {
            None
        }
    };
    if let Some((port, boot_token, pid)) = existing_running {
        if port != 0 && wait_for_backend_ready(host, port, ready_wait_secs).await {
            println!("[backend] 已在运行并就绪：http://{}:{} (pid={})", host, port, pid);
            return Ok(backend_ready_status(
                &app_handle,
                port,
                Some(pid),
                boot_token,
            ));
        }
        append_log_line(
            early_log_path.clone(),
            "[meta] start_backend: existing process not http-ready yet",
        );
        return Err(
            "后端进程已存在但尚未就绪，请查看 super_auto_cut_backend.log".to_string(),
        );
    }

    let forced_port_opt = std::env::var("SACV_FORCE_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .filter(|p| *p > 0);
    if is_dev_mode && forced_port_opt.is_none() {
        if let Some((p, boot_token)) = discover_existing_backend(host, false).await {
            *state.backend_port.lock().unwrap() = p;
            *state.backend_boot_token.lock().unwrap() = boot_token.clone();
            println!("[backend] 已发现运行中的后端：http://{}:{}", host, p);
            return Ok(backend_ready_status(&app_handle, p, None, boot_token));
        }
    }
    // 生产环境也尝试发现已运行的后端，避免重复启动
    if !is_dev_mode && forced_port_opt.is_none() {
        if let Some((p, boot_token)) = discover_existing_backend_quick(host, true).await {
            *state.backend_port.lock().unwrap() = p;
            *state.backend_boot_token.lock().unwrap() = boot_token.clone();
            println!("[backend] 已发现运行中的后端：http://{}:{}", host, p);
            return Ok(backend_ready_status(&app_handle, p, None, boot_token));
        }
    }

    // 获取资源目录路径（并准备后备路径：与应用同级 resources 目录）
    let (resource_dir, resource_root) = resolve_backend_resource_root(&app_handle);
    let exe_dir_fallback = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()));
    let install_dir = exe_dir_fallback
        .clone()
        .or_else(|| resource_dir.parent().map(|p| p.to_path_buf()));

    let force_packaged_backend =
        std::env::var("FORCE_PACKAGED_BACKEND").ok().as_deref() == Some("1");
    let backend_zip_path = resource_root.join("superAutoCutVideoBackend.zip");
    let backend_zip_exists = backend_zip_path.exists();
    let force_backend_reextract =
        std::env::var("SACV_FORCE_BACKEND_REEXTRACT").ok().as_deref() == Some("1");
    let backend_folder_exe = if cfg!(target_os = "windows") {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend.exe")
    } else {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
    };
    let backend_nested_folder_exe = if cfg!(target_os = "windows") {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend.exe")
    } else {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
    };
    let backend_folder_exists =
        !force_backend_reextract && (backend_folder_exe.exists() || backend_nested_folder_exe.exists());
    let prefer_python_backend =
        is_dev_mode && !force_packaged_backend && !backend_zip_exists && !backend_folder_exists;

    append_log_line(
        early_log_path.clone(),
        &format!(
            "[meta] is_dev_mode={} prefer_python_backend={} resource_dir={} resource_root={} backend_zip_exists={} backend_folder_exists={} force_backend_reextract={}",
            is_dev_mode,
            prefer_python_backend,
            resource_dir.to_string_lossy(),
            resource_root.to_string_lossy(),
            backend_zip_exists,
            backend_folder_exists,
            force_backend_reextract
        ),
    );

    if !is_dev_mode && !backend_zip_exists && !backend_folder_exists {
        *state.backend_port.lock().unwrap() = 0;
        *state.backend_boot_token.lock().unwrap() = None;
        let err = format!(
            "安装资源缺失：未找到 {}，也未找到已解压的后端目录 {}。请确认安装包同目录带有 superAutoCutVideoBackend_gpu.zip，或重新安装包含后端资源的版本。",
            backend_zip_path.to_string_lossy(),
            resource_root.join("superAutoCutVideoBackend").to_string_lossy()
        );
        append_log_line(early_log_path.clone(), &format!("[error] {}", err));
        return Err(err);
    }

    #[cfg(target_os = "windows")]
    let extracted_backend_exe =
        if !prefer_python_backend && backend_zip_exists && !backend_folder_exists {
            let zip_path = resource_root.join("superAutoCutVideoBackend.zip");
            append_log_line(
                early_log_path.clone(),
                &format!(
                    "[meta] backend_extract_dir={}",
                    resource_root
                        .join("superAutoCutVideoBackend")
                        .to_string_lossy()
                ),
            );
            append_log_line(
                early_log_path.clone(),
                &format!(
                    "[meta] backend_zip_exists={} backend_zip_path={}",
                    zip_path.exists(),
                    zip_path.to_string_lossy()
                ),
            );
            append_log_line(
                early_log_path.clone(),
                "[meta] ensure_backend_executable_available_begin",
            );
            let resource_root_blocking = resource_root.clone();
            let app_handle_blocking = app_handle.clone();
            match tokio::task::spawn_blocking(move || {
                ensure_backend_executable_available(&app_handle_blocking, &resource_root_blocking)
            })
            .await
            {
                Ok(Ok(p)) => {
                    append_log_line(
                        early_log_path.clone(),
                        &format!(
                            "[meta] ensure_backend_executable_available_ok={} exists={}",
                            p.to_string_lossy(),
                            p.exists()
                        ),
                    );
                    Some(p)
                }
                Ok(Err(e)) => {
                    append_log_line(
                        early_log_path.clone(),
                        &format!("[meta] ensure_backend_executable_available_error={}", e),
                    );
                    *state.backend_port.lock().unwrap() = 0;
                    *state.backend_boot_token.lock().unwrap() = None;
                    return Err(e);
                }
                Err(e) => {
                    let msg = format!("后端解压任务异常: {}", e);
                    append_log_line(early_log_path.clone(), &format!("[meta] {}", msg));
                    *state.backend_port.lock().unwrap() = 0;
                    *state.backend_boot_token.lock().unwrap() = None;
                    return Err(msg);
                }
            }
        } else {
            None
        };

    #[cfg(target_os = "windows")]
    {
        if is_dev_mode {
            if let Err(e) = ensure_ffmpeg_binaries(&resource_root).await {
                eprintln!("开发模式自动准备FFmpeg失败: {}", e);
            }
        }
    }

    // 尝试定位打包的后端可执行文件
    let primary_path_dir = if cfg!(target_os = "windows") {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend.exe")
    } else {
        resource_root
            .join("superAutoCutVideoBackend")
            .join("superAutoCutVideoBackend")
    };
    let primary_path_file = if cfg!(target_os = "windows") {
        resource_root.join("superAutoCutVideoBackend.exe")
    } else {
        resource_root.join("superAutoCutVideoBackend")
    };
    let mut candidates: Vec<PathBuf> = Vec::new();
    #[cfg(target_os = "windows")]
    if let Some(p) = extracted_backend_exe.clone() {
        candidates.push(p);
    }
    candidates.push(primary_path_dir.clone());
    candidates.push(backend_nested_folder_exe.clone());
    candidates.push(primary_path_file.clone());
    if let Some(dir) = &exe_dir_fallback {
        if cfg!(target_os = "windows") {
            candidates.push(dir.join("resources").join("superAutoCutVideoBackend.exe"));
            candidates.push(
                dir.join("resources")
                    .join("superAutoCutVideoBackend")
                    .join("superAutoCutVideoBackend.exe"),
            );
        } else {
            candidates.push(dir.join("resources").join("superAutoCutVideoBackend"));
            candidates.push(
                dir.join("resources")
                    .join("superAutoCutVideoBackend")
                    .join("superAutoCutVideoBackend"),
            );
        }
        for anc in dir.ancestors().take(8) {
            if cfg!(target_os = "windows") {
                candidates.push(
                    anc.join("src-tauri")
                        .join("resources")
                        .join("superAutoCutVideoBackend.exe"),
                );
                candidates.push(anc.join("resources").join("superAutoCutVideoBackend.exe"));
                candidates.push(
                    anc.join("src-tauri")
                        .join("resources")
                        .join("superAutoCutVideoBackend")
                        .join("superAutoCutVideoBackend.exe"),
                );
                candidates.push(
                    anc.join("resources")
                        .join("superAutoCutVideoBackend")
                        .join("superAutoCutVideoBackend.exe"),
                );
            } else {
                candidates.push(
                    anc.join("src-tauri")
                        .join("resources")
                        .join("superAutoCutVideoBackend"),
                );
                candidates.push(anc.join("resources").join("superAutoCutVideoBackend"));
                candidates.push(
                    anc.join("src-tauri")
                        .join("resources")
                        .join("superAutoCutVideoBackend")
                        .join("superAutoCutVideoBackend"),
                );
                candidates.push(
                    anc.join("resources")
                        .join("superAutoCutVideoBackend")
                        .join("superAutoCutVideoBackend"),
                );
            }
        }
    }
    let backend_executable = candidates
        .into_iter()
        .find(|p| p.exists())
        .unwrap_or(primary_path_dir.clone());
    append_log_line(
        early_log_path.clone(),
        &format!(
            "[meta] backend_executable_candidate={} exists={}",
            backend_executable.to_string_lossy(),
            backend_executable.exists()
        ),
    );

    #[cfg(target_os = "windows")]
    {
        if !backend_executable.exists() && !is_dev_mode {
            let _ = ensure_ffmpeg_binaries(&resource_root).await.map_err(|e| {
                eprintln!("自动准备FFmpeg失败: {}", &e);
                e
            });
        }
    }

    let mut cmd = if !prefer_python_backend && backend_executable.exists() {
        // 使用打包的可执行文件
        append_log_line(early_log_path.clone(), "[meta] use_packaged_backend_exe=1");
        println!("使用打包的后端可执行文件: {:?}", backend_executable);
        let backend_working_dir = backend_executable
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| resource_root.clone());
        let mut c = apply_windows_no_window(Command::new(&backend_executable));
        c.current_dir(backend_working_dir);
        c
    } else if is_dev_mode {
        let mut backend_script: Option<PathBuf> = None;
        let mut search_roots: Vec<PathBuf> = vec![resource_dir.clone()];
        if let Ok(exe) = std::env::current_exe() {
            search_roots.push(exe);
        }
        if let Ok(cwd) = std::env::current_dir() {
            search_roots.push(cwd);
        }
        for root in search_roots {
            for anc in root.ancestors().take(8) {
                let cand = anc.join("backend").join("main.py");
                if cand.exists() {
                    backend_script = Some(cand);
                    break;
                }
            }
            if backend_script.is_some() {
                break;
            }
        }
        let backend_script =
            backend_script.ok_or_else(|| "后端脚本不存在: backend/main.py".to_string())?;
        if !backend_script.exists() {
            return Err(format!("后端脚本不存在: {:?}", backend_script));
        }
        append_log_line(
            early_log_path.clone(),
            &format!(
                "[meta] use_python_backend_script={} ",
                backend_script.to_string_lossy()
            ),
        );
        println!("使用Python运行后端脚本: {:?}", backend_script);
        let backend_dir = backend_script.parent().unwrap().to_path_buf();
        let venv_py_unix = backend_dir.join(".venv").join("bin").join("python3");
        let venv_py_unix_alt = backend_dir.join(".venv").join("bin").join("python");
        let venv_py_win = backend_dir.join(".venv").join("Scripts").join("python.exe");
        let env_override = std::env::var("BACKEND_PYTHON").ok();
        let python_cmd: String = if let Some(p) = env_override {
            p
        } else if venv_py_unix.exists() {
            venv_py_unix.to_string_lossy().to_string()
        } else if venv_py_unix_alt.exists() {
            venv_py_unix_alt.to_string_lossy().to_string()
        } else if venv_py_win.exists() {
            venv_py_win.to_string_lossy().to_string()
        } else if which::which("python3").is_ok() {
            "python3".to_string()
        } else {
            "python".to_string()
        };
        append_log_line(
            early_log_path.clone(),
            &format!("[meta] python_cmd={}", python_cmd),
        );
        println!("选择的 Python 解释器: {}", python_cmd);
        let mut c = Command::new(python_cmd);
        c.arg(backend_script);
        #[cfg(target_os = "windows")]
        {
            c.creation_flags(CREATE_NO_WINDOW);
        }
        c.current_dir(backend_dir);
        c
    } else {
        let err = "未找到打包的后端可执行文件，请检查打包配置 bundle.resources".to_string();
        let path = std::env::temp_dir().join("super_auto_cut_backend.log");
        append_log_line(path, &format!("[error] {}", err));
        *state.backend_port.lock().unwrap() = 0;
        *state.backend_boot_token.lock().unwrap() = None;
        return Err(err);
    };

    // 设置环境变量
    let port_env = std::env::var("SACV_FORCE_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .filter(|p| *p > 0);
    let port: u16 = port_env.unwrap_or_else(|| choose_backend_port(is_dev_mode));
    let boot_token = generate_boot_token();
    let orig_path = std::env::var("PATH").unwrap_or_default();
    let sep = if cfg!(target_os = "windows") {
        ";"
    } else {
        ":"
    };
    let backend_dir = backend_executable
        .parent()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| resource_root.to_string_lossy().to_string());
    let resource_dir_s = resource_root.to_string_lossy().to_string();
    let internal_dir_s = backend_executable
        .parent()
        .map(|p| p.join("_internal"))
        .filter(|p| p.exists())
        .map(|p| p.to_string_lossy().to_string());
    let new_path = match internal_dir_s {
        Some(internal) => {
            if backend_dir != resource_dir_s {
                format!("{}{}{}{}{}{}{}", backend_dir, sep, resource_dir_s, sep, internal, sep, orig_path)
            } else {
                format!("{}{}{}{}{}", resource_dir_s, sep, internal, sep, orig_path)
            }
        }
        None => {
            if backend_dir != resource_dir_s {
                format!("{}{}{}{}{}", backend_dir, sep, resource_dir_s, sep, orig_path)
            } else {
                format!("{}{}{}", resource_dir_s, sep, orig_path)
            }
        }
    };
    let backend_tmp_dir = std::env::var("SACV_BACKEND_TMPDIR")
        .ok()
        .map(PathBuf::from)
        .or_else(|| app_handle.path().app_cache_dir().ok())
        .unwrap_or_else(std::env::temp_dir)
        .join("super_auto_cut_backend_tmp");
    let _ = std::fs::create_dir_all(&backend_tmp_dir);
    let backend_tmp_dir_s = backend_tmp_dir.to_string_lossy().to_string();
    *state.backend_port.lock().unwrap() = port;
    *state.backend_boot_token.lock().unwrap() = Some(boot_token.clone());
    cmd.env("HOST", host)
        .env("PORT", port.to_string())
        .env("PATH", new_path)
        .env("TEMP", backend_tmp_dir_s.clone())
        .env("TMP", backend_tmp_dir_s)
        .env("SACV_BOOT_TOKEN", boot_token.clone())
        .env("SACV_RUNTIME", "tauri")
        .env(
            "SACV_INSTALL_DIR",
            install_dir
                .as_ref()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default(),
        )
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // 启动进程
    match cmd.spawn() {
        Ok(mut child) => {
            println!(
                "[backend] 已启动进程，等待就绪：http://{}:{} (pid={})",
                host,
                port,
                child.id()
            );
            // 捕获日志到临时文件
            let log_path = std::env::temp_dir().join("super_auto_cut_backend.log");
            let _ = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path);
            if let Some(stdout) = child.stdout.take() {
                let path_clone = log_path.clone();
                thread::spawn(move || {
                    let reader = BufReader::new(stdout);
                    for line in reader.lines() {
                        if let Ok(l) = line {
                            append_log_line(path_clone.clone(), &format!("[stdout] {}", l));
                        }
                    }
                });
            }
            if let Some(stderr) = child.stderr.take() {
                let path_clone = log_path.clone();
                thread::spawn(move || {
                    let reader = BufReader::new(stderr);
                    for line in reader.lines() {
                        if let Ok(l) = line {
                            append_log_line(path_clone.clone(), &format!("[stderr] {}", l));
                        }
                    }
                });
            }

            let pid = child.id();
            {
                let mut process_guard = state.backend_process.lock().unwrap();
                *process_guard = Some(child);
            }

            // 等待后端就绪（GPU 冷启动可能较慢）
            if wait_for_backend_ready(host, port, ready_wait_secs).await {
                println!("[backend] 已就绪：http://{}:{}", host, port);
                let _ = tauri_plugin_notification::NotificationExt::notification(&app_handle)
                    .builder()
                    .title("AI智能视频剪辑")
                    .body("后端服务启动成功")
                    .show();

                Ok(backend_ready_status(
                    &app_handle,
                    port,
                    Some(pid),
                    Some(boot_token),
                ))
            } else {
                // 超时未就绪，尝试从日志解析实际监听端口
                if let Some(found_port) = parse_backend_port_from_log() {
                    *state.backend_port.lock().unwrap() = found_port;
                    println!(
                        "[backend] 从日志解析到监听端口：http://{}:{}",
                        host, found_port
                    );
                    Ok(backend_ready_status(
                        &app_handle,
                        found_port,
                        Some(pid),
                        state.backend_boot_token.lock().unwrap().clone(),
                    ))
                } else {
                    if let Some((found_port, found_token)) =
                        discover_existing_backend_quick(host, !is_dev_mode).await
                    {
                        *state.backend_port.lock().unwrap() = found_port;
                        *state.backend_boot_token.lock().unwrap() = found_token.clone();
                        println!(
                            "[backend] 已发现运行中的后端：http://{}:{}",
                            host, found_port
                        );
                        Ok(backend_ready_status(
                            &app_handle,
                            found_port,
                            Some(pid),
                            found_token,
                        ))
                    } else {
                        // 未发现已就绪端口，保留已启动的进程，返回错误以提示检查日志，但不杀进程
                        Err("后端服务启动超时，但进程已保留；请查看临时日志 super_auto_cut_backend.log".to_string())
                    }
                }
            }
        }
        Err(e) => {
            *state.backend_port.lock().unwrap() = 0;
            *state.backend_boot_token.lock().unwrap() = None;
            let path = std::env::temp_dir().join("super_auto_cut_backend.log");
            append_log_line(
                path,
                &format!("[error] spawn_failed: {}", e),
            );
            Err(format!("启动后端失败: {}", e))
        }
    }
}

/// 停止后端并释放 AppData 下 DLL 文件锁（覆盖后端目录前必须调用，否则 Windows 报 os error 32）。
fn stop_backend_sync(state: &AppState) -> Result<bool, String> {
    state.backend_starting.store(false, Ordering::SeqCst);
    let mut process_guard = state.backend_process.lock().unwrap();

    if let Some(mut child) = process_guard.take() {
        let pid = child.id();
        match child.kill() {
            Ok(_) => {
                let _ = child.wait(); // 等待进程完全退出
                *state.backend_port.lock().unwrap() = 0;
                *state.backend_boot_token.lock().unwrap() = None;
                println!("[backend] 已停止 (pid={})", pid);
                #[cfg(target_os = "windows")]
                {
                    kill_all_backend_processes();
                }
                Ok(true)
            }
            Err(e) => Err(format!("停止后端失败: {}", e)),
        }
    } else {
        #[cfg(target_os = "windows")]
        {
            kill_all_backend_processes();
        }
        Ok(false)
    }
}

// Tauri命令：停止Python后端
#[tauri::command]
async fn stop_backend(state: State<'_, AppState>) -> Result<bool, String> {
    stop_backend_sync(&state)
}

/// 取出 Rust 侧缓存的 backend-ready（仅消费一次，用于弥补前端 listen 注册前的竞态）
#[tauri::command]
fn take_pending_backend_ready(state: State<'_, AppState>) -> Option<BackendReadyPayload> {
    state.pending_backend_ready.lock().unwrap().take()
}

/// 由 Rust 直接探测 HTTP（不依赖 WebView fetch），供首屏 loading 轮询
#[tauri::command]
async fn probe_backend_http_ready(state: State<'_, AppState>) -> Result<BackendStatus, String> {
    let host = "127.0.0.1";
    let port = *state.backend_port.lock().unwrap();
    let boot_token = state.backend_boot_token.lock().unwrap().clone();
    if port != 0 && probe_backend_ready(host, port).await {
        return Ok(BackendStatus {
            running: true,
            port,
            pid: None,
            boot_token,
        });
    }
    for p in [18000u16, 8000u16] {
        if probe_backend_ready(host, p).await {
            *state.backend_port.lock().unwrap() = p;
            return Ok(BackendStatus {
                running: true,
                port: p,
                pid: None,
                boot_token: state.backend_boot_token.lock().unwrap().clone(),
            });
        }
    }
    for p in 18001u16..=18100 {
        if probe_backend_ready(host, p).await {
            *state.backend_port.lock().unwrap() = p;
            return Ok(BackendStatus {
                running: true,
                port: p,
                pid: None,
                boot_token: state.backend_boot_token.lock().unwrap().clone(),
            });
        }
    }
    for p in 8001u16..=8100 {
        if probe_backend_ready(host, p).await {
            *state.backend_port.lock().unwrap() = p;
            return Ok(BackendStatus {
                running: true,
                port: p,
                pid: None,
                boot_token: state.backend_boot_token.lock().unwrap().clone(),
            });
        }
    }
    Ok(BackendStatus {
        running: false,
        port: 0,
        pid: None,
        boot_token: None,
    })
}

// Tauri命令：获取后端状态
#[tauri::command]
async fn get_backend_status(state: State<'_, AppState>) -> Result<BackendStatus, String> {
    let host = "127.0.0.1";
    let snapshot = {
        let mut process_guard = state.backend_process.lock().unwrap();
        if let Some(ref mut child) = *process_guard {
            match child.try_wait() {
                Ok(Some(_)) => {
                    *process_guard = None;
                    *state.backend_port.lock().unwrap() = 0;
                    *state.backend_boot_token.lock().unwrap() = None;
                    None
                }
                Ok(None) => Some((
                    *state.backend_port.lock().unwrap(),
                    state.backend_boot_token.lock().unwrap().clone(),
                    Some(child.id()),
                )),
                Err(e) => return Err(format!("检查进程状态失败: {}", e)),
            }
        } else {
            Some((
                *state.backend_port.lock().unwrap(),
                state.backend_boot_token.lock().unwrap().clone(),
                None,
            ))
        }
    };

    let Some((port, boot_token, pid)) = snapshot else {
        return Ok(BackendStatus {
            running: false,
            port: 0,
            pid: None,
            boot_token: None,
        });
    };

    let http_ready = port != 0 && probe_backend_ready(host, port).await;
    Ok(BackendStatus {
        running: http_ready,
        port,
        pid,
        boot_token,
    })
}

// Tauri命令：检查后端资源是否已复制/解压到resources
#[tauri::command]
fn get_backend_resource_status(app_handle: AppHandle) -> Result<BackendResourceStatus, String> {
    Ok(inspect_backend_resource_status(&app_handle))
}

// Tauri命令：选择视频文件
#[tauri::command]
async fn select_video_file(app: AppHandle) -> Result<FileSelection, String> {
    let file_path = tauri_plugin_dialog::DialogExt::dialog(&app)
        .file()
        .add_filter("视频文件", &["mp4", "avi", "mov", "mkv", "wmv", "flv"])
        .set_title("选择视频文件")
        .blocking_pick_file();

    match file_path {
        Some(path) => Ok(FileSelection {
            path: Some(path.to_string()),
            cancelled: false,
        }),
        None => Ok(FileSelection {
            path: None,
            cancelled: true,
        }),
    }
}

// Tauri命令：选择输出目录
#[tauri::command]
async fn select_output_directory(app: AppHandle) -> Result<FileSelection, String> {
    let dir_path = tauri_plugin_dialog::DialogExt::dialog(&app)
        .file()
        .set_title("选择输出目录")
        .blocking_pick_folder();

    match dir_path {
        Some(path) => Ok(FileSelection {
            path: Some(path.to_string()),
            cancelled: false,
        }),
        None => Ok(FileSelection {
            path: None,
            cancelled: true,
        }),
    }
}

// Tauri命令：选择离线更新总清单 offline-bundle-manifest.json
#[tauri::command]
async fn select_offline_bundle_manifest(app: AppHandle) -> Result<FileSelection, String> {
    let file_path = tauri_plugin_dialog::DialogExt::dialog(&app)
        .file()
        .add_filter("offline-bundle-manifest", &["json"])
        .set_title("选择 offline-bundle-manifest.json")
        .blocking_pick_file();

    match file_path {
        Some(path) => Ok(FileSelection {
            path: Some(path.to_string()),
            cancelled: false,
        }),
        None => Ok(FileSelection {
            path: None,
            cancelled: true,
        }),
    }
}

// Tauri命令：获取应用信息
#[tauri::command]
async fn get_app_info(app_handle: AppHandle) -> Result<HashMap<String, String>, String> {
    let mut info = HashMap::new();
    let pkg = app_handle.package_info();
    let version = pkg.version.to_string();
    info.insert("name".to_string(), "AI智能视频剪辑".to_string());
    info.insert("version".to_string(), version);
    info.insert(
        "description".to_string(),
        "基于AI技术的智能视频剪辑工具".to_string(),
    );
    Ok(info)
}

// Tauri命令：显示通知
#[tauri::command]
async fn show_notification(
    app_handle: AppHandle,
    title: String,
    body: String,
) -> Result<(), String> {
    tauri_plugin_notification::NotificationExt::notification(&app_handle)
        .builder()
        .title(&title)
        .body(&body)
        .show()
        .map_err(|e| format!("显示通知失败: {}", e))?;
    Ok(())
}

// Tauri命令：打开外部链接
#[tauri::command]
async fn open_external_link(app: AppHandle, url: String) -> Result<(), String> {
    tauri_plugin_opener::OpenerExt::opener(&app)
        .open_url(url, None::<String>)
        .map_err(|e| format!("打开链接失败: {}", e))
}

#[tauri::command]
async fn minimize_main_window(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    window.minimize().map_err(|e| format!("最小化窗口失败: {}", e))
}

#[tauri::command]
async fn start_dragging_main_window(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    window
        .start_dragging()
        .map_err(|e| format!("拖动窗口失败: {}", e))
}

#[tauri::command]
async fn toggle_maximize_main_window(app: AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    let is_maximized = window
        .is_maximized()
        .map_err(|e| format!("读取窗口最大化状态失败: {}", e))?;
    if is_maximized {
        window
            .unmaximize()
            .map_err(|e| format!("还原窗口失败: {}", e))?;
        Ok(false)
    } else {
        window
            .maximize()
            .map_err(|e| format!("最大化窗口失败: {}", e))?;
        Ok(true)
    }
}

#[tauri::command]
async fn is_main_window_maximized(app: AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    window
        .is_maximized()
        .map_err(|e| format!("读取窗口最大化状态失败: {}", e))
}

/// 设置主窗口内边尺寸（逻辑像素），可选居中。用于启动页小窗与主界面大窗切换。
#[tauri::command]
async fn set_main_window_size(
    app: AppHandle,
    width: f64,
    height: f64,
    center: bool,
) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    if window
        .is_maximized()
        .map_err(|e| format!("读取窗口最大化状态失败: {}", e))?
    {
        window
            .unmaximize()
            .map_err(|e| format!("还原窗口失败: {}", e))?;
    }
    window
        .set_size(tauri::LogicalSize::new(width, height))
        .map_err(|e| format!("调整窗口大小失败: {}", e))?;
    if center {
        window
            .center()
            .map_err(|e| format!("居中窗口失败: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
async fn close_main_window(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;

    window.hide().map_err(|e| format!("隐藏窗口失败: {}", e))?;

    let _ = tauri_plugin_notification::NotificationExt::notification(&app)
        .builder()
        .title("SuperAI 影视剪辑")
        .body("应用已最小化到系统托盘，可在右下角托盘中恢复或退出")
        .show();

    Ok(())
}

// ── 运行时分块更新 Tauri 命令 ──────────────────────────────────────

#[tauri::command]
async fn check_runtime_update(
    app_handle: AppHandle,
) -> Result<runtime_updater::RuntimeUpdateInfo, String> {
    runtime_updater::check_update(&app_handle).await
}

#[tauri::command]
async fn download_runtime_update(
    app_handle: AppHandle,
    state: State<'_, AppState>,
) -> Result<runtime_updater::RuntimeUpdateInfo, String> {
    let _ = stop_backend_sync(&state)?;
    #[cfg(target_os = "windows")]
    std::thread::sleep(std::time::Duration::from_millis(400));
    runtime_updater::download_and_apply(&app_handle).await
}

#[tauri::command]
async fn get_runtime_installed_state(
    app_handle: AppHandle,
) -> Result<runtime_updater::InstalledState, String> {
    runtime_updater::get_installed_info(&app_handle).await
}

#[tauri::command]
fn check_local_runtime_update(
    app_handle: AppHandle,
    manifest_path: String,
) -> Result<runtime_updater::RuntimeUpdateInfo, String> {
    runtime_updater::check_local_update(&app_handle, &manifest_path)
}

#[tauri::command]
async fn apply_local_runtime_update(
    app_handle: AppHandle,
    state: State<'_, AppState>,
    manifest_path: String,
) -> Result<runtime_updater::RuntimeUpdateInfo, String> {
    let _ = stop_backend_sync(&state)?;
    #[cfg(target_os = "windows")]
    std::thread::sleep(std::time::Duration::from_millis(400));
    let app_handle = app_handle.clone();
    tokio::task::spawn_blocking(move || runtime_updater::apply_local_update(&app_handle, &manifest_path))
        .await
        .map_err(|e| format!("本地运行时更新任务异常: {}", e))?
}

#[tauri::command]
fn resolve_offline_update_bundle(
    selected_path: String,
) -> Result<offline_bundle::OfflineBundleResolved, String> {
    offline_bundle::resolve_offline_update_bundle(selected_path)
}

#[tauri::command]
fn launch_local_shell_installer(installer_path: String) -> Result<(), String> {
    offline_bundle::launch_local_shell_installer(installer_path)
}

// 应用启动时的初始化
fn setup_app(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let show_item = MenuItem::with_id(app, "tray_show", "显示主窗口", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "tray_quit", "退出", true, None::<&str>)?;
    let tray_menu = Menu::with_items(app, &[&show_item, &quit_item])?;

    let tray_icon = app
        .default_window_icon()
        .cloned()
        .ok_or("缺少默认窗口图标，无法创建系统托盘图标")?;

    TrayIconBuilder::with_id("main-tray")
        .icon(Image::from(tray_icon))
        .tooltip("SuperAI 影视剪辑")
        .menu(&tray_menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    // 若未由配置自动创建窗口，则显式创建主窗口
    if app.get_webview_window("main").is_none() {
        #[cfg(target_os = "windows")]
        let window_builder =
            tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
                .title("AI智能视频剪辑")
                .resizable(true)
                .decorations(false)
                .shadow(false)
                .transparent(true)
                .inner_size(800.0, 350.0)
                .center();

        #[cfg(not(target_os = "windows"))]
        let window_builder =
            tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
                .title("AI智能视频剪辑")
                .resizable(true)
                .decorations(false)
                .shadow(false)
                .inner_size(800.0, 350.0)
                .center();

        window_builder.build()?;
    }

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.center();
    }

    if std::env::var("SACV_DISABLE_SETUP_AUTO_START_BACKEND")
        .ok()
        .as_deref()
        == Some("1")
    {
        println!("[backend] setup 阶段自动启动已禁用（SACV_DISABLE_SETUP_AUTO_START_BACKEND=1）");
    } else {
        let app_handle = app.handle().clone();
        tauri::async_runtime::spawn(async move {
            // Give the WebView a brief chance to register event listeners first. If the
            // frontend invoke path fails, this delayed fallback still starts the backend.
            tokio::time::sleep(Duration::from_millis(1500)).await;
            let state = app_handle.state::<AppState>();
            match start_backend(state, app_handle.clone()).await {
                Ok(status) => {
                    if status.running && status.port != 0 {
                        println!("[backend] setup 延迟自动启动完成：http://127.0.0.1:{}", status.port);
                    }
                }
                Err(e) => {
                    eprintln!("[backend] setup 延迟自动启动失败: {}", e);
                }
            }
        });
    }

    Ok(())
}

// 应用退出时的清理
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .manage(AppState::default())
        .setup(setup_app)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "tray_show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "tray_quit" => {
                let state = app.state::<AppState>();
                state.app_is_quitting.store(true, Ordering::SeqCst);
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.close();
                } else {
                    app.exit(0);
                }
            }
            _ => {}
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let state = app.state::<AppState>();
                if state.app_is_quitting.load(Ordering::SeqCst) {
                    return;
                }
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            start_backend,
            stop_backend,
            get_backend_status,
            take_pending_backend_ready,
            probe_backend_http_ready,
            get_backend_resource_status,
            select_video_file,
            select_output_directory,
            select_offline_bundle_manifest,
            get_app_info,
            show_notification,
            open_external_link,
            minimize_main_window,
            start_dragging_main_window,
            toggle_maximize_main_window,
            is_main_window_maximized,
            set_main_window_size,
            close_main_window,
            check_runtime_update,
            download_runtime_update,
            get_runtime_installed_state,
            check_local_runtime_update,
            apply_local_runtime_update,
            resolve_offline_update_bundle,
            launch_local_shell_installer
        ])
        .build(tauri::generate_context!())
        .expect("启动Tauri应用失败")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app.state::<AppState>();
                let _ = stop_backend_sync(&*state);
            }
        });
}
