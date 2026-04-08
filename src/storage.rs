use std::env;
use std::fs;
use std::io;
use std::path::PathBuf;

use chrono::{DateTime, Local, NaiveDate, NaiveDateTime, Utc};

use crate::model::{
    default_general_tab_sync_id, default_tabs, task_sync_id_from_legacy_id, tab_sync_id_from_name,
    APP_NAME, AppData, Settings, SyncFile, SyncPreferences, SyncSharedData, SyncTabRecord,
    SyncTaskRecord, SyncTaskStatus, SyncWriter, TabSpec, TaskItem,
};

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

pub fn now_sync_stamp() -> String {
    Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
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

pub fn load_sync_file_from_path(path: &PathBuf) -> io::Result<SyncFile> {
    let raw = fs::read_to_string(path)?;
    let file: SyncFile = serde_json::from_str(&raw)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    Ok(file.normalized())
}

pub fn save_sync_file_to_path(path: &PathBuf, data: &SyncFile) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let payload = serde_json::to_string_pretty(&data.clone().normalized())
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;

    fs::write(path, payload)
}

pub fn app_data_to_sync_file(data: &AppData, device_id: &str) -> SyncFile {
    let normalized = data.clone().normalized();
    let updated_at = now_sync_stamp();

    let tabs = normalized
        .settings
        .tabs
        .iter()
        .enumerate()
        .map(|(order, tab)| SyncTabRecord {
            id: if tab.sync_id.trim().is_empty() {
                tab_sync_id_from_name(&tab.name)
            } else {
                tab.sync_id.clone()
            },
            name: tab.name.clone(),
            priority: tab.priority,
            order: order as i32,
            updated_at: updated_at.clone(),
            deleted_at: None,
        })
        .collect();

    let active_tasks = normalized
        .active
        .iter()
        .enumerate()
        .map(|(order, task)| sync_task_from_local(task, order as i32, SyncTaskStatus::Active));
    let history_tasks = normalized.history.iter().enumerate().map(|(order, task)| {
        sync_task_from_local(task, order as i32, SyncTaskStatus::Completed)
    });

    SyncFile {
        schema_version: crate::model::default_sync_schema_version(),
        updated_at: updated_at.clone(),
        last_writer: SyncWriter {
            device_id: device_id.trim().to_string(),
            app_id: "focus-desktop".to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
        },
        shared: SyncSharedData {
            tabs,
            tasks: active_tasks.chain(history_tasks).collect(),
            preferences: SyncPreferences {
                theme_name: normalized.settings.theme_name,
                custom_palette: normalized.settings.custom_palette,
                font_scale: normalized.settings.font_scale,
                accessibility_mode: normalized.settings.accessibility_mode,
                show_item_meta: normalized.settings.show_item_meta,
            },
        }
        .normalized(),
        extra: Default::default(),
    }
}

pub fn sync_file_to_app_data(sync: &SyncFile, local_settings: Option<&Settings>) -> AppData {
    let normalized = sync.clone().normalized();

    let mut settings = local_settings.cloned().unwrap_or_default().normalized();
    settings.theme_name = normalized.shared.preferences.theme_name.clone();
    settings.custom_palette = normalized.shared.preferences.custom_palette.clone();
    settings.font_scale = normalized.shared.preferences.font_scale;
    settings.accessibility_mode = normalized.shared.preferences.accessibility_mode;
    settings.show_item_meta = normalized.shared.preferences.show_item_meta;

    let mut tabs: Vec<TabSpec> = normalized
        .shared
        .tabs
        .iter()
        .filter(|tab| tab.deleted_at.is_none())
        .map(|tab| TabSpec {
            sync_id: tab.id.clone(),
            name: tab.name.clone(),
            priority: tab.priority,
        })
        .collect();
    tabs.sort_by_key(|tab| {
        normalized
            .shared
            .tabs
            .iter()
            .find(|record| record.id == tab.sync_id)
            .map(|record| record.order)
            .unwrap_or_default()
    });
    settings.tabs = crate::model::normalize_tabs(if tabs.is_empty() { default_tabs() } else { tabs });

    let active = sync_tasks_to_local(&normalized, SyncTaskStatus::Active, &settings.tabs);
    let history = sync_tasks_to_local(&normalized, SyncTaskStatus::Completed, &settings.tabs);

    AppData {
        active,
        history,
        settings,
    }
    .normalized()
}

pub fn default_export_path() -> PathBuf {
    home_dir()
        .unwrap_or_else(env::temp_dir)
        .join("focus-export.json")
}

pub fn startup_enabled() -> io::Result<bool> {
    Ok(startup_path().is_some_and(|path| path.exists()))
}

pub fn set_startup_enabled(enabled: bool) -> io::Result<()> {
    let Some(path) = startup_path() else {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "Startup is currently implemented for Windows and Linux.",
        ));
    };

    if enabled {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let exe = env::current_exe()?;
        #[cfg(target_os = "windows")]
        {
            let script = format!("@echo off\r\nstart \"\" \"{}\"\r\n", exe.display());
            fs::write(path, script)?;
        }

        #[cfg(target_os = "linux")]
        {
            let entry = format!(
                "[Desktop Entry]\nType=Application\nName=focus\nExec=\"{}\"\nX-GNOME-Autostart-enabled=true\n",
                exe.display()
            );
            fs::write(path, entry)?;
        }
    } else if let Some(path) = startup_path() {
        let _ = fs::remove_file(path);
    }

    Ok(())
}

fn data_file_path() -> io::Result<PathBuf> {
    Ok(data_dir_path()?.join("checklist.json"))
}

fn startup_path() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        return home_dir().map(|home| {
            home.join("AppData")
                .join("Roaming")
                .join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs")
                .join("Startup")
                .join("focus.cmd")
        });
    }

    #[cfg(target_os = "linux")]
    {
        return home_dir().map(|home| {
            home.join(".config")
                .join("autostart")
                .join("focus.desktop")
        });
    }

    #[cfg(not(any(target_os = "windows", target_os = "linux")))]
    {
        None
    }
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

fn sync_task_from_local(task: &TaskItem, order: i32, status: SyncTaskStatus) -> SyncTaskRecord {
    SyncTaskRecord {
        id: if task.sync_id.trim().is_empty() {
            task_sync_id_from_legacy_id(task.id)
        } else {
            task.sync_id.clone()
        },
        text: task.text.clone(),
        status,
        tab_id: if task.tab.trim().is_empty() {
            default_general_tab_sync_id()
        } else {
            tab_sync_id_from_name(&task.tab)
        },
        current: task.current && matches!(status, SyncTaskStatus::Active),
        order,
        created_at: local_stamp_to_sync(&task.created_at),
        updated_at: local_stamp_to_sync(
            if matches!(status, SyncTaskStatus::Completed) && !task.completed_at.trim().is_empty() {
                &task.completed_at
            } else {
                &task.created_at
            },
        ),
        completed_at: if task.completed_at.trim().is_empty() {
            None
        } else {
            Some(local_stamp_to_sync(&task.completed_at))
        },
        deleted_at: None,
        extra_info: task.extra_info.clone(),
        due_date: if task.due_date.trim().is_empty() {
            None
        } else {
            Some(local_stamp_to_sync(&task.due_date))
        },
    }
}

fn sync_tasks_to_local(sync: &SyncFile, status: SyncTaskStatus, tabs: &[TabSpec]) -> Vec<TaskItem> {
    let mut tasks: Vec<&SyncTaskRecord> = sync
        .shared
        .tasks
        .iter()
        .filter(|task| task.deleted_at.is_none() && task.status == status)
        .collect();
    tasks.sort_by_key(|task| task.order);

    tasks.into_iter()
        .enumerate()
        .map(|(index, task)| TaskItem {
            id: sync_task_numeric_id(&task.id).unwrap_or(index as u64 + 1),
            sync_id: task.id.clone(),
            text: task.text.clone(),
            done: matches!(status, SyncTaskStatus::Completed),
            current: matches!(status, SyncTaskStatus::Active) && task.current,
            created_at: sync_stamp_to_local(&task.created_at),
            completed_at: task
                .completed_at
                .as_deref()
                .map(sync_stamp_to_local)
                .unwrap_or_default(),
            extra_info: task.extra_info.clone(),
            due_date: task
                .due_date
                .as_deref()
                .map(sync_stamp_to_local)
                .unwrap_or_default(),
            tab: resolve_tab_name(&task.tab_id, tabs),
        })
        .collect()
}

fn resolve_tab_name(tab_id: &str, tabs: &[TabSpec]) -> String {
    tabs.iter()
        .find(|tab| tab.sync_id == tab_id)
        .map(|tab| tab.name.clone())
        .unwrap_or_else(|| crate::model::GENERAL_TAB_NAME.to_string())
}

fn sync_task_numeric_id(value: &str) -> Option<u64> {
    value.strip_prefix("task-")?.parse().ok()
}

fn local_stamp_to_sync(value: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        return String::new();
    }

    NaiveDateTime::parse_from_str(value, "%Y-%m-%d %H:%M")
        .map(|date| date.and_utc().format("%Y-%m-%dT%H:%M:%SZ").to_string())
        .or_else(|_| {
            NaiveDate::parse_from_str(value, "%Y-%m-%d")
                .map(|date| date.and_hms_opt(0, 0, 0).unwrap().and_utc().format("%Y-%m-%dT%H:%M:%SZ").to_string())
        })
        .unwrap_or_else(|_| value.to_string())
}

fn sync_stamp_to_local(value: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        return String::new();
    }

    DateTime::parse_from_rfc3339(value)
        .map(|date| date.with_timezone(&Local).format("%Y-%m-%d %H:%M").to_string())
        .or_else(|_| {
            NaiveDateTime::parse_from_str(value, "%Y-%m-%d %H:%M")
                .map(|date| date.format("%Y-%m-%d %H:%M").to_string())
        })
        .unwrap_or_else(|_| value.to_string())
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

    #[test]
    fn sync_round_trip_preserves_shared_fields() {
        let mut data = AppData::with_default_items("2026-04-05 12:00");
        data.settings.sync.enabled = true;
        data.settings.sync.device_id = "desktop-win11".into();
        data.active[0].sync_id = "tsk_01".into();
        data.active[0].tab = "General".into();
        data.active[0].current = true;
        data.active[0].due_date = "2026-04-08 09:30".into();

        let sync = app_data_to_sync_file(&data, "desktop-win11");
        let restored = sync_file_to_app_data(&sync, Some(&data.settings));

        assert_eq!(sync.schema_version, 1);
        assert_eq!(sync.shared.tabs[0].id, "general");
        assert_eq!(sync.shared.tasks[0].id, "tsk_01");
        assert_eq!(restored.active.len(), data.active.len());
        assert_eq!(restored.active[0].sync_id, "tsk_01");
        assert_eq!(restored.active[0].tab, "General");
        assert!(restored.settings.sync.enabled);
        assert_eq!(restored.settings.sync.device_id, "desktop-win11");
    }
}
