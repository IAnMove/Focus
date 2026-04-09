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
    let fallback_updated_at = default_local_sync_updated_at(&normalized);
    let preferences_updated_at = effective_preferences_updated_at(&normalized, &fallback_updated_at);

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
            updated_at: effective_tab_updated_at(tab, &fallback_updated_at),
            deleted_at: None,
        })
        .collect::<Vec<_>>();

    let active_tasks = normalized
        .active
        .iter()
        .enumerate()
        .map(|(order, task)| {
            sync_task_from_local(task, order as i32, SyncTaskStatus::Active, &fallback_updated_at)
        });
    let history_tasks = normalized.history.iter().enumerate().map(|(order, task)| {
        sync_task_from_local(task, order as i32, SyncTaskStatus::Completed, &fallback_updated_at)
    });
    let tasks = active_tasks.chain(history_tasks).collect::<Vec<_>>();
    let updated_at = latest_sync_stamp(
        tabs.iter()
            .map(sync_tab_version_stamp)
            .chain(tasks.iter().map(sync_task_version_stamp))
            .chain(std::iter::once(preferences_updated_at.clone())),
    )
    .unwrap_or_else(|| fallback_updated_at.clone());

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
            tasks,
            preferences: SyncPreferences {
                theme_name: normalized.settings.theme_name,
                custom_palette: normalized.settings.custom_palette,
                font_scale: normalized.settings.font_scale,
                accessibility_mode: normalized.settings.accessibility_mode,
                show_item_meta: normalized.settings.show_item_meta,
                updated_at: preferences_updated_at,
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
    settings.preferences_updated_at = if normalized.shared.preferences.updated_at.trim().is_empty() {
        normalized.updated_at.clone()
    } else {
        normalized.shared.preferences.updated_at.clone()
    };

    let mut tabs: Vec<TabSpec> = normalized
        .shared
        .tabs
        .iter()
        .filter(|tab| tab.deleted_at.is_none())
        .map(|tab| TabSpec {
            sync_id: tab.id.clone(),
            sync_updated_at: tab.updated_at.clone(),
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

fn sync_task_from_local(
    task: &TaskItem,
    order: i32,
    status: SyncTaskStatus,
    fallback_updated_at: &str,
) -> SyncTaskRecord {
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
        updated_at: effective_task_updated_at(task, status, fallback_updated_at),
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
            sync_updated_at: task.updated_at.clone(),
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

fn default_local_sync_updated_at(data: &AppData) -> String {
    if !data.settings.sync.last_sync_at.trim().is_empty() {
        normalize_sync_meta_stamp(&data.settings.sync.last_sync_at, &now_sync_stamp())
    } else {
        now_sync_stamp()
    }
}

fn effective_preferences_updated_at(data: &AppData, fallback: &str) -> String {
    normalize_sync_meta_stamp(&data.settings.preferences_updated_at, fallback)
}

fn effective_tab_updated_at(tab: &TabSpec, fallback: &str) -> String {
    normalize_sync_meta_stamp(&tab.sync_updated_at, fallback)
}

fn effective_task_updated_at(task: &TaskItem, status: SyncTaskStatus, fallback: &str) -> String {
    if !task.sync_updated_at.trim().is_empty() {
        return normalize_sync_meta_stamp(&task.sync_updated_at, fallback);
    }

    if matches!(status, SyncTaskStatus::Completed) && !task.completed_at.trim().is_empty() {
        return normalize_sync_meta_stamp(&task.completed_at, fallback);
    }

    if !task.created_at.trim().is_empty() {
        return normalize_sync_meta_stamp(&task.created_at, fallback);
    }

    fallback.to_string()
}

fn normalize_sync_meta_stamp(value: &str, fallback: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        return fallback.to_string();
    }

    let normalized = local_stamp_to_sync(value);
    if normalized.trim().is_empty() {
        fallback.to_string()
    } else {
        normalized
    }
}

fn sync_task_version_stamp(task: &SyncTaskRecord) -> String {
    task.deleted_at
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(task.updated_at.as_str())
        .trim()
        .to_string()
}

fn sync_tab_version_stamp(tab: &SyncTabRecord) -> String {
    tab.deleted_at
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(tab.updated_at.as_str())
        .trim()
        .to_string()
}

fn latest_sync_stamp<I>(stamps: I) -> Option<String>
where
    I: IntoIterator<Item = String>,
{
    stamps
        .into_iter()
        .filter(|stamp| !stamp.trim().is_empty())
        .max_by(|left, right| compare_sync_stamps(left, right))
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

pub fn merge_sync_files(
    local: &SyncFile,
    remote: &SyncFile,
    last_sync_at: &str,
    device_id: &str,
) -> SyncFile {
    let local = local.clone().normalized();
    let remote = remote.clone().normalized();
    let now = now_sync_stamp();
    let normalized_last_sync = normalize_sync_meta_stamp(last_sync_at, "");

    let tabs = merge_tab_records(&local.shared.tabs, &remote.shared.tabs, &normalized_last_sync, &now);
    let tasks = merge_task_records(&local.shared.tasks, &remote.shared.tasks, &normalized_last_sync, &now);
    let preferences = merge_preferences(
        &local.shared.preferences,
        &remote.shared.preferences,
        &normalized_last_sync,
    );
    let updated_at = latest_sync_stamp(
        tabs.iter()
            .map(sync_tab_version_stamp)
            .chain(tasks.iter().map(sync_task_version_stamp))
            .chain(std::iter::once(preferences.updated_at.clone()))
            .chain(std::iter::once(local.updated_at.clone()))
            .chain(std::iter::once(remote.updated_at.clone())),
    )
    .unwrap_or_else(|| now.clone());

    SyncFile {
        schema_version: crate::model::default_sync_schema_version(),
        updated_at,
        last_writer: SyncWriter {
            device_id: device_id.trim().to_string(),
            app_id: "focus-desktop".to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
        },
        shared: SyncSharedData {
            tabs,
            tasks,
            preferences,
        }
        .normalized(),
        extra: remote.extra.clone(),
    }
    .normalized()
}

fn merge_tab_records(
    local: &[SyncTabRecord],
    remote: &[SyncTabRecord],
    last_sync_at: &str,
    now: &str,
) -> Vec<SyncTabRecord> {
    let mut merged = std::collections::BTreeMap::new();

    for record in remote {
        merged.insert(record.id.clone(), record.clone());
    }

    for record in local {
        merged
            .entry(record.id.clone())
            .and_modify(|existing| *existing = pick_tab_record(record, existing))
            .or_insert_with(|| record.clone());
    }

    for record in remote {
        if local.iter().any(|local_record| local_record.id == record.id) || record.deleted_at.is_some() {
            continue;
        }

        if !last_sync_at.is_empty() && compare_sync_stamps(&sync_tab_version_stamp(record), last_sync_at).is_le() {
            merged.insert(record.id.clone(), tombstone_tab_record(record, now));
        }
    }

    let mut records: Vec<SyncTabRecord> = merged.into_values().collect();
    records.sort_by_key(|record| record.order);
    records
}

fn merge_task_records(
    local: &[SyncTaskRecord],
    remote: &[SyncTaskRecord],
    last_sync_at: &str,
    now: &str,
) -> Vec<SyncTaskRecord> {
    let mut merged = std::collections::BTreeMap::new();

    for record in remote {
        merged.insert(record.id.clone(), record.clone());
    }

    for record in local {
        merged
            .entry(record.id.clone())
            .and_modify(|existing| *existing = pick_task_record(record, existing))
            .or_insert_with(|| record.clone());
    }

    for record in remote {
        if local.iter().any(|local_record| local_record.id == record.id) || record.deleted_at.is_some() {
            continue;
        }

        if !last_sync_at.is_empty() && compare_sync_stamps(&sync_task_version_stamp(record), last_sync_at).is_le() {
            merged.insert(record.id.clone(), tombstone_task_record(record, now));
        }
    }

    let mut records: Vec<SyncTaskRecord> = merged.into_values().collect();
    records.sort_by(|left, right| {
        let left_key = match left.status {
            SyncTaskStatus::Active => 0,
            SyncTaskStatus::Completed => 1,
            SyncTaskStatus::Deleted => 2,
        };
        let right_key = match right.status {
            SyncTaskStatus::Active => 0,
            SyncTaskStatus::Completed => 1,
            SyncTaskStatus::Deleted => 2,
        };
        left_key.cmp(&right_key).then(left.order.cmp(&right.order))
    });
    records
}

fn merge_preferences(
    local: &SyncPreferences,
    remote: &SyncPreferences,
    last_sync_at: &str,
) -> SyncPreferences {
    if local.updated_at.trim().is_empty() && !remote.updated_at.trim().is_empty() {
        return remote.clone();
    }

    if remote.updated_at.trim().is_empty() && !local.updated_at.trim().is_empty() {
        return local.clone();
    }

    if local.updated_at.trim().is_empty() && remote.updated_at.trim().is_empty() {
        return if !last_sync_at.is_empty() { local.clone() } else { remote.clone() };
    }

    match compare_sync_stamps(&local.updated_at, &remote.updated_at) {
        std::cmp::Ordering::Greater => local.clone(),
        std::cmp::Ordering::Less => remote.clone(),
        std::cmp::Ordering::Equal => local.clone(),
    }
}

fn pick_tab_record(local: &SyncTabRecord, remote: &SyncTabRecord) -> SyncTabRecord {
    match compare_sync_stamps(&sync_tab_version_stamp(local), &sync_tab_version_stamp(remote)) {
        std::cmp::Ordering::Greater => local.clone(),
        std::cmp::Ordering::Less => remote.clone(),
        std::cmp::Ordering::Equal => {
            if local.deleted_at.is_some() && remote.deleted_at.is_none() {
                local.clone()
            } else {
                remote.clone()
            }
        }
    }
}

fn pick_task_record(local: &SyncTaskRecord, remote: &SyncTaskRecord) -> SyncTaskRecord {
    match compare_sync_stamps(&sync_task_version_stamp(local), &sync_task_version_stamp(remote)) {
        std::cmp::Ordering::Greater => local.clone(),
        std::cmp::Ordering::Less => remote.clone(),
        std::cmp::Ordering::Equal => {
            if local.deleted_at.is_some() && remote.deleted_at.is_none() {
                local.clone()
            } else {
                remote.clone()
            }
        }
    }
}

fn tombstone_tab_record(source: &SyncTabRecord, now: &str) -> SyncTabRecord {
    let mut record = source.clone();
    record.updated_at = now.to_string();
    record.deleted_at = Some(now.to_string());
    record
}

fn tombstone_task_record(source: &SyncTaskRecord, now: &str) -> SyncTaskRecord {
    let mut record = source.clone();
    record.status = SyncTaskStatus::Deleted;
    record.current = false;
    record.updated_at = now.to_string();
    record.deleted_at = Some(now.to_string());
    record
}

fn compare_sync_stamps(left: &str, right: &str) -> std::cmp::Ordering {
    match (parse_sync_stamp(left), parse_sync_stamp(right)) {
        (Some(left), Some(right)) => left.cmp(&right),
        _ => left.trim().cmp(right.trim()),
    }
}

fn parse_sync_stamp(value: &str) -> Option<DateTime<Utc>> {
    let value = value.trim();
    if value.is_empty() {
        return None;
    }

    DateTime::parse_from_rfc3339(value)
        .map(|value| value.with_timezone(&Utc))
        .ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_path(label: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        env::temp_dir().join(format!(
            "focus-{label}-{}-{nonce}.json",
            std::process::id()
        ))
    }

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
        data.settings.sync.last_sync_at = "2026-04-05T12:00:00Z".into();
        data.settings.preferences_updated_at = "2026-04-05T12:00:00Z".into();
        data.active[0].sync_id = "tsk_01".into();
        data.active[0].sync_updated_at = "2026-04-05T12:10:00Z".into();
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
        assert_eq!(restored.active[0].sync_updated_at, "2026-04-05T12:10:00Z");
        assert_eq!(restored.active[0].tab, "General");
        assert!(restored.settings.sync.enabled);
        assert_eq!(restored.settings.sync.device_id, "desktop-win11");
    }

    #[test]
    fn merge_prefers_newer_remote_task_updates() {
        let mut local = SyncFile::default();
        local.shared.tasks.push(SyncTaskRecord {
            id: "task-1".into(),
            text: "Local title".into(),
            status: SyncTaskStatus::Active,
            tab_id: "general".into(),
            current: false,
            order: 0,
            created_at: "2026-04-05T12:00:00Z".into(),
            updated_at: "2026-04-05T12:05:00Z".into(),
            completed_at: None,
            deleted_at: None,
            extra_info: String::new(),
            due_date: None,
        });
        local.shared.preferences.updated_at = "2026-04-05T12:05:00Z".into();
        local.updated_at = "2026-04-05T12:05:00Z".into();

        let mut remote = local.clone();
        remote.shared.tasks[0].text = "Remote title".into();
        remote.shared.tasks[0].updated_at = "2026-04-05T12:10:00Z".into();
        remote.updated_at = "2026-04-05T12:10:00Z".into();

        let merged = merge_sync_files(&local, &remote, "2026-04-05T12:00:00Z", "desktop");
        assert_eq!(merged.shared.tasks.len(), 1);
        assert_eq!(merged.shared.tasks[0].text, "Remote title");
    }

    #[test]
    fn merge_marks_missing_local_records_as_deleted_when_remote_is_old() {
        let local = SyncFile::default();
        let mut remote = SyncFile::default();
        remote.shared.tasks.push(SyncTaskRecord {
            id: "task-1".into(),
            text: "Old remote task".into(),
            status: SyncTaskStatus::Active,
            tab_id: "general".into(),
            current: false,
            order: 0,
            created_at: "2026-04-05T12:00:00Z".into(),
            updated_at: "2026-04-05T12:01:00Z".into(),
            completed_at: None,
            deleted_at: None,
            extra_info: String::new(),
            due_date: None,
        });
        remote.updated_at = "2026-04-05T12:01:00Z".into();

        let merged = merge_sync_files(&local, &remote, "2026-04-05T12:03:00Z", "desktop");
        assert_eq!(merged.shared.tasks.len(), 1);
        assert_eq!(merged.shared.tasks[0].status, SyncTaskStatus::Deleted);
        assert!(merged.shared.tasks[0].deleted_at.is_some());
    }

    #[test]
    fn save_and_load_data_round_trip_truncates_history() {
        let path = unique_temp_path("data-roundtrip");
        let mut data = AppData::with_default_items("2026-04-05 12:00");
        data.history = (0..260)
            .map(|index| {
                let mut item = TaskItem::new(index + 1000, format!("Done {index}"));
                item.done = true;
                item.completed_at = "2026-04-05 13:00".into();
                item
            })
            .collect();

        save_data_to_path(&path, &data).unwrap();
        let restored = load_data_from_path(&path).unwrap();

        assert_eq!(restored.active.len(), 3);
        assert_eq!(restored.history.len(), 250);

        let _ = fs::remove_file(path);
    }

    #[test]
    fn save_and_load_sync_file_round_trip_preserves_writer() {
        let path = unique_temp_path("sync-roundtrip");
        let sync = SyncFile {
            updated_at: "2026-04-07T20:41:12Z".into(),
            last_writer: SyncWriter {
                device_id: "desktop".into(),
                app_id: "focus-desktop".into(),
                app_version: "0.1.0".into(),
            },
            shared: SyncSharedData {
                tabs: vec![SyncTabRecord {
                    id: "general".into(),
                    name: "General".into(),
                    priority: crate::model::TabPriority::Normal,
                    order: 0,
                    updated_at: "2026-04-07T20:41:12Z".into(),
                    deleted_at: None,
                }],
                tasks: vec![],
                preferences: SyncPreferences::default(),
            },
            ..SyncFile::default()
        };

        save_sync_file_to_path(&path, &sync).unwrap();
        let restored = load_sync_file_from_path(&path).unwrap();

        assert_eq!(restored.last_writer.device_id, "desktop");
        assert_eq!(restored.shared.tabs.len(), 1);
        assert_eq!(restored.shared.tabs[0].name, "General");

        let _ = fs::remove_file(path);
    }

    #[test]
    fn sync_file_to_app_data_reassigns_unknown_tabs_and_ignores_deleted_records() {
        let sync = SyncFile {
            updated_at: "2026-04-07T20:41:12Z".into(),
            shared: SyncSharedData {
                tabs: vec![
                    SyncTabRecord {
                        id: "general".into(),
                        name: "General".into(),
                        priority: crate::model::TabPriority::Normal,
                        order: 0,
                        updated_at: "2026-04-07T20:41:12Z".into(),
                        deleted_at: None,
                    },
                    SyncTabRecord {
                        id: "old".into(),
                        name: "Old".into(),
                        priority: crate::model::TabPriority::Low,
                        order: 1,
                        updated_at: "2026-04-07T20:41:12Z".into(),
                        deleted_at: Some("2026-04-07T20:50:00Z".into()),
                    },
                ],
                tasks: vec![
                    SyncTaskRecord {
                        id: "task-1".into(),
                        text: "Active".into(),
                        status: SyncTaskStatus::Active,
                        tab_id: "missing".into(),
                        current: true,
                        order: 0,
                        created_at: "2026-04-07T20:10:00Z".into(),
                        updated_at: "2026-04-07T20:41:12Z".into(),
                        completed_at: None,
                        deleted_at: None,
                        extra_info: String::new(),
                        due_date: None,
                    },
                    SyncTaskRecord {
                        id: "task-2".into(),
                        text: "Deleted".into(),
                        status: SyncTaskStatus::Deleted,
                        tab_id: "general".into(),
                        current: false,
                        order: 1,
                        created_at: "2026-04-07T20:10:00Z".into(),
                        updated_at: "2026-04-07T20:41:12Z".into(),
                        completed_at: None,
                        deleted_at: Some("2026-04-07T20:50:00Z".into()),
                        extra_info: String::new(),
                        due_date: None,
                    },
                ],
                preferences: SyncPreferences {
                    theme_name: "forest".into(),
                    font_scale: 1.2,
                    accessibility_mode: true,
                    show_item_meta: false,
                    updated_at: "2026-04-07T20:41:12Z".into(),
                    ..SyncPreferences::default()
                },
            },
            ..SyncFile::default()
        };

        let restored = sync_file_to_app_data(&sync, Some(&Settings::default()));

        assert_eq!(restored.active.len(), 1);
        assert!(restored.history.is_empty());
        assert_eq!(restored.active[0].tab, crate::model::GENERAL_TAB_NAME);
        assert_eq!(restored.settings.theme_name, "forest");
        assert!(restored.settings.accessibility_mode);
        assert!(!restored.settings.show_item_meta);
        assert_eq!(restored.settings.tabs.len(), 1);
    }

    #[test]
    fn local_and_sync_stamp_conversion_support_date_and_datetime_inputs() {
        assert_eq!(
            local_stamp_to_sync("2026-04-07 20:41"),
            "2026-04-07T20:41:00Z"
        );
        assert_eq!(
            local_stamp_to_sync("2026-04-07"),
            "2026-04-07T00:00:00Z"
        );
        assert_eq!(sync_stamp_to_local("2026-04-07 20:41"), "2026-04-07 20:41");
        assert!(!sync_stamp_to_local("2026-04-07T20:41:12Z").is_empty());
    }

    #[test]
    fn merge_preferences_prefers_local_when_timestamps_match() {
        let local = SyncPreferences {
            theme_name: "forest".into(),
            updated_at: "2026-04-07T20:41:12Z".into(),
            ..SyncPreferences::default()
        };
        let remote = SyncPreferences {
            theme_name: "rose".into(),
            updated_at: "2026-04-07T20:41:12Z".into(),
            ..SyncPreferences::default()
        };

        let merged = merge_preferences(&local, &remote, "2026-04-07T20:00:00Z");
        assert_eq!(merged.theme_name, "forest");
    }
}
