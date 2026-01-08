// AI智能视频剪辑桌面应用 - Tauri Rust桥接层
// 负责启动Python后端、文件系统访问和前后端通信桥接

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::collections::HashMap;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::net::TcpListener;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

// Windows: 隐藏子进程窗口（CREATE_NO_WINDOW）
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

// 应用状态结构
#[derive(Default)]
struct AppState {
    backend_process: Arc<Mutex<Option<Child>>>,
    backend_port: Arc<Mutex<u16>>,
}

// 后端状态响应
#[derive(Serialize, Deserialize, Debug)
]
struct BackendStatus {
    running: bool,
    port: u16,
    pid: Option<u32>,
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
        .timeout(Duration::from_millis(1200))
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

fn choose_available_port(preferred: u16) -> u16 {
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
    // 兜底返回首选端口（可能被占用，后续就绪检测会失败并反馈日志）
    preferred
}


// Tauri命令：启动Python后端
#[tauri::command]
async fn start_backend(
    state: State<'_, AppState>,
    app_handle: AppHandle,
) -> Result<BackendStatus, String> {
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
                    return Ok(BackendStatus {
                        running: true,
                        port,
                        pid: Some(child.id()),
                    });
                }
                Err(_) => {
                    // 检查失败，清理
                    *process_guard = None;
                }
            }
        }
    }

    // 获取资源目录路径（并准备后备路径：与应用同级 resources 目录）
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .map_err(|e| format!("无法获取资源目录: {}", e))?;
    let exe_dir_fallback = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()));

    let is_dev_mode = cfg!(debug_assertions) || std::env::var("TAURI_DEV").ok().as_deref() == Some("1");
    let force_packaged_backend = std::env::var("FORCE_PACKAGED_BACKEND").ok().as_deref() == Some("1");
    let prefer_python_backend = is_dev_mode && !force_packaged_backend;

    // 尝试定位打包的后端可执行文件
    let primary_path = if cfg!(target_os = "windows") {
        resource_dir.join("superAutoCutVideoBackend.exe")
    } else {
        resource_dir.join("superAutoCutVideoBackend")
    };
    let fallback_path = exe_dir_fallback.as_ref().map(|dir| {
        if cfg!(target_os = "windows") {
            dir.join("resources").join("superAutoCutVideoBackend.exe")
        } else {
            dir.join("resources").join("superAutoCutVideoBackend")
        }
    });

    let backend_executable = if primary_path.exists() {
        primary_path
    } else if let Some(fp) = &fallback_path { fp.clone() } else { primary_path };

    let mut cmd = if !prefer_python_backend && backend_executable.exists() {
        // 使用打包的可执行文件
        println!("使用打包的后端可执行文件: {:?}", backend_executable);
        let mut c = Command::new(backend_executable);
        #[cfg(target_os = "windows")]
        { c.creation_flags(CREATE_NO_WINDOW); }
        c
    } else {
        // 未发现打包的后端
        // 生产环境严格要求存在打包后端；开发环境允许回退到 Python
        if is_dev_mode {
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

            let backend_script = backend_script.ok_or_else(|| "后端脚本不存在: backend/main.py".to_string())?;

            if !backend_script.exists() {
                return Err(format!("后端脚本不存在: {:?}", backend_script));
            }

            println!("开发模式：使用Python运行后端脚本: {:?}", backend_script);

            // 优先选择 workspace backend/.venv 下的解释器；其次尝试 python3；最后回退到 python
            let backend_dir = backend_script.parent().unwrap().to_path_buf();
            let venv_py_unix = backend_dir.join(".venv").join("bin").join("python3");
            let venv_py_unix_alt = backend_dir.join(".venv").join("bin").join("python");
            let venv_py_win = backend_dir.join(".venv").join("Scripts").join("python.exe");

            // 允许通过环境变量强制指定解释器
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

            println!("选择的 Python 解释器: {}", python_cmd);

            let mut c = Command::new(python_cmd);
            c.arg(backend_script);
            #[cfg(target_os = "windows")]
            { c.creation_flags(CREATE_NO_WINDOW); }
            c.current_dir(backend_dir);

            c
        } else {
            return Err("未找到打包的后端可执行文件，请检查打包配置 bundle.resources".to_string());
        }
    };

    // 设置环境变量
    let host = "127.0.0.1";
    let port: u16 = choose_available_port(8000);
    cmd.env("HOST", host)
        .env("PORT", port.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // 启动进程
    match cmd.spawn() {
        Ok(mut child) => {
            // 捕获日志到临时文件
            let log_path = std::env::temp_dir().join("super_auto_cut_backend.log");
            let _ = std::fs::OpenOptions::new()
                .create(true)
                .truncate(true)
                .write(true)
                .open(&log_path);
            if let Some(stdout) = child.stdout.take() {
                let path_clone = log_path.clone();
                thread::spawn(move || {
                    let reader = BufReader::new(stdout);
                    for line in reader.lines() {
                        if let Ok(l) = line { append_log_line(path_clone.clone(), &format!("[stdout] {}", l)); }
                    }
                });
            }
            if let Some(stderr) = child.stderr.take() {
                let path_clone = log_path.clone();
                thread::spawn(move || {
                    let reader = BufReader::new(stderr);
                    for line in reader.lines() {
                        if let Ok(l) = line { append_log_line(path_clone.clone(), &format!("[stderr] {}", l)); }
                    }
                });
            }

            let pid = child.id();
            {
                let mut process_guard = state.backend_process.lock().unwrap();
                *process_guard = Some(child);
            }
            *state.backend_port.lock().unwrap() = port;

            // 等待后端就绪（最多 20 秒，避免首次解压或冷启动偏慢）
            if wait_for_backend_ready(host, port, 20).await {
                let _ = tauri_plugin_notification::NotificationExt::notification(&app_handle)
                    .builder()
                    .title("AI智能视频剪辑")
                    .body("后端服务启动成功")
                    .show();

                Ok(BackendStatus {
                    running: true,
                    port,
                    pid: Some(pid),
                })
            } else {
                // 超时未就绪，停止进程
                if let Some(mut child_ref) = state.backend_process.lock().unwrap().take() {
                    let _ = child_ref.kill();
                    let _ = child_ref.wait();
                }
                Err("后端服务启动超时，请查看临时日志 super_auto_cut_backend.log".to_string())
            }
        }
        Err(e) => Err(format!("启动后端失败: {}", e)),
    }
}

// Tauri命令：停止Python后端
#[tauri::command]
async fn stop_backend(state: State<'_, AppState>) -> Result<bool, String> {
    let mut process_guard = state.backend_process.lock().unwrap();
    
    if let Some(mut child) = process_guard.take() {
        match child.kill() {
            Ok(_) => {
                let _ = child.wait(); // 等待进程完全退出
                Ok(true)
            }
            Err(e) => Err(format!("停止后端失败: {}", e)),
        }
    } else {
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
                })
            }
            Ok(None) => {
                // 进程仍在运行
                let port = *state.backend_port.lock().unwrap();
                Ok(BackendStatus {
                    running: true,
                    port,
                    pid: Some(child.id()),
                })
            }
            Err(e) => Err(format!("检查进程状态失败: {}", e)),
        }
    } else {
        Ok(BackendStatus {
            running: false,
            port: 0,
            pid: None,
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
    info.insert("description".to_string(), "基于AI技术的智能视频剪辑工具".to_string());
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
    let app_handle = app.handle();

    // 若未由配置自动创建窗口，则显式创建主窗口
    if app.get_webview_window("main").is_none() {
        tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::default())
            .title("AI智能视频剪辑")
            .resizable(true)
            .inner_size(1200.0, 800.0)
            .center()
            .build()?;
    }

    // 在后台线程中自动启动后端
    let app_handle_clone = app_handle.clone();
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(1)); // 等待应用完全启动

        let state = app_handle_clone.state::<AppState>();
        let rt = tokio::runtime::Runtime::new().unwrap();

        match rt.block_on(start_backend(state, app_handle_clone.clone())) {
            Ok(status) => {
                println!("后端自动启动成功: {:?}", status);
            }
            Err(e) => {
                eprintln!("后端自动启动失败: {}", e);
            }
        }
    });

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
