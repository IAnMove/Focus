use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const APP_NAME: &str = "focus";
pub const DEFAULT_THEME_NAME: &str = "warm";
pub const GENERAL_TAB_NAME: &str = "General";
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
    pub name: String,
    #[serde(default)]
    pub priority: TabPriority,
}

impl Default for TabSpec {
    fn default() -> Self {
        Self {
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
        Some(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct TaskItem {
    pub id: u64,
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

pub fn default_task_tab() -> String {
    GENERAL_TAB_NAME.to_string()
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
        .filter(|tab| seen.insert(tab.name.clone()))
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
                name: "   Work   Sprint   ".into(),
                priority: TabPriority::High,
            },
            TabSpec {
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
}
