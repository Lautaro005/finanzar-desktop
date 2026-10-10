//! Actualizaciones: consulta cada 3 horas con jitter y backoff.
//!
//! Nunca instala sin consentimiento. Si GitHub no está disponible, se mantiene
//! el último estado conocido y no se interrumpe el trabajo.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use rand::Rng;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::UpdaterExt;

pub const POLL_SECONDS: u64 = 3 * 60 * 60;
const JITTER_SECONDS: u64 = 10 * 60;

static POLLING: AtomicBool = AtomicBool::new(false);

/// Compara versiones semánticas simples (`a.b.c`).
pub fn version_is_newer(candidate: &str, current: &str) -> bool {
    fn parse(value: &str) -> (u32, u32, u32) {
        let cleaned = value.trim_start_matches('v');
        let mut parts = cleaned.split('.').map(|part| {
            part.chars()
                .take_while(|ch| ch.is_ascii_digit())
                .collect::<String>()
                .parse::<u32>()
                .unwrap_or(0)
        });
        (
            parts.next().unwrap_or(0),
            parts.next().unwrap_or(0),
            parts.next().unwrap_or(0),
        )
    }
    parse(candidate) > parse(current)
}

/// Consulta puntual del updater.
pub async fn check_now(app: &AppHandle) -> Result<Value, String> {
    let updater = app.updater().map_err(|err| err.to_string())?;
    match updater.check().await {
        Ok(Some(update)) => Ok(json!({
            "available": true,
            "version": update.version,
            "currentVersion": update.current_version,
            "date": update.date.map(|date| date.to_string()),
            "body": update.body,
            "requiresConsent": true,
        })),
        Ok(None) => Ok(json!({
            "available": false,
            "currentVersion": app.package_info().version.to_string(),
            "requiresConsent": true,
        })),
        Err(err) => Err(err.to_string()),
    }
}

/// Descarga e instala la actualización disponible (requiere consentimiento).
pub async fn install(app: &AppHandle) -> Result<Value, String> {
    let updater = app.updater().map_err(|err| err.to_string())?;
    let update = updater
        .check()
        .await
        .map_err(|err| err.to_string())?
        .ok_or_else(|| "No hay actualizaciones disponibles".to_string())?;
    let version = update.version.clone();
    let mut downloaded: u64 = 0;
    update
        .download_and_install(
            |chunk_size, _content_length| {
                downloaded += chunk_size as u64;
            },
            || {},
        )
        .await
        .map_err(|err| err.to_string())?;
    Ok(json!({ "installed": true, "version": version, "downloadedBytes": downloaded }))
}

/// Arranca el sondeo periódico en segundo plano.
pub fn start_polling(app: AppHandle) {
    if POLLING.swap(true, Ordering::SeqCst) {
        return;
    }
    tauri::async_runtime::spawn(async move {
        let _ = app.emit(
            "update://polling-started",
            json!({ "intervalSeconds": POLL_SECONDS }),
        );
        let mut backoff: u64 = 0;
        while POLLING.load(Ordering::SeqCst) {
            let jitter = rand::thread_rng().gen_range(0..JITTER_SECONDS);
            let wait = if backoff == 0 {
                POLL_SECONDS + jitter
            } else {
                (POLL_SECONDS.min(backoff * 2)) + jitter
            };
            tokio::time::sleep(Duration::from_secs(wait)).await;
            if !POLLING.load(Ordering::SeqCst) {
                break;
            }
            match check_now(&app).await {
                Ok(status) => {
                    backoff = 0;
                    let _ = app.emit("update://status", status);
                }
                Err(_) => {
                    backoff = if backoff == 0 {
                        60
                    } else {
                        (backoff * 2).min(POLL_SECONDS)
                    };
                }
            }
        }
    });
}

/// Detiene el sondeo automático (la persona puede desactivarlo).
pub fn stop_polling() {
    POLLING.store(false, Ordering::SeqCst);
}

/// Sondeo habilitado.
pub fn is_polling() -> bool {
    POLLING.load(Ordering::SeqCst)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn newer_version_detection() {
        assert!(version_is_newer("0.2.0", "0.1.0"));
        assert!(version_is_newer("v1.0.1", "1.0.0"));
        assert!(!version_is_newer("0.1.0", "0.1.0"));
        assert!(!version_is_newer("0.0.9", "0.1.0"));
        assert!(version_is_newer("2", "1.9.9"));
    }

    #[test]
    fn polling_flag_toggles() {
        stop_polling();
        assert!(!is_polling());
    }
}
