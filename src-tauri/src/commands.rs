//! Cliente HTTP local y comandos expuestos al frontend.
//!
//! Rust nunca habla con la red externa para datos financieros: solo con
//! `127.0.0.1:<puerto>` del sidecar Python.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::State;

use crate::paths;
use crate::sidecar::Backend;
use crate::updater;

/// Estado compartido de la aplicación.
pub struct AppState {
    pub backend: std::sync::Mutex<Option<Backend>>,
    pub base_url: std::sync::Mutex<Option<String>>,
    pub version: String,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            backend: std::sync::Mutex::new(None),
            base_url: std::sync::Mutex::new(None),
            version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }

    pub fn base_url(&self) -> Option<String> {
        self.base_url.lock().ok().and_then(|guard| guard.clone())
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiEnvelope {
    pub ok: bool,
    pub data: Option<Value>,
    pub error: Option<Value>,
    pub request_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl CommandError {
    fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.to_string(),
            message: message.into(),
        }
    }

    fn not_ready() -> Self {
        Self::new(
            "backend_unavailable",
            "El backend local todavía no está listo",
        )
    }
}

/// Estado de arranque que la interfaz muestra mientras se levanta el backend.
#[derive(Debug, Serialize, Clone)]
pub struct BootstrapStatus {
    pub backend: bool,
    pub base_url: Option<String>,
    pub version: String,
    pub stage: String,
}

#[tauri::command]
pub fn bootstrap_status(state: State<'_, AppState>) -> BootstrapStatus {
    let base_url = state.base_url();
    BootstrapStatus {
        backend: base_url.is_some(),
        stage: if base_url.is_some() {
            "listo"
        } else {
            "iniciando backend"
        }
        .to_string(),
        base_url,
        version: state.version.clone(),
    }
}

/// GET al backend local.
#[tauri::command]
pub async fn api_get(state: State<'_, AppState>, path: String) -> Result<Value, CommandError> {
    let base_url = state.base_url().ok_or_else(CommandError::not_ready)?;
    let url = format!("{}{}", base_url, path);
    let response = reqwest::get(&url)
        .await
        .map_err(|err| CommandError::new("request_failed", err.to_string()))?;
    let envelope: ApiEnvelope = response
        .json()
        .await
        .map_err(|err| CommandError::new("invalid_response", err.to_string()))?;
    if envelope.ok {
        Ok(envelope.data.unwrap_or(Value::Null))
    } else {
        Err(CommandError::new(
            "backend_error",
            envelope
                .error
                .as_ref()
                .and_then(|error| error.get("message"))
                .and_then(|message| message.as_str())
                .unwrap_or("Error del backend local")
                .to_string(),
        ))
    }
}

/// POST/PATCH/DELETE al backend local con cuerpo JSON opcional.
#[tauri::command]
pub async fn api_request(
    state: State<'_, AppState>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<Value, CommandError> {
    let base_url = state.base_url().ok_or_else(CommandError::not_ready)?;
    let url = format!("{}{}", base_url, path);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .map_err(|err| CommandError::new("client_error", err.to_string()))?;
    let request = match method.to_uppercase().as_str() {
        "POST" => client.post(&url),
        "PATCH" => client.patch(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        _ => return Err(CommandError::new("invalid_method", "Método no permitido")),
    };
    let request = match body {
        Some(payload) => request.json(&payload),
        None => request,
    };
    let response = request
        .send()
        .await
        .map_err(|err| CommandError::new("request_failed", err.to_string()))?;
    let envelope: ApiEnvelope = response
        .json()
        .await
        .map_err(|err| CommandError::new("invalid_response", err.to_string()))?;
    if envelope.ok {
        Ok(envelope.data.unwrap_or(Value::Null))
    } else {
        let error = envelope.error.unwrap_or(Value::Null);
        Err(CommandError::new(
            error
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("backend_error"),
            error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("Error del backend local")
                .to_string(),
        ))
    }
}

/// Importa un PDF elegido con el selector nativo.
///
/// Rust reenvía el archivo al backend local como multipart. El PDF nunca sale
/// del equipo.
#[tauri::command]
pub async fn pick_and_import_pdf(
    state: State<'_, AppState>,
    path: String,
) -> Result<Value, CommandError> {
    let base_url = state.base_url().ok_or_else(CommandError::not_ready)?;
    let file_path = std::path::PathBuf::from(&path);
    if !file_path.exists() {
        return Err(CommandError::new(
            "file_not_found",
            "El archivo seleccionado no existe",
        ));
    }
    let bytes = tokio::fs::read(&file_path)
        .await
        .map_err(|err| CommandError::new("read_failed", err.to_string()))?;
    let filename = file_path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "resumen.pdf".to_string());
    let part = reqwest::multipart::Part::bytes(bytes)
        .file_name(filename)
        .mime_str("application/pdf")
        .map_err(|err| CommandError::new("multipart_error", err.to_string()))?;
    let form = reqwest::multipart::Form::new().part("file", part);
    let response = reqwest::Client::new()
        .post(format!("{base_url}/api/documents/import"))
        .multipart(form)
        .timeout(std::time::Duration::from_secs(300))
        .send()
        .await
        .map_err(|err| CommandError::new("request_failed", err.to_string()))?;
    let envelope: ApiEnvelope = response
        .json()
        .await
        .map_err(|err| CommandError::new("invalid_response", err.to_string()))?;
    if envelope.ok {
        Ok(envelope.data.unwrap_or(Value::Null))
    } else {
        let error = envelope.error.unwrap_or(Value::Null);
        Err(CommandError::new(
            error
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("import_failed"),
            error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("No se pudo importar el documento")
                .to_string(),
        ))
    }
}

/// Datos de entorno que pide la interfaz al abrir.
#[tauri::command]
pub fn app_paths(app: tauri::AppHandle) -> Value {
    let data = paths::data_dir(&app);
    serde_json::json!({
        "dataDir": data.to_string_lossy(),
        "target": paths::target_triple(),
        "version": env!("CARGO_PKG_VERSION"),
        "dev": cfg!(debug_assertions),
    })
}

/// Comprueba actualizaciones (con backoff y sin datos financieros).
#[tauri::command]
pub async fn check_update(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Value, CommandError> {
    _ = state;
    updater::check_now(&app)
        .await
        .map_err(|err| CommandError::new("update_failed", err.to_string()))
}

/// Instala una actualización **solo** si la persona lo pidió explícitamente.
#[tauri::command]
pub async fn install_update(app: tauri::AppHandle, confirmed: bool) -> Result<Value, CommandError> {
    if !confirmed {
        return Err(CommandError::new(
            "consent_required",
            "La instalación requiere tu confirmación explícita",
        ));
    }
    updater::install(&app)
        .await
        .map_err(|err| CommandError::new("install_failed", err.to_string()))
}

/// Inicia el sondeo periódico del updater (cada 3 horas con jitter).
#[tauri::command]
pub fn start_update_polling(app: tauri::AppHandle) -> Value {
    updater::start_polling(app);
    serde_json::json!({ "polling": true, "intervalSeconds": updater::POLL_SECONDS })
}

/// Detiene el sondeo automático de actualizaciones.
#[tauri::command]
pub fn stop_update_polling() -> Value {
    updater::stop_polling();
    serde_json::json!({ "polling": false })
}
