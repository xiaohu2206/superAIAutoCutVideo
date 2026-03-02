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
use tauri::{AppHandle, Manager, State};
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

// 应用状态结构
struct AppState {
    backend_process: Arc<Mutex<Option<Child>>>,
    backend_port: Arc<Mutex<u16>>,
    backend_starting: Arc<AtomicBool>,
    backend_boot_token: Arc<Mutex<Option<String>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            backend_process: Arc::new(Mutex::new(None)),
            backend_port: Arc::new(Mutex::new(0)),
            backend_starting: Arc::new(AtomicBool::new(false)),
            backend_boot_token: Arc::new(Mutex::new(None)),
        }
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

// 文件选择结果
#[derive(Serialize, Deserialize)]
struct FileSelection {
    path: Option<String>,
    cancelled: bool,
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
fn ensure_backend_executable_available(
    _app_handle: &AppHandle,
    resource_dir: &PathBuf,
) -> Result<PathBuf, String> {
    let app_data_dir = _app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("无法获取应用数据目录: {}", e))?;
    let extracted_backend_dir = app_data_dir.join("superAutoCutVideoBackend");
    let nested_backend_dir = extracted_backend_dir.join("superAutoCutVideoBackend");
    let zip_path = resource_dir.join("superAutoCutVideoBackend.zip");
    let stamp_path = extracted_backend_dir.join(".backend_zip_stamp");
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

    let zip_stamp = || -> Option<String> {
        let mt = std::fs::metadata(&zip_path).ok()?.modified().ok()?;
        let d = mt.duration_since(std::time::UNIX_EPOCH).ok()?;
        Some(format!("{}.{}", d.as_secs(), d.subsec_nanos()))
    };
    let read_stamp = || -> Option<String> {
        std::fs::read_to_string(&stamp_path).ok().map(|s| s.trim().to_string())
    };
    let should_refresh = || -> bool {
        if !zip_path.exists() {
            return false;
        }
        let want = match zip_stamp() {
            Some(v) => v,
            None => return false,
        };
        match read_stamp() {
            Some(got) if got == want => false,
            _ => true,
        }
    };

    if let Some(exe) = is_valid_backend_root(&extracted_backend_dir) {
        if !should_refresh() {
            return Ok(exe);
        }
    }
    if let Some(exe) = is_valid_backend_root(&nested_backend_dir) {
        if !should_refresh() {
            return Ok(exe);
        }
    }
    if extracted_backend_dir.exists() {
        let _ = std::fs::remove_dir_all(&extracted_backend_dir);
    }
    if !zip_path.exists() {
        return Ok(extracted_backend_dir.join("superAutoCutVideoBackend.exe"));
    }

    let _ = std::fs::create_dir_all(&app_data_dir);
    if extracted_backend_dir.exists() {
        let _ = std::fs::remove_dir_all(&extracted_backend_dir);
    }
    let _ = std::fs::create_dir_all(&extracted_backend_dir);

    let mut zip_extract_ok = false;
    if let Ok(file) = std::fs::File::open(&zip_path) {
        if let Ok(mut zip) = ZipArchive::new(file) {
            if zip.extract(&extracted_backend_dir).is_ok() {
                zip_extract_ok = true;
            }
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
    }
    if let Some(stamp) = zip_stamp() {
        let _ = std::fs::write(&stamp_path, stamp);
    }

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
    // 先短暂持锁检查和清理状态，避免并发重复启动
    {
        let mut process_guard = state.backend_process.lock().unwrap();
        if let Some(ref mut child) = *process_guard {
            match child.try_wait() {
                Ok(Some(_)) => {
                    // 进程已退出，清理
                    *process_guard = None;
                }
                Ok(None) => {
                    // 进程仍在运行
                    let port = *state.backend_port.lock().unwrap();
                    let boot_token = state.backend_boot_token.lock().unwrap().clone();
                    println!(
                        "[backend] 已在运行：http://127.0.0.1:{} (pid={})",
                        port,
                        child.id()
                    );
                    return Ok(BackendStatus {
                        running: true,
                        port,
                        pid: Some(child.id()),
                        boot_token,
                    });
                }
                Err(_) => {
                    // 检查失败，清理
                    *process_guard = None;
                }
            }
        }
    }

    let host = "127.0.0.1";
    let is_dev_mode = std::env::var("TAURI_DEV").ok().as_deref() == Some("1");
    let forced_port_opt = std::env::var("SACV_FORCE_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .filter(|p| *p > 0);
    if is_dev_mode && forced_port_opt.is_none() {
        if let Some((p, boot_token)) = discover_existing_backend(host, false).await {
            *state.backend_port.lock().unwrap() = p;
            *state.backend_boot_token.lock().unwrap() = boot_token.clone();
            println!("[backend] 已发现运行中的后端：http://{}:{}", host, p);
            return Ok(BackendStatus {
                running: true,
                port: p,
                pid: None,
                boot_token,
            });
        }
    }
    // 生产环境也尝试发现已运行的后端，避免重复启动
    if !is_dev_mode && forced_port_opt.is_none() {
        if let Some((p, boot_token)) = discover_existing_backend_quick(host, true).await {
            *state.backend_port.lock().unwrap() = p;
            *state.backend_boot_token.lock().unwrap() = boot_token.clone();
            println!("[backend] 已发现运行中的后端：http://{}:{}", host, p);
            return Ok(BackendStatus {
                running: true,
                port: p,
                pid: None,
                boot_token,
            });
        }
    }

    // 获取资源目录路径（并准备后备路径：与应用同级 resources 目录）
    let resource_dir = match app_handle.path().resource_dir() {
        Ok(p) => p,
        Err(_e) => {
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
    let backend_folder_exe = resource_root
        .join("superAutoCutVideoBackend")
        .join("superAutoCutVideoBackend.exe");
    let backend_folder_exists = backend_folder_exe.exists();
    let prefer_python_backend =
        is_dev_mode && !force_packaged_backend && !backend_zip_exists && !backend_folder_exists;

    append_log_line(
        early_log_path.clone(),
        &format!(
            "[meta] is_dev_mode={} prefer_python_backend={} resource_dir={} resource_root={} backend_zip_exists={}",
            is_dev_mode,
            prefer_python_backend,
            resource_dir.to_string_lossy(),
            resource_root.to_string_lossy(),
            backend_zip_exists
        ),
    );

    #[cfg(target_os = "windows")]
    let extracted_backend_exe = if !prefer_python_backend && backend_zip_exists && !backend_folder_exists {
        let zip_path = resource_root.join("superAutoCutVideoBackend.zip");
        if let Ok(app_data_dir) = app_handle.path().app_data_dir() {
            append_log_line(
                early_log_path.clone(),
                &format!("[meta] app_data_dir={}", app_data_dir.to_string_lossy()),
            );
        }
        append_log_line(
            early_log_path.clone(),
            &format!(
                "[meta] backend_zip_exists={} backend_zip_path={}",
                zip_path.exists(),
                zip_path.to_string_lossy()
            ),
        );
        append_log_line(early_log_path.clone(), "[meta] ensure_backend_executable_available_begin");
        match ensure_backend_executable_available(&app_handle, &resource_root) {
            Ok(p) => {
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
            Err(e) => {
                append_log_line(
                    early_log_path.clone(),
                    &format!("[meta] ensure_backend_executable_available_error={}", e),
                );
                return Err(e);
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
        return Err(err);
    };

    // 并发启动防护：若已有启动流程进行中，则不再重复启动
    if state.backend_starting.swap(true, Ordering::SeqCst) {
        tokio::time::sleep(Duration::from_millis(300)).await;
        let port = *state.backend_port.lock().unwrap();
        let boot_token = state.backend_boot_token.lock().unwrap().clone();
        if port != 0 {
            println!(
                "[backend] 启动中（复用已有启动流程）：http://{}:{}",
                host, port
            );
        }
        return Ok(BackendStatus {
            running: port != 0,
            port,
            pid: None,
            boot_token,
        });
    }

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
            state.backend_starting.store(false, Ordering::SeqCst);

            // 等待后端就绪（最多 60 秒，避免首次解压或冷启动偏慢）
            if wait_for_backend_ready(host, port, 60).await {
                println!("[backend] 已就绪：http://{}:{}", host, port);
                let _ = tauri_plugin_notification::NotificationExt::notification(&app_handle)
                    .builder()
                    .title("AI智能视频剪辑")
                    .body("后端服务启动成功")
                    .show();

                Ok(BackendStatus {
                    running: true,
                    port,
                    pid: Some(pid),
                    boot_token: Some(boot_token),
                })
            } else {
                // 超时未就绪，尝试从日志解析实际监听端口
                if let Some(found_port) = parse_backend_port_from_log() {
                    *state.backend_port.lock().unwrap() = found_port;
                    println!(
                        "[backend] 从日志解析到监听端口：http://{}:{}",
                        host, found_port
                    );
                    Ok(BackendStatus {
                        running: true,
                        port: found_port,
                        pid: Some(pid),
                        boot_token: state.backend_boot_token.lock().unwrap().clone(),
                    })
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
                        Ok(BackendStatus {
                            running: true,
                            port: found_port,
                            pid: Some(pid),
                            boot_token: found_token,
                        })
                    } else {
                        // 未发现已就绪端口，保留已启动的进程，返回错误以提示检查日志，但不杀进程
                        Err("后端服务启动超时，但进程已保留；请查看临时日志 super_auto_cut_backend.log".to_string())
                    }
                }
            }
        }
        Err(e) => {
            state.backend_starting.store(false, Ordering::SeqCst);
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

// Tauri命令：停止Python后端
#[tauri::command]
async fn stop_backend(state: State<'_, AppState>) -> Result<bool, String> {
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
                    // 额外兜底：强制结束所有同名后端进程，避免残留
                    kill_all_backend_processes();
                }
                Ok(true)
            }
            Err(e) => Err(format!("停止后端失败: {}", e)),
        }
    } else {
        #[cfg(target_os = "windows")]
        {
            // 无记录的子进程，但可能仍有残留后端，兜底清理
            kill_all_backend_processes();
        }
        Ok(false) // 没有运行的进程
    }
}

// Tauri命令：获取后端状态
#[tauri::command]
async fn get_backend_status(state: State<'_, AppState>) -> Result<BackendStatus, String> {
    let mut process_guard = state.backend_process.lock().unwrap();

    if let Some(ref mut child) = *process_guard {
        match child.try_wait() {
            Ok(Some(_)) => {
                // 进程已退出
                *process_guard = None;
                Ok(BackendStatus {
                    running: false,
                    port: 0,
                    pid: None,
                    boot_token: None,
                })
            }
            Ok(None) => {
                // 进程仍在运行
                let port = *state.backend_port.lock().unwrap();
                Ok(BackendStatus {
                    running: true,
                    port,
                    pid: Some(child.id()),
                    boot_token: state.backend_boot_token.lock().unwrap().clone(),
                })
            }
            Err(e) => Err(format!("检查进程状态失败: {}", e)),
        }
    } else {
        Ok(BackendStatus {
            running: false,
            port: 0,
            pid: None,
            boot_token: None,
        })
    }
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

// 应用启动时的初始化
fn setup_app(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    // 若未由配置自动创建窗口，则显式创建主窗口
    if app.get_webview_window("main").is_none() {
        tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
            .title("AI智能视频剪辑")
            .resizable(true)
            .inner_size(1200.0, 800.0)
            .center()
            .build()?;
    }

    {
        let app_handle = app.handle().clone();
        tauri::async_runtime::spawn(async move {
            let state = app_handle.state::<AppState>();
            match start_backend(state, app_handle.clone()).await {
                Ok(status) => {
                    if status.running && status.port != 0 {
                        println!("[backend] 自动启动完成：http://127.0.0.1:{}", status.port);
                    }
                }
                Err(e) => {
                    eprintln!("[backend] 自动启动失败: {}", e);
                }
            }
        });
    }

    Ok(())
}

// 应用退出时的清理
fn cleanup_app(app_handle: AppHandle) {
    let state = app_handle.state::<AppState>();
    let rt = tokio::runtime::Runtime::new().unwrap();

    if let Err(e) = rt.block_on(stop_backend(state)) {
        eprintln!("清理后端进程失败: {}", e);
    }
}

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
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .manage(AppState::default())
        .setup(setup_app)
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                cleanup_app(window.app_handle().clone());
            }
        })
        .invoke_handler(tauri::generate_handler![
            start_backend,
            stop_backend,
            get_backend_status,
            select_video_file,
            select_output_directory,
            get_app_info,
            show_notification,
            open_external_link
        ])
        .run(tauri::generate_context!())
        .expect("启动Tauri应用失败");
}
