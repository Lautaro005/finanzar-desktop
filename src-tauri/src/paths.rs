//! Resolución de rutas locales de FinanzAR.

use std::path::PathBuf;

use tauri::{AppHandle, Manager};

/// Directorio de datos de la aplicación.
///
/// Prioriza `FINANZAR_DATA_DIR` (que usa `scripts/dev.sh`) y cae al
/// `app_data_dir` estándar de Tauri (`~/Library/Application Support/...`).
pub fn data_dir(app: &AppHandle) -> PathBuf {
    if let Ok(custom) = std::env::var("FINANZAR_DATA_DIR") {
        if !custom.is_empty() {
            return PathBuf::from(custom);
        }
    }
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// Raíz del repositorio/proyecto (solo disponible en desarrollo).
pub fn repo_root() -> Option<PathBuf> {
    if let Ok(custom) = std::env::var("FINANZAR_REPO_ROOT") {
        if !custom.is_empty() {
            return Some(PathBuf::from(custom));
        }
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest.parent().map(|path| path.to_path_buf())
}

/// Target de macOS en el formato que usa Tauri (`aarch64-apple-darwin`).
pub fn target_triple() -> String {
    let arch = if cfg!(target_arch = "aarch64") {
        "aarch64"
    } else if cfg!(target_arch = "x86_64") {
        "x86_64"
    } else {
        "unknown"
    };
    format!("{arch}-apple-darwin")
}
