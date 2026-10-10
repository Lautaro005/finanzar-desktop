//! Biblioteca de FinanzAR Desktop (shell Tauri 2).
//!
//! Rust crea la ventana, arranca y detiene el sidecar del backend Python,
//! expone comandos seguros al frontend y coordina el updater firmado.

pub mod commands;
pub mod paths;
pub mod sidecar;
pub mod updater;

use std::time::{Duration, Instant};

use commands::AppState;
use sidecar::Backend;
use tauri::{Emitter, Manager};

/// Espera a que el backend responda en `/health`.
async fn wait_for_backend(base_url: &str, timeout: Duration) -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
    {
        Ok(client) => client,
        Err(_) => return false,
    };
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Ok(response) = client.get(format!("{base_url}/health")).send().await {
            if response.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(400)).await;
    }
    false
}

fn set_base_url(app: &tauri::AppHandle, base_url: String) {
    let state = app.state::<AppState>();
    let lock = state.base_url.lock();
    if let Ok(mut guard) = lock {
        *guard = Some(base_url);
    }
}

/// Arranca un backend gestionado por Rust y avisa cuando está listo.
fn spawn_managed_backend(app: &tauri::AppHandle) {
    let data_dir = paths::data_dir(app);
    let repo_root = paths::repo_root();
    match Backend::spawn(app, &data_dir, repo_root.as_deref()) {
        Ok(backend) => {
            let base_url = backend.base_url.clone();
            let state = app.state::<AppState>();
            let backend_lock = state.backend.lock();
            if let Ok(mut guard) = backend_lock {
                *guard = Some(backend);
            }
            set_base_url(app, base_url.clone());
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                let ready = wait_for_backend(&base_url, Duration::from_secs(120)).await;
                let _ = app_clone.emit(
                    "backend://ready",
                    serde_json::json!({ "ready": ready, "baseUrl": base_url }),
                );
                log::info!("Backend listo: {ready}");
            });
        }
        Err(err) => {
            log::error!("No se pudo iniciar el backend: {err}");
            let _ = app.emit(
                "backend://error",
                serde_json::json!({ "message": err.to_string() }),
            );
        }
    }
}

/// Arranca el backend si todavía no está corriendo (reutiliza el de desarrollo).
fn ensure_backend(app: &tauri::AppHandle) {
    let state = app.state::<AppState>();
    if state.base_url().is_some() {
        return;
    }
    let _ = std::fs::create_dir_all(paths::data_dir(app));

    // En desarrollo, si `scripts/dev.sh` ya arrancó un backend, se reutiliza.
    if let Ok(port) = std::env::var("FINANZAR_PORT") {
        if let Ok(port) = port.parse::<u16>() {
            let url = format!("http://127.0.0.1:{port}");
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                if wait_for_backend(&url, Duration::from_secs(3)).await {
                    set_base_url(&app_clone, url);
                    log::info!("Backend de desarrollo reutilizado");
                } else {
                    spawn_managed_backend(&app_clone);
                }
            });
            return;
        }
    }
    spawn_managed_backend(app);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            commands::bootstrap_status,
            commands::api_get,
            commands::api_request,
            commands::pick_and_import_pdf,
            commands::app_paths,
            commands::check_update,
            commands::install_update,
            commands::start_update_polling,
            commands::stop_update_polling,
        ])
        .setup(|app| {
            ensure_backend(app.handle());
            updater::start_polling(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<AppState>();
                let lock = state.backend.lock();
                if let Ok(mut guard) = lock {
                    if let Some(backend) = guard.as_mut() {
                        backend.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error al iniciar FinanzAR Desktop");
}
