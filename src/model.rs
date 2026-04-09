use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const APP_NAME: &str = "focus";
pub const DEFAULT_THEME_NAME: &str = "warm";
pub const GENERAL_TAB_NAME: &str = "General";
pub const SYNC_SCHEMA_VERSION: u32 = 1;
pub const DEFAULT_ITEM_TEXTS: [&str; 3] = [
    "Define the next concrete task",
    "Finish what is already in progress",
    "Avoid switching context without reason",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum TabPriority {
    High,
    #[default]
    Normal,
    Low,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TabSpec {
    #[serde(default)]
    pub sync_id: String,
    #[serde(default)]
    pub sync_updated_at: String,
    pub name: String,
    #[serde(default)]
    pub priority: TabPriority,
}

impl Default for TabSpec {
    fn default() -> Self {
        Self {
            sync_id: default_general_tab_sync_id(),
            sync_updated_at: String::new(),
            name: GENERAL_TAB_NAME.to_string(),
            priority: TabPriority::Normal,
        }
    }
}

impl TabSpec {
    pub fn normalized(mut self) -> Option<Self> {
        self.name = normalize_tab_name(&self.name);
        if self.name.is_empty() {
            return None;
        }
        if self.sync_id.trim().is_empty() {
            self.sync_id = tab_sync_id_from_name(&self.name);
        } else {
            self.sync_id = self.sync_id.trim().to_string();
        }
        self.sync_updated_at = self.sync_updated_at.trim().to_string();
        Some(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct TaskItem {
    pub id: u64,
    #[serde(default)]
    pub sync_id: String,
    #[serde(default)]
    pub sync_updated_at: String,
    pub text: String,
    #[serde(default)]
    pub done: bool,
    #[serde(default)]
    pub current: bool,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub completed_at: String,
    #[serde(default)]
    pub extra_info: String,
    #[serde(default)]
    pub due_date: String,
    #[serde(default = "default_task_tab")]
    pub tab: String,
}

impl TaskItem {
    pub fn new(id: u64, text: impl Into<String>) -> Self {
        Self {
            id,
            sync_id: task_sync_id_from_legacy_id(id),
            sync_updated_at: String::new(),
            text: text.into().trim().to_string(),
            done: false,
            current: false,
            created_at: String::new(),
            completed_at: String::new(),
            extra_info: String::new(),
            due_date: String::new(),
            tab: default_task_tab(),
        }
    }

    pub fn normalize_active(mut self, fallback_id: u64) -> Option<Self> {
        self.text = self.text.trim().to_string();
        if self.text.is_empty() {
            return None;
        }
        if self.id == 0 {
            self.id = fallback_id;
        }
        if self.sync_id.trim().is_empty() {
            self.sync_id = task_sync_id_from_legacy_id(self.id);
        } else {
            self.sync_id = self.sync_id.trim().to_string();
        }
        self.sync_updated_at = self.sync_updated_at.trim().to_string();
        self.done = false;
        self.completed_at.clear();
        self.tab = normalize_tab_name(&self.tab);
        if self.tab.is_empty() {
            self.tab = default_task_tab();
        }
        Some(self)
    }

    pub fn normalize_history(mut self, fallback_id: u64) -> Option<Self> {
        self.text = self.text.trim().to_string();
        if self.text.is_empty() {
            return None;
        }
        if self.id == 0 {
            self.id = fallback_id;
        }
        if self.sync_id.trim().is_empty() {
            self.sync_id = task_sync_id_from_legacy_id(self.id);
        } else {
            self.sync_id = self.sync_id.trim().to_string();
        }
        self.sync_updated_at = self.sync_updated_at.trim().to_string();
        self.done = true;
        self.current = false;
        self.tab = normalize_tab_name(&self.tab);
        if self.tab.is_empty() {
            self.tab = default_task_tab();
        }
        Some(self)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Settings {
    #[serde(default = "default_tabs")]
    pub tabs: Vec<TabSpec>,
    #[serde(default = "default_theme_name")]
    pub theme_name: String,
    #[serde(default)]
    pub custom_palette: BTreeMap<String, String>,
    #[serde(default = "default_font_scale")]
    pub font_scale: f32,
    #[serde(default)]
    pub accessibility_mode: bool,
    #[serde(default = "default_show_item_meta")]
    pub show_item_meta: bool,
    #[serde(default = "default_tab_visible_count")]
    pub tab_visible_count: u8,
    #[serde(default = "default_always_on_top")]
    pub always_on_top: bool,
    #[serde(default)]
    pub preferences_updated_at: String,
    #[serde(default)]
    pub sync: SyncConfig,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            tabs: default_tabs(),
            theme_name: default_theme_name(),
            custom_palette: BTreeMap::new(),
            font_scale: default_font_scale(),
            accessibility_mode: false,
            show_item_meta: default_show_item_meta(),
            tab_visible_count: default_tab_visible_count(),
            always_on_top: default_always_on_top(),
            preferences_updated_at: String::new(),
            sync: SyncConfig::default(),
            extra: BTreeMap::new(),
        }
    }
}

impl Settings {
    pub fn normalized(mut self) -> Self {
        self.tabs = normalize_tabs(self.tabs);
        if self.theme_name.trim().is_empty() {
            self.theme_name = default_theme_name();
        }
        self.font_scale = self.font_scale.clamp(0.8, 1.8);
        self.tab_visible_count = self.tab_visible_count.clamp(2, 12);
        self.preferences_updated_at = self.preferences_updated_at.trim().to_string();
        self.sync = self.sync.normalized();
        self.custom_palette = self
            .custom_palette
            .into_iter()
            .filter_map(|(key, value)| {
                let value = value.trim().to_ascii_lowercase();
                if is_hex_color(&value) {
                    Some((key, value))
                } else {
                    None
                }
            })
            .collect();
        self
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum SyncProvider {
    #[default]
    LocalFile,
    GoogleDrive,
}

impl SyncProvider {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::LocalFile => "local_file",
            Self::GoogleDrive => "google_drive",
        }
    }

    pub fn from_str(value: &str) -> Self {
        match value.trim().to_ascii_lowercase().as_str() {
            "google_drive" => Self::GoogleDrive,
            _ => Self::LocalFile,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct SyncConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub provider: SyncProvider,
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub device_id: String,
    #[serde(default)]
    pub google_drive_client_id: String,
    #[serde(default)]
    pub google_drive_file_id: String,
    #[serde(default)]
    pub last_sync_at: String,
}

impl SyncConfig {
    pub fn normalized(mut self) -> Self {
        self.path = self.path.trim().to_string();
        self.device_id = self.device_id.trim().to_string();
        self.google_drive_client_id = self.google_drive_client_id.trim().to_string();
        self.google_drive_file_id = self.google_drive_file_id.trim().to_string();
        self.last_sync_at = self.last_sync_at.trim().to_string();
        self
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct SyncWriter {
    #[serde(default)]
    pub device_id: String,
    #[serde(default)]
    pub app_id: String,
    #[serde(default)]
    pub app_version: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum SyncTaskStatus {
    #[default]
    Active,
    Completed,
    Deleted,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct SyncTabRecord {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub priority: TabPriority,
    #[serde(default)]
    pub order: i32,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub deleted_at: Option<String>,
}

impl SyncTabRecord {
    pub fn normalized(mut self) -> Option<Self> {
        self.id = self.id.trim().to_string();
        self.name = normalize_tab_name(&self.name);
        self.updated_at = self.updated_at.trim().to_string();
        self.deleted_at = self.deleted_at.map(|value| value.trim().to_string());
        if self.id.is_empty() || self.name.is_empty() {
            return None;
        }
        Some(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct SyncTaskRecord {
    pub id: String,
    pub text: String,
    #[serde(default)]
    pub status: SyncTaskStatus,
    #[serde(default)]
    pub tab_id: String,
    #[serde(default)]
    pub current: bool,
    #[serde(default)]
    pub order: i32,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub completed_at: Option<String>,
    #[serde(default)]
    pub deleted_at: Option<String>,
    #[serde(default)]
    pub extra_info: String,
    #[serde(default)]
    pub due_date: Option<String>,
}

impl SyncTaskRecord {
    pub fn normalized(mut self) -> Option<Self> {
        self.id = self.id.trim().to_string();
        self.text = self.text.trim().to_string();
        self.tab_id = self.tab_id.trim().to_string();
        self.created_at = self.created_at.trim().to_string();
        self.updated_at = self.updated_at.trim().to_string();
        self.completed_at = self.completed_at.map(|value| value.trim().to_string());
        self.deleted_at = self.deleted_at.map(|value| value.trim().to_string());
        self.extra_info = self.extra_info.trim().to_string();
        self.due_date = self.due_date.map(|value| value.trim().to_string());
        if self.id.is_empty() || self.text.is_empty() {
            return None;
        }
        Some(self)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SyncPreferences {
    #[serde(default = "default_theme_name")]
    pub theme_name: String,
    #[serde(default)]
    pub custom_palette: BTreeMap<String, String>,
    #[serde(default = "default_font_scale")]
    pub font_scale: f32,
    #[serde(default)]
    pub accessibility_mode: bool,
    #[serde(default = "default_show_item_meta")]
    pub show_item_meta: bool,
    #[serde(default)]
    pub updated_at: String,
}

impl Default for SyncPreferences {
    fn default() -> Self {
        Self {
            theme_name: default_theme_name(),
            custom_palette: BTreeMap::new(),
            font_scale: default_font_scale(),
            accessibility_mode: false,
            show_item_meta: default_show_item_meta(),
            updated_at: String::new(),
        }
    }
}

impl SyncPreferences {
    pub fn normalized(mut self) -> Self {
        if self.theme_name.trim().is_empty() {
            self.theme_name = default_theme_name();
        }
        self.font_scale = self.font_scale.clamp(0.8, 1.8);
        self.updated_at = self.updated_at.trim().to_string();
        self.custom_palette = self
            .custom_palette
            .into_iter()
            .filter_map(|(key, value)| {
                let value = value.trim().to_ascii_lowercase();
                if is_hex_color(&value) {
                    Some((key, value))
                } else {
                    None
                }
            })
            .collect();
        self
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct SyncSharedData {
    #[serde(default)]
    pub tabs: Vec<SyncTabRecord>,
    #[serde(default)]
    pub tasks: Vec<SyncTaskRecord>,
    #[serde(default)]
    pub preferences: SyncPreferences,
}

impl SyncSharedData {
    pub fn normalized(mut self) -> Self {
        let mut seen_tabs = BTreeSet::new();
        self.tabs = self
            .tabs
            .into_iter()
            .filter_map(SyncTabRecord::normalized)
            .filter(|tab| seen_tabs.insert(tab.id.clone()))
            .collect();

        let mut seen_tasks = BTreeSet::new();
        self.tasks = self
            .tasks
            .into_iter()
            .filter_map(SyncTaskRecord::normalized)
            .filter(|task| seen_tasks.insert(task.id.clone()))
            .collect();

        self.preferences = self.preferences.normalized();
        self
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SyncFile {
    #[serde(default = "default_sync_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub last_writer: SyncWriter,
    #[serde(default)]
    pub shared: SyncSharedData,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl Default for SyncFile {
    fn default() -> Self {
        Self {
            schema_version: default_sync_schema_version(),
            updated_at: String::new(),
            last_writer: SyncWriter::default(),
            shared: SyncSharedData::default(),
            extra: BTreeMap::new(),
        }
    }
}

impl SyncFile {
    pub fn normalized(mut self) -> Self {
        if self.schema_version == 0 {
            self.schema_version = default_sync_schema_version();
        }
        self.updated_at = self.updated_at.trim().to_string();
        self.last_writer.device_id = self.last_writer.device_id.trim().to_string();
        self.last_writer.app_id = self.last_writer.app_id.trim().to_string();
        self.last_writer.app_version = self.last_writer.app_version.trim().to_string();
        self.shared = self.shared.normalized();
        self
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct AppData {
    #[serde(default)]
    pub active: Vec<TaskItem>,
    #[serde(default)]
    pub history: Vec<TaskItem>,
    #[serde(default)]
    pub settings: Settings,
}

impl AppData {
    pub fn with_default_items(created_at: &str) -> Self {
        let active = DEFAULT_ITEM_TEXTS
            .iter()
            .enumerate()
            .map(|(index, text)| {
                let mut item = TaskItem::new(index as u64 + 1, *text);
                item.created_at = created_at.to_string();
                item
            })
            .collect();

        Self {
            active,
            history: Vec::new(),
            settings: Settings::default(),
        }
    }

    pub fn normalized(mut self) -> Self {
        self.active = self
            .active
            .into_iter()
            .enumerate()
            .filter_map(|(index, item)| item.normalize_active(index as u64 + 1))
            .collect();
        self.history = self
            .history
            .into_iter()
            .enumerate()
            .filter_map(|(index, item)| item.normalize_history(index as u64 + 1000))
            .take(250)
            .collect();
        self.settings = self.settings.normalized();
        self
    }

    pub fn next_id(&self) -> u64 {
        self.active
            .iter()
            .chain(self.history.iter())
            .map(|item| item.id)
            .max()
            .unwrap_or(0)
            + 1
    }
}

pub fn default_theme_name() -> String {
    DEFAULT_THEME_NAME.to_string()
}

pub fn default_sync_schema_version() -> u32 {
    SYNC_SCHEMA_VERSION
}

pub fn default_task_tab() -> String {
    GENERAL_TAB_NAME.to_string()
}

pub fn default_general_tab_sync_id() -> String {
    "general".to_string()
}

pub fn default_tabs() -> Vec<TabSpec> {
    vec![TabSpec::default()]
}

pub fn default_font_scale() -> f32 {
    1.0
}

pub fn default_show_item_meta() -> bool {
    true
}

pub fn default_tab_visible_count() -> u8 {
    5
}

pub fn default_always_on_top() -> bool {
    true
}

pub fn normalize_tabs(tabs: Vec<TabSpec>) -> Vec<TabSpec> {
    let mut seen = BTreeSet::new();
    let mut normalized: Vec<TabSpec> = tabs
        .into_iter()
        .filter_map(TabSpec::normalized)
        .filter(|tab| seen.insert(tab.sync_id.clone()))
        .collect();

    if normalized.is_empty() {
        return default_tabs();
    }

    if !normalized.iter().any(|tab| tab.name == GENERAL_TAB_NAME) {
        normalized.insert(0, TabSpec::default());
    }

    normalized
}

pub fn normalize_tab_name(value: &str) -> String {
    let collapsed = value.split_whitespace().collect::<Vec<_>>().join(" ");
    let trimmed = collapsed.trim();
    trimmed.chars().take(40).collect()
}

pub fn tab_sync_id_from_name(value: &str) -> String {
    let normalized = normalize_tab_name(value);
    if normalized.eq_ignore_ascii_case(GENERAL_TAB_NAME) {
        return default_general_tab_sync_id();
    }

    let mut slug = String::new();
    let mut last_dash = false;
    for ch in normalized.chars().flat_map(|ch| ch.to_lowercase()) {
        if ch.is_ascii_alphanumeric() {
            slug.push(ch);
            last_dash = false;
        } else if !last_dash {
            slug.push('-');
            last_dash = true;
        }
    }
    let trimmed = slug.trim_matches('-');
    if trimmed.is_empty() {
        default_general_tab_sync_id()
    } else {
        trimmed.to_string()
    }
}

pub fn task_sync_id_from_legacy_id(id: u64) -> String {
    format!("task-{id}")
}

fn is_hex_color(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7 && bytes[0] == b'#' && bytes[1..].iter().all(|byte| byte.is_ascii_hexdigit())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_tab_names_and_inserts_general() {
        let tabs = vec![
            TabSpec {
                sync_id: String::new(),
                sync_updated_at: String::new(),
                name: "   Work   Sprint   ".into(),
                priority: TabPriority::High,
            },
            TabSpec {
                sync_id: String::new(),
                sync_updated_at: String::new(),
                name: String::new(),
                priority: TabPriority::Low,
            },
        ];

        let normalized = normalize_tabs(tabs);

        assert_eq!(normalized.len(), 2);
        assert_eq!(normalized[0].name, GENERAL_TAB_NAME);
        assert_eq!(normalized[1].name, "Work Sprint");
    }

    #[test]
    fn normalizes_active_and_history_items() {
        let active = TaskItem {
            id: 0,
            sync_id: String::new(),
            sync_updated_at: String::new(),
            text: "  Ship Rust port  ".into(),
            done: true,
            current: true,
            created_at: String::new(),
            completed_at: "2026-04-05 13:00".into(),
            extra_info: String::new(),
            due_date: String::new(),
            tab: "   ".into(),
        }
        .normalize_active(7)
        .unwrap();

        assert_eq!(active.id, 7);
        assert_eq!(active.text, "Ship Rust port");
        assert!(!active.done);
        assert!(active.current);
        assert!(active.completed_at.is_empty());
        assert_eq!(active.tab, GENERAL_TAB_NAME);

        let history = TaskItem::new(0, " Done item ")
            .normalize_history(1002)
            .unwrap();
        assert_eq!(history.id, 1002);
        assert!(history.done);
        assert!(!history.current);
    }

    #[test]
    fn deserializes_python_compatible_payload() {
        let raw = r##"
        {
          "active": [
            {
              "id": 1,
              "text": "Define the next concrete task",
              "done": false,
              "current": true,
              "created_at": "2026-04-05 12:00",
              "completed_at": "",
              "extra_info": "",
              "due_date": "",
              "tab": "General"
            }
          ],
          "history": [],
          "settings": {
            "tabs": [{"name": "General", "priority": "normal"}],
            "theme_name": "warm",
            "always_on_top": true,
            "show_item_meta": true
          }
        }
        "##;

        let data: AppData = serde_json::from_str(raw).unwrap();
        let normalized = data.normalized();

        assert_eq!(normalized.active.len(), 1);
        assert_eq!(normalized.active[0].text, "Define the next concrete task");
        assert_eq!(normalized.settings.tabs[0].name, GENERAL_TAB_NAME);
        assert!(normalized.settings.always_on_top);
    }

    #[test]
    fn builds_default_items_payload() {
        let data = AppData::with_default_items("2026-04-05 12:00");

        assert_eq!(data.active.len(), 3);
        assert_eq!(data.active[0].id, 1);
        assert_eq!(data.active[0].created_at, "2026-04-05 12:00");
        assert_eq!(data.settings.tabs[0].name, GENERAL_TAB_NAME);
    }

    #[test]
    fn normalizes_local_sync_config() {
        let config = SyncConfig {
            enabled: true,
            provider: SyncProvider::LocalFile,
            path: "  C:/sync/focus-sync.json  ".into(),
            device_id: "  desktop-win11  ".into(),
            google_drive_client_id: "  desktop-client-id.apps.googleusercontent.com  ".into(),
            google_drive_file_id: "  1abCDefGhIJklmnOP  ".into(),
            last_sync_at: "  2026-04-07T20:41:12Z ".into(),
        }
        .normalized();

        assert!(config.enabled);
        assert_eq!(config.provider, SyncProvider::LocalFile);
        assert_eq!(config.path, "C:/sync/focus-sync.json");
        assert_eq!(config.device_id, "desktop-win11");
        assert_eq!(
            config.google_drive_client_id,
            "desktop-client-id.apps.googleusercontent.com"
        );
        assert_eq!(config.google_drive_file_id, "1abCDefGhIJklmnOP");
        assert_eq!(config.last_sync_at, "2026-04-07T20:41:12Z");
    }

    #[test]
    fn deserializes_shared_sync_payload() {
        let raw = r##"
        {
          "schema_version": 1,
          "updated_at": "2026-04-07T20:41:12Z",
          "last_writer": {
            "device_id": "desktop-win11-ina",
            "app_id": "focus-desktop",
            "app_version": "0.1.0"
          },
          "shared": {
            "tabs": [
              {
                "id": "general",
                "name": "General",
                "priority": "normal",
                "order": 0,
                "updated_at": "2026-04-07T20:41:12Z",
                "deleted_at": null
              }
            ],
            "tasks": [
              {
                "id": "tsk_01",
                "text": "Ship Android sync",
                "status": "active",
                "tab_id": "general",
                "current": true,
                "order": 0,
                "created_at": "2026-04-07T20:10:00Z",
                "updated_at": "2026-04-07T20:41:12Z",
                "completed_at": null,
                "deleted_at": null,
                "extra_info": "",
                "due_date": null
              }
            ],
            "preferences": {
              "theme_name": "warm",
              "font_scale": 1.0,
              "accessibility_mode": false,
              "show_item_meta": true,
              "updated_at": "2026-04-07T20:41:12Z"
            }
          }
        }
        "##;

        let file: SyncFile = serde_json::from_str(raw).unwrap();
        let normalized = file.normalized();

        assert_eq!(normalized.schema_version, 1);
        assert_eq!(normalized.shared.tabs.len(), 1);
        assert_eq!(normalized.shared.tabs[0].id, "general");
        assert_eq!(normalized.shared.tasks.len(), 1);
        assert_eq!(normalized.shared.tasks[0].status, SyncTaskStatus::Active);
        assert!(normalized.shared.tasks[0].current);
    }

    #[test]
    fn sync_provider_round_trips_strings() {
        assert_eq!(SyncProvider::from_str("local_file"), SyncProvider::LocalFile);
        assert_eq!(SyncProvider::from_str("google_drive"), SyncProvider::GoogleDrive);
        assert_eq!(SyncProvider::from_str(" GOOGLE_DRIVE "), SyncProvider::GoogleDrive);
        assert_eq!(SyncProvider::GoogleDrive.as_str(), "google_drive");
        assert_eq!(SyncProvider::LocalFile.as_str(), "local_file");
    }

    #[test]
    fn settings_normalization_clamps_and_filters_custom_palette() {
        let mut custom_palette = BTreeMap::new();
        custom_palette.insert("accent".into(), "  #ABCDEF  ".into());
        custom_palette.insert("broken".into(), "blue".into());

        let settings = Settings {
            tabs: vec![],
            theme_name: "   ".into(),
            custom_palette,
            font_scale: 4.0,
            accessibility_mode: false,
            show_item_meta: true,
            tab_visible_count: 99,
            always_on_top: true,
            preferences_updated_at: " 2026-04-07T20:41:12Z ".into(),
            sync: SyncConfig::default(),
            extra: BTreeMap::new(),
        }
        .normalized();

        assert_eq!(settings.theme_name, DEFAULT_THEME_NAME);
        assert_eq!(settings.font_scale, 1.8);
        assert_eq!(settings.tab_visible_count, 12);
        assert_eq!(
            settings.custom_palette.get("accent").map(String::as_str),
            Some("#abcdef")
        );
        assert!(!settings.custom_palette.contains_key("broken"));
        assert_eq!(settings.preferences_updated_at, "2026-04-07T20:41:12Z");
        assert_eq!(settings.tabs[0].name, GENERAL_TAB_NAME);
    }

    #[test]
    fn app_data_normalization_limits_history_and_preserves_next_id() {
        let mut data = AppData::default();
        data.active = vec![
            TaskItem::new(5, "Keep"),
            TaskItem::new(12, "Highest active"),
        ];
        data.history = (0..260)
            .map(|index| {
                let mut item = TaskItem::new(index + 100, format!("Done {index}"));
                item.done = true;
                item.completed_at = "2026-04-05 12:00".into();
                item
            })
            .collect();

        let normalized = data.normalized();

        assert_eq!(normalized.history.len(), 250);
        assert_eq!(normalized.next_id(), 350);
    }

    #[test]
    fn tab_and_task_sync_ids_are_stable() {
        assert_eq!(tab_sync_id_from_name("General"), "general");
        assert_eq!(tab_sync_id_from_name(" Android Ideas "), "android-ideas");
        assert_eq!(tab_sync_id_from_name("###"), "general");
        assert_eq!(task_sync_id_from_legacy_id(42), "task-42");
    }

    #[test]
    fn sync_shared_data_normalization_deduplicates_tabs_and_tasks() {
        let shared = SyncSharedData {
            tabs: vec![
                SyncTabRecord {
                    id: "general".into(),
                    name: "General".into(),
                    priority: TabPriority::Normal,
                    order: 0,
                    updated_at: "2026-04-07T20:41:12Z".into(),
                    deleted_at: None,
                },
                SyncTabRecord {
                    id: "general".into(),
                    name: "Duplicate".into(),
                    priority: TabPriority::High,
                    order: 1,
                    updated_at: "2026-04-07T20:42:12Z".into(),
                    deleted_at: None,
                },
            ],
            tasks: vec![
                SyncTaskRecord {
                    id: "task-1".into(),
                    text: "One".into(),
                    status: SyncTaskStatus::Active,
                    tab_id: "general".into(),
                    current: false,
                    order: 0,
                    created_at: "2026-04-07T20:10:00Z".into(),
                    updated_at: "2026-04-07T20:41:12Z".into(),
                    completed_at: None,
                    deleted_at: None,
                    extra_info: String::new(),
                    due_date: None,
                },
                SyncTaskRecord {
                    id: "task-1".into(),
                    text: "Duplicate".into(),
                    status: SyncTaskStatus::Completed,
                    tab_id: "general".into(),
                    current: false,
                    order: 1,
                    created_at: "2026-04-07T20:10:00Z".into(),
                    updated_at: "2026-04-07T20:42:12Z".into(),
                    completed_at: Some("2026-04-07T20:42:12Z".into()),
                    deleted_at: None,
                    extra_info: String::new(),
                    due_date: None,
                },
            ],
            preferences: SyncPreferences::default(),
        }
        .normalized();

        assert_eq!(shared.tabs.len(), 1);
        assert_eq!(shared.tasks.len(), 1);
        assert_eq!(shared.tabs[0].name, "General");
        assert_eq!(shared.tasks[0].text, "One");
    }
}
