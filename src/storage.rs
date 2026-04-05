use std::env;
use std::fs;
use std::io;
use std::path::PathBuf;

use chrono::Local;

use crate::model::{APP_NAME, AppData};

#[derive(Debug, Clone)]
pub struct DataStore {
    path: PathBuf,
}

impl DataStore {
    pub fn new() -> io::Result<Self> {
        Ok(Self {
            path: data_file_path()?,
        })
    }

    #[cfg(test)]
    pub fn from_path(path: PathBuf) -> Self {
        Self { path }
    }

    pub fn load(&self) -> AppData {
        let defaults = AppData::with_default_items(&now_stamp());

        if !self.path.exists() {
            return defaults;
        }

        load_data_from_path(&self.path).unwrap_or(defaults)
    }

    pub fn save(&self, data: &AppData) -> io::Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut normalized = data.clone().normalized();
        normalized.history.truncate(250);

        let payload = serde_json::to_string_pretty(&normalized)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;

        fs::write(&self.path, payload)
    }
}

pub fn now_stamp() -> String {
    Local::now().format("%Y-%m-%d %H:%M").to_string()
}

pub fn load_data_from_path(path: &PathBuf) -> io::Result<AppData> {
    let raw = fs::read_to_string(path)?;
    let data: AppData = serde_json::from_str(&raw)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    Ok(data.normalized())
}

pub fn save_data_to_path(path: &PathBuf, data: &AppData) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let mut normalized = data.clone().normalized();
    normalized.history.truncate(250);

    let payload = serde_json::to_string_pretty(&normalized)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;

    fs::write(path, payload)
}

pub fn default_export_path() -> PathBuf {
    home_dir()
        .unwrap_or_else(env::temp_dir)
        .join("focus-export.json")
}

fn data_file_path() -> io::Result<PathBuf> {
    Ok(data_dir_path()?.join("checklist.json"))
}

fn data_dir_path() -> io::Result<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        let base = env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| home_dir().map(|home| home.join("AppData").join("Roaming")))
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::NotFound, "APPDATA directory not found")
            })?;
        return Ok(base.join(APP_NAME));
    }

    #[cfg(target_os = "macos")]
    {
        let home = home_dir()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "home directory not found"))?;
        return Ok(home
            .join("Library")
            .join("Application Support")
            .join(APP_NAME));
    }

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let home = home_dir()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "home directory not found"))?;
        Ok(home.join(format!(".{APP_NAME}")))
    }
}

fn home_dir() -> Option<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("USERPROFILE").map(PathBuf::from))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn now_stamp_uses_python_compatible_format() {
        let stamp = now_stamp();
        assert_eq!(stamp.len(), 16);
        assert_eq!(&stamp[4..5], "-");
        assert_eq!(&stamp[7..8], "-");
        assert_eq!(&stamp[10..11], " ");
        assert_eq!(&stamp[13..14], ":");
    }

    #[test]
    fn load_returns_default_payload_when_file_is_missing() {
        let path = env::temp_dir().join(format!("focus-missing-{}.json", std::process::id()));
        let store = DataStore::from_path(path);

        let data = store.load();

        assert_eq!(data.active.len(), 3);
        assert!(data.history.is_empty());
        assert!(data.settings.always_on_top);
    }
}
