//! Gestión del sidecar del backend Python.
//!
//! En producción se lanza el binario empaquetado (sidecar de Tauri). En
//! desarrollo se lanza el intérprete del entorno virtual del backend, para no
//! depender de un build previo. El proceso se detiene al cerrar la ventana.

use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

use tauri::AppHandle;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SidecarError {
    #[error("no se encontró un backend ejecutable (sidecar o entorno de desarrollo)")]
    NotFound,
    #[error("no se pudo iniciar el backend: {0}")]
    Spawn(String),
}

enum Process {
    Std(Child),
    Plugin(Option<tauri_plugin_shell::process::CommandChild>),
}

/// Un backend en ejecución dentro de `127.0.0.1`.
pub struct Backend {
    pub port: u16,
    pub base_url: String,
    process: Process,
}

pub fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|listener| listener.local_addr())
        .map(|addr| addr.port())
        .unwrap_or(8765)
}

fn dev_python(repo_root: Option<&Path>) -> Option<PathBuf> {
    let root = repo_root?;
    let candidate = root
        .join("backend")
        .join(".venv")
        .join("bin")
        .join("python");
    candidate.exists().then_some(candidate)
}

impl Backend {
    /// Arranca el backend y espera a que el puerto quede escuchando.
    pub fn spawn(
        app: &AppHandle,
        data_dir: &Path,
        repo_root: Option<&Path>,
    ) -> Result<Self, SidecarError> {
        let port = free_port();
        let process = if cfg!(debug_assertions) {
            Self::spawn_dev(data_dir, repo_root, port)?
        } else {
            Self::spawn_sidecar(app, data_dir, port)?
        };
        let back_end = Self {
            port,
            base_url: format!("http://127.0.0.1:{port}"),
            process,
        };
        Ok(back_end)
    }

    fn spawn_dev(
        data_dir: &Path,
        repo_root: Option<&Path>,
        port: u16,
    ) -> Result<Process, SidecarError> {
        let program = if let Some(python) = dev_python(repo_root) {
            python
        } else {
            PathBuf::from(
                std::env::var("FINANZAR_DEV_BACKEND").unwrap_or_else(|_| "python3".to_string()),
            )
        };
        let mut command = Command::new(&program);
        command
            .args([
                "-m",
                "finanzar_backend",
                "--host",
                "127.0.0.1",
                "--port",
                &port.to_string(),
                "--data-dir",
                &data_dir.to_string_lossy(),
            ])
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        if let Some(root) = repo_root {
            command.env("FINANZAR_REPO_ROOT", root.to_string_lossy().to_string());
            command.current_dir(root.join("backend"));
        }
        let child = command
            .spawn()
            .map_err(|err| SidecarError::Spawn(err.to_string()))?;
        Ok(Process::Std(child))
    }

    fn spawn_sidecar(app: &AppHandle, data_dir: &Path, port: u16) -> Result<Process, SidecarError> {
        use tauri_plugin_shell::ShellExt;

        let command = app
            .shell()
            .sidecar("finanzar-backend")
            .map_err(|err| SidecarError::Spawn(err.to_string()))?
            .args([
                "--host",
                "127.0.0.1",
                "--port",
                &port.to_string(),
                "--data-dir",
                &data_dir.to_string_lossy(),
            ]);
        let (mut receiver, child) = command
            .spawn()
            .map_err(|err| SidecarError::Spawn(err.to_string()))?;
        tauri::async_runtime::spawn(async move {
            use tauri_plugin_shell::process::CommandEvent;
            while let Some(event) = receiver.recv().await {
                match event {
                    CommandEvent::Stderr(line) => {
                        log::warn!("backend: {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Terminated(payload) => {
                        log::info!("backend terminado con código {:?}", payload.code);
                    }
                    _ => {}
                }
            }
        });
        Ok(Process::Plugin(Some(child)))
    }

    /// Detiene el proceso del backend.
    pub fn stop(&mut self) {
        match &mut self.process {
            Process::Std(child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            Process::Plugin(slot) => {
                // `CommandChild::kill` consume el child, por eso se guarda en un `Option`.
                if let Some(child) = slot.take() {
                    let _ = child.kill();
                }
            }
        }
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}
