mod audio;
mod model;
mod storage;

use std::cell::RefCell;
use std::path::PathBuf;
use std::process::Command;
use std::rc::Rc;
use std::time::Duration;

use chrono::{Datelike, Local, NaiveDate, NaiveDateTime};
use slint::winit_030::{WinitWindowAccessor, winit};
use slint::{Color, ModelRc, Timer, TimerMode, VecModel, Weak};

slint::include_modules!();

const PROJECT_REPO_URL: &str = "https://github.com/IAnMove/Focus";
const BUILD_COMMIT: &str = match option_env!("GIT_COMMIT_HASH") {
    Some(value) => value,
    None => "dev",
};

#[derive(Debug)]
struct AppState {
    data: model::AppData,
    active_tab: String,
    open_task_menu_id: Option<u64>,
    tab_window_start: usize,
    visible_tab_count: usize,
    history_visible: bool,
    tools_visible: bool,
    draft_visible: bool,
    draft_title: String,
    draft_extra: String,
    draft_due_date: String,
    draft_has_due: bool,
    draft_message: String,
    draft_tab_name: String,
    transfer_path: String,
    sync_enabled: bool,
    sync_path: String,
    sync_device_id: String,
    sync_message: String,
    startup_enabled: bool,
    startup_message: String,
    tools_message: String,
    editing_task_id: Option<u64>,
    undo_item: Option<model::TaskItem>,
    store: Option<storage::DataStore>,
}

#[derive(Debug, Clone, Copy)]
struct ThemePalette {
    bg: &'static str,
    panel: &'static str,
    panel_alt: &'static str,
    panel_soft: &'static str,
    text_main: &'static str,
    text_muted: &'static str,
    accent: &'static str,
    border: &'static str,
    accent_warm: &'static str,
}

impl AppState {
    fn new(data: model::AppData, store: Option<storage::DataStore>) -> Self {
        let sync_enabled = data.settings.sync.enabled;
        let sync_path = data.settings.sync.path.clone();
        let sync_device_id = data.settings.sync.device_id.clone();
        let startup_enabled = storage::startup_enabled().unwrap_or(false);

        Self {
            data,
            active_tab: "All".to_string(),
            open_task_menu_id: None,
            tab_window_start: 0,
            visible_tab_count: 3,
            history_visible: false,
            tools_visible: false,
            draft_visible: false,
            draft_title: String::new(),
            draft_extra: String::new(),
            draft_due_date: String::new(),
            draft_has_due: false,
            draft_message: String::new(),
            draft_tab_name: String::new(),
            transfer_path: storage::default_export_path().display().to_string(),
            sync_enabled,
            sync_path,
            sync_device_id,
            sync_message: String::new(),
            startup_enabled,
            startup_message: String::new(),
            tools_message: String::new(),
            editing_task_id: None,
            undo_item: None,
            store,
        }
    }

    fn save(&mut self) {
        if let Some(store) = &self.store {
            let _ = store.save(&self.data);
        }

        self.push_sync_if_enabled();
    }

    fn clear_draft(&mut self) {
        self.draft_title.clear();
        self.draft_extra.clear();
        self.draft_due_date.clear();
        self.draft_has_due = false;
        self.draft_message.clear();
        self.editing_task_id = None;
        self.draft_visible = false;
        self.open_task_menu_id = None;
    }

    fn clear_tab_draft(&mut self) {
        self.draft_tab_name.clear();
    }

    fn toggle_task_menu(&mut self, task_id: u64) {
        self.open_task_menu_id = if self.open_task_menu_id == Some(task_id) {
            None
        } else {
            Some(task_id)
        };
    }

    fn set_tools_message(&mut self, message: impl Into<String>) {
        self.tools_message = message.into();
    }

    fn set_sync_message(&mut self, message: impl Into<String>) {
        self.sync_message = message.into();
    }

    fn set_startup_message(&mut self, message: impl Into<String>) {
        self.startup_message = message.into();
    }

    fn touch_all_active_tasks(&mut self) {
        let stamp = storage::now_sync_stamp();
        for task in &mut self.data.active {
            task.sync_updated_at = stamp.clone();
        }
    }

    fn touch_tab(&mut self, name: &str) {
        let stamp = storage::now_sync_stamp();
        if let Some(tab) = self.data.settings.tabs.iter_mut().find(|tab| tab.name == name) {
            tab.sync_updated_at = stamp;
        }
    }

    fn touch_all_tabs(&mut self) {
        let stamp = storage::now_sync_stamp();
        for tab in &mut self.data.settings.tabs {
            tab.sync_updated_at = stamp.clone();
        }
    }

    fn touch_preferences(&mut self) {
        self.data.settings.preferences_updated_at = storage::now_sync_stamp();
    }

    fn push_sync_if_enabled(&mut self) {
        if !self.sync_enabled {
            return;
        }

        let path = self.sync_path.trim();
        if path.is_empty() {
            self.set_sync_message("Sync enabled but no path configured");
            return;
        }

        let device_id = self.sync_device_id.trim();
        if device_id.is_empty() {
            self.set_sync_message("Sync enabled but device id is empty");
            return;
        }

        let path = PathBuf::from(path);
        let local_sync = storage::app_data_to_sync_file(&self.data, device_id);
        let merged_sync = match storage::load_sync_file_from_path(&path) {
            Ok(remote_sync) => storage::merge_sync_files(
                &local_sync,
                &remote_sync,
                &self.data.settings.sync.last_sync_at,
                device_id,
            ),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => local_sync,
            Err(error) => {
                self.set_sync_message(format!("Sync failed: {}", error));
                return;
            }
        };

        match storage::save_sync_file_to_path(&path, &merged_sync) {
            Ok(()) => {
                let mut local_settings = self.data.settings.clone();
                local_settings.sync.enabled = true;
                local_settings.sync.path = self.sync_path.clone();
                local_settings.sync.device_id = self.sync_device_id.clone();
                local_settings.sync.last_sync_at = storage::now_sync_stamp();
                let sync_config = local_settings.sync.clone();
                self.data = storage::sync_file_to_app_data(&merged_sync, Some(&local_settings));
                self.data.settings.sync = sync_config;
                if let Some(store) = &self.store {
                    let _ = store.save(&self.data);
                }
                self.set_sync_message(format!("Synced to {}", path.display()));
            }
            Err(error) => {
                self.set_sync_message(format!("Sync failed: {}", error));
            }
        }
    }

    fn submit_draft(&mut self) -> bool {
        let text = self.draft_title.trim();
        if text.is_empty() {
            self.draft_message = "Task title cannot be empty".to_string();
            return false;
        }

        let due_date = match normalize_due_input(
            if self.draft_has_due {
                self.draft_due_date.trim()
            } else {
                ""
            },
        ) {
            Ok(value) => value,
            Err(message) => {
                self.draft_message = message;
                return false;
            }
        };

        if let Some(task_id) = self.editing_task_id {
            if let Some(task) = self.data.active.iter_mut().find(|task| task.id == task_id) {
                task.text = text.to_string();
                task.extra_info = self.draft_extra.trim().to_string();
                task.due_date = due_date;
                task.sync_updated_at = storage::now_sync_stamp();
            }
        } else {
            let mut item = model::TaskItem::new(self.data.next_id(), text);
            item.created_at = storage::now_stamp();
            item.extra_info = self.draft_extra.trim().to_string();
            item.due_date = due_date;
            item.sync_updated_at = storage::now_sync_stamp();
            item.tab = if self.active_tab == "All" {
                model::GENERAL_TAB_NAME.to_string()
            } else {
                self.active_tab.clone()
            };
            self.data.active.push(item);
        }

        self.clear_draft();
        self.save();
        true
    }

    fn start_edit(&mut self, task_id: u64) {
        if let Some(task) = self.data.active.iter().find(|task| task.id == task_id) {
            self.editing_task_id = Some(task_id);
            self.draft_title = task.text.clone();
            self.draft_extra = task.extra_info.clone();
            self.draft_due_date = task.due_date.clone();
            self.draft_has_due = !task.due_date.trim().is_empty();
            self.draft_message.clear();
            self.draft_visible = true;
            self.history_visible = false;
            self.tools_visible = false;
            self.open_task_menu_id = None;
        }
    }

    fn delete_task(&mut self, task_id: u64) -> bool {
        let before = self.data.active.len();
        self.data.active.retain(|task| task.id != task_id);
        let changed = self.data.active.len() != before;
        if changed {
            if self.editing_task_id == Some(task_id) {
                self.clear_draft();
            }
            self.touch_all_active_tasks();
            self.open_task_menu_id = None;
            self.save();
        }
        changed
    }

    fn toggle_current(&mut self, task_id: u64) -> bool {
        let mut found = false;
        let mut should_promote = false;

        for task in &self.data.active {
            if task.id == task_id {
                found = true;
                should_promote = !task.current;
                break;
            }
        }

        if !found {
            return false;
        }

        if should_promote {
            let stamp = storage::now_sync_stamp();
            for task in &mut self.data.active {
                let next = task.id == task_id;
                if task.current != next {
                    task.current = next;
                    task.sync_updated_at = stamp.clone();
                }
            }
            if let Some(index) = self.data.active.iter().position(|task| task.id == task_id) {
                let task = self.data.active.remove(index);
                self.data.active.insert(0, task);
            }
        } else if let Some(task) = self.data.active.iter_mut().find(|task| task.id == task_id) {
            task.current = false;
            task.sync_updated_at = storage::now_sync_stamp();
        }

        self.touch_all_active_tasks();
        self.open_task_menu_id = None;
        self.save();
        true
    }

    fn finalize_pending_completion(&mut self) -> bool {
        let Some(item) = self.undo_item.take() else {
            return false;
        };
        self.data.history.push(item);
        self.data.history.truncate(250);
        self.open_task_menu_id = None;
        self.save();
        true
    }

    fn complete_task(&mut self, task_id: u64) -> bool {
        self.finalize_pending_completion();

        let Some(index) = self.data.active.iter().position(|task| task.id == task_id) else {
            return false;
        };

        let mut item = self.data.active.remove(index);
        item.done = true;
        item.current = false;
        item.completed_at = storage::now_stamp();
        item.sync_updated_at = storage::now_sync_stamp();
        self.undo_item = Some(item);
        self.touch_all_active_tasks();
        self.open_task_menu_id = None;

        if self.editing_task_id == Some(task_id) {
            self.clear_draft();
        }

        self.save();
        true
    }

    fn undo_complete(&mut self) -> bool {
        let Some(mut item) = self.undo_item.take() else {
            return false;
        };

        item.done = false;
        item.completed_at.clear();
        item.sync_updated_at = storage::now_sync_stamp();
        self.data.active.insert(0, item);
        self.open_task_menu_id = None;
        self.touch_all_active_tasks();
        self.save();
        true
    }

    fn select_tab(&mut self, name: String) {
        self.active_tab = name;
        self.ensure_active_tab_visible();
        self.history_visible = false;
        self.tools_visible = false;
        self.open_task_menu_id = None;
    }

    fn toggle_history(&mut self) {
        self.history_visible = !self.history_visible;
        if self.history_visible {
            self.tools_visible = false;
            self.draft_visible = false;
            self.open_task_menu_id = None;
        }
    }

    fn toggle_tools(&mut self) {
        self.tools_visible = !self.tools_visible;
        if self.tools_visible {
            self.history_visible = false;
            self.draft_visible = false;
            self.open_task_menu_id = None;
        }
    }

    fn update_tab_strip_width(&mut self, width: f32) {
        let configured = self.data.settings.tab_visible_count.clamp(2, 12) as usize;
        self.visible_tab_count = if width < 380.0 {
            1
        } else if width < 470.0 {
            2
        } else if width < 620.0 {
            3
        } else {
            configured
        };
        self.clamp_tab_window();
        self.ensure_active_tab_visible();
    }

    fn clamp_tab_window(&mut self) {
        let tab_len = self.data.settings.tabs.len();
        let max_start = tab_len.saturating_sub(self.visible_tab_count.max(1));
        self.tab_window_start = self.tab_window_start.min(max_start);
    }

    fn ensure_active_tab_visible(&mut self) {
        if self.active_tab == "All" {
            self.clamp_tab_window();
            return;
        }

        let Some(index) = self
            .data
            .settings
            .tabs
            .iter()
            .position(|tab| tab.name == self.active_tab)
        else {
            self.clamp_tab_window();
            return;
        };

        if index < self.tab_window_start {
            self.tab_window_start = index;
        } else if index >= self.tab_window_start + self.visible_tab_count.max(1) {
            self.tab_window_start = index + 1 - self.visible_tab_count.max(1);
        }

        self.clamp_tab_window();
    }

    fn shift_tab_window(&mut self, direction: isize) {
        if self.data.settings.tabs.is_empty() {
            return;
        }

        let names: Vec<String> = self
            .data
            .settings
            .tabs
            .iter()
            .map(|tab| tab.name.clone())
            .collect();

        let current_index = if self.active_tab == "All" {
            if direction > 0 { -1 } else { 0 }
        } else {
            names
                .iter()
                .position(|name| name == &self.active_tab)
                .map(|index| index as isize)
                .unwrap_or(if direction > 0 { -1 } else { 0 })
        };

        let target_index = (current_index + direction).clamp(0, names.len() as isize - 1) as usize;
        self.active_tab = names[target_index].clone();
        self.ensure_active_tab_visible();
        self.history_visible = false;
        self.tools_visible = false;
    }

    fn restore_history(&mut self, task_id: u64) -> bool {
        let Some(index) = self.data.history.iter().position(|task| task.id == task_id) else {
            return false;
        };

        let mut item = self.data.history.remove(index);
        item.done = false;
        item.current = false;
        item.completed_at.clear();
        item.sync_updated_at = storage::now_sync_stamp();
        self.data.active.push(item);
        self.history_visible = false;
        self.touch_all_active_tasks();
        self.save();
        true
    }

    fn move_task(&mut self, task_id: u64, delta: isize) -> bool {
        let Some(index) = self.data.active.iter().position(|task| task.id == task_id) else {
            return false;
        };

        let target = index as isize + delta;
        if target < 0 || target >= self.data.active.len() as isize {
            return false;
        }

        self.data.active.swap(index, target as usize);
        self.touch_all_active_tasks();
        self.open_task_menu_id = None;
        self.save();
        true
    }

    fn cycle_task_tab(&mut self, task_id: u64) -> bool {
        let tabs = &self.data.settings.tabs;
        if tabs.is_empty() {
            return false;
        }

        let Some(task) = self.data.active.iter_mut().find(|task| task.id == task_id) else {
            return false;
        };

        let current_index = tabs
            .iter()
            .position(|tab| tab.name == task.tab)
            .unwrap_or(0);
        let next_index = (current_index + 1) % tabs.len();
        task.tab = tabs[next_index].name.clone();
        task.sync_updated_at = storage::now_sync_stamp();
        self.open_task_menu_id = None;
        self.save();
        true
    }

    fn submit_tab(&mut self) -> bool {
        let name = model::normalize_tab_name(&self.draft_tab_name);
        if name.is_empty() || self.data.settings.tabs.iter().any(|tab| tab.name == name) {
            return false;
        }

        self.data.settings.tabs.push(model::TabSpec {
            sync_id: model::tab_sync_id_from_name(&name),
            sync_updated_at: storage::now_sync_stamp(),
            name: name.clone(),
            priority: model::TabPriority::Normal,
        });
        self.active_tab = name;
        self.ensure_active_tab_visible();
        self.clear_tab_draft();
        self.save();
        true
    }

    fn move_tab(&mut self, name: &str, delta: isize) -> bool {
        let Some(index) = self
            .data
            .settings
            .tabs
            .iter()
            .position(|tab| tab.name == name)
        else {
            return false;
        };

        let target = index as isize + delta;
        if target < 0 || target >= self.data.settings.tabs.len() as isize {
            return false;
        }

        self.data.settings.tabs.swap(index, target as usize);
        self.touch_all_tabs();
        self.save();
        true
    }

    fn delete_tab(&mut self, name: &str) -> bool {
        if name == model::GENERAL_TAB_NAME {
            return false;
        }

        let before = self.data.settings.tabs.len();
        self.data.settings.tabs.retain(|tab| tab.name != name);
        if self.data.settings.tabs.len() == before {
            return false;
        }

        for task in self
            .data
            .active
            .iter_mut()
            .chain(self.data.history.iter_mut())
        {
            if task.tab == name {
                task.tab = model::GENERAL_TAB_NAME.to_string();
                task.sync_updated_at = storage::now_sync_stamp();
            }
        }

        if self.active_tab == name {
            self.active_tab = "All".to_string();
        }

        self.clamp_tab_window();
        self.touch_all_tabs();
        self.touch_tab(model::GENERAL_TAB_NAME);
        self.save();
        true
    }

    fn import_data(&mut self) -> bool {
        let path = self.transfer_path.trim().to_string();
        if path.is_empty() {
            self.set_tools_message("Enter a JSON path to import.");
            return false;
        }

        match storage::load_data_from_path(&PathBuf::from(&path)) {
            Ok(data) => {
                self.data = data;
                self.active_tab = "All".to_string();
                self.history_visible = false;
                self.tools_visible = true;
                self.clear_draft();
                self.set_tools_message(format!("Imported data from {}", path));
                self.save();
                true
            }
            Err(error) => {
                self.set_tools_message(format!("Import failed: {}", error));
                false
            }
        }
    }

    fn export_data(&mut self) -> bool {
        let path = self.transfer_path.trim();
        if path.is_empty() {
            self.transfer_path = storage::default_export_path().display().to_string();
        }

        let export_path = PathBuf::from(self.transfer_path.trim());
        match storage::save_data_to_path(&export_path, &self.data) {
            Ok(()) => {
                self.set_tools_message(format!("Exported data to {}", export_path.display()));
                true
            }
            Err(error) => {
                self.set_tools_message(format!("Export failed: {}", error));
                false
            }
        }
    }

    fn save_sync_config(&mut self) -> bool {
        self.data.settings.sync.enabled = self.sync_enabled;
        self.data.settings.sync.path = self.sync_path.trim().to_string();
        self.data.settings.sync.device_id = self.sync_device_id.trim().to_string();
        self.save();
        self.set_sync_message("Sync settings saved locally.");
        true
    }

    fn sync_now(&mut self) -> bool {
        if !self.sync_enabled {
            self.set_sync_message("Enable sync first.");
            return false;
        }

        let path = self.sync_path.trim().to_string();
        if path.is_empty() {
            self.set_sync_message("Enter a path for focus-sync.json.");
            return false;
        }

        let sync_path = PathBuf::from(&path);
        match storage::load_sync_file_from_path(&sync_path) {
            Ok(sync_file) => {
                let mut local_settings = self.data.settings.clone();
                local_settings.sync.enabled = self.sync_enabled;
                local_settings.sync.path = path.clone();
                local_settings.sync.device_id = self.sync_device_id.trim().to_string();
                let local_sync = storage::app_data_to_sync_file(&self.data, self.sync_device_id.trim());
                let merged_sync = storage::merge_sync_files(
                    &local_sync,
                    &sync_file,
                    &self.data.settings.sync.last_sync_at,
                    self.sync_device_id.trim(),
                );
                let sync_stamp = storage::now_sync_stamp();
                local_settings.sync.last_sync_at = sync_stamp.clone();

                if let Err(error) = storage::save_sync_file_to_path(&sync_path, &merged_sync) {
                    self.set_sync_message(format!("Sync failed: {}", error));
                    return false;
                }

                self.data = storage::sync_file_to_app_data(&merged_sync, Some(&local_settings));
                self.data.settings.sync = local_settings.sync.clone();
                self.active_tab = "All".to_string();
                self.clear_draft();
                if let Some(store) = &self.store {
                    if let Err(error) = store.save(&self.data) {
                        self.set_sync_message(format!("Sync failed: {}", error));
                        return false;
                    }
                }
                self.set_sync_message(format!("Synced from {}", path));
                true
            }
            Err(error) => {
                self.set_sync_message(format!("Sync failed: {}", error));
                false
            }
        }
    }

    fn apply_theme_preset(&mut self, name: &str) -> bool {
        let normalized = name.trim().to_ascii_lowercase();
        match normalized.as_str() {
            "warm" | "forest" | "ocean" | "rose" | "dark" => {
                self.data.settings.theme_name = normalized.clone();
                self.touch_preferences();
                self.save();
                self.set_tools_message(format!("Applied theme preset {}", normalized));
                true
            }
            _ => false,
        }
    }

    fn adjust_font_scale(&mut self, delta: f32) -> bool {
        let next = (self.data.settings.font_scale + delta).clamp(0.8, 1.8);
        if (next - self.data.settings.font_scale).abs() < f32::EPSILON {
            return false;
        }

        self.data.settings.font_scale = (next * 10.0).round() / 10.0;
        self.touch_preferences();
        self.save();
        self.set_tools_message(format!(
            "Font scale set to {}%",
            (self.data.settings.font_scale * 100.0).round() as i32
        ));
        true
    }

    fn toggle_accessibility_mode(&mut self) -> bool {
        self.data.settings.accessibility_mode = !self.data.settings.accessibility_mode;
        self.touch_preferences();
        self.save();
        self.set_tools_message(if self.data.settings.accessibility_mode {
            "Accessibility mode enabled"
        } else {
            "Accessibility mode disabled"
        });
        true
    }

    fn toggle_item_meta(&mut self) -> bool {
        self.data.settings.show_item_meta = !self.data.settings.show_item_meta;
        self.touch_preferences();
        self.save();
        self.set_tools_message(if self.data.settings.show_item_meta {
            "Task metadata visible"
        } else {
            "Task metadata hidden"
        });
        true
    }

    fn toggle_startup(&mut self) -> bool {
        let next = !self.startup_enabled;
        match storage::set_startup_enabled(next) {
            Ok(()) => {
                self.startup_enabled = next;
                self.set_startup_message(if next {
                    "Launch on login enabled"
                } else {
                    "Launch on login disabled"
                });
                true
            }
            Err(error) => {
                self.startup_enabled = storage::startup_enabled().unwrap_or(false);
                self.set_startup_message(error.to_string());
                false
            }
        }
    }

}

fn main() -> Result<(), slint::PlatformError> {
    slint::BackendSelector::new()
        .backend_name("winit".into())
        .select()?;

    let app = AppWindow::new()?;
    let store = storage::DataStore::new().ok();
    let data = store
        .as_ref()
        .map(|store| store.load())
        .unwrap_or_else(|| model::AppData::with_default_items(&storage::now_stamp()));

    let state = Rc::new(RefCell::new(AppState::new(data, store)));
    let undo_timer = Rc::new(RefCell::new(Timer::default()));

    apply_always_on_top(&app, state.borrow().data.settings.always_on_top);
    refresh_ui(&app, &state.borrow());

    bind_callbacks(&app, state.clone(), undo_timer.clone());

    let result = app.run();

    {
        let mut state = state.borrow_mut();
        state.finalize_pending_completion();
    }

    result
}

fn bind_callbacks(app: &AppWindow, state: Rc<RefCell<AppState>>, undo_timer: Rc<RefCell<Timer>>) {
    let app_weak = app.as_weak();

    app.on_add_task({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.clear_draft();
            state.draft_visible = true;
            state.history_visible = false;
            state.tools_visible = false;
            audio::play_add();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_submit_draft({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            if let Some(app) = app_weak.upgrade() {
                let mut state = state.borrow_mut();
                state.draft_title = app.get_draft_title().to_string();
                state.draft_extra = app.get_draft_extra().to_string();
                state.draft_due_date = app.get_draft_due_date().to_string();
                state.draft_has_due = app.get_draft_has_due();
                if state.submit_draft() {
                    refresh_ui(&app, &state);
                } else {
                    refresh_ui(&app, &state);
                }
            }
        }
    });

    app.on_cancel_draft({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.clear_draft();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_select_tab({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |name| {
            let mut state = state.borrow_mut();
            state.select_tab(name.to_string());
            audio::play_click();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_shift_tabs_left({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.shift_tab_window(-1);
            audio::play_click();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_shift_tabs_right({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.shift_tab_window(1);
            audio::play_click();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_tab_strip_resized({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |width| {
            let mut state = state.borrow_mut();
            state.update_tab_strip_width(width);
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_edit_task({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            state.start_edit(task_id as u64);
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_delete_task({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.delete_task(task_id as u64) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_current({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.toggle_current(task_id as u64) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_complete_task({
        let app_weak = app_weak.clone();
        let state = state.clone();
        let undo_timer = undo_timer.clone();
        move |task_id| {
            let mut state_ref = state.borrow_mut();
            if !state_ref.complete_task(task_id as u64) {
                return;
            }
            audio::play_complete();
            refresh_if_possible(&app_weak, &state_ref);
            drop(state_ref);

            let state_for_timer = state.clone();
            let app_for_timer = app_weak.clone();
            undo_timer.borrow_mut().start(
                TimerMode::SingleShot,
                Duration::from_secs(3),
                move || {
                    let mut state = state_for_timer.borrow_mut();
                    if state.finalize_pending_completion() {
                        refresh_if_possible(&app_for_timer, &state);
                    }
                },
            );
        }
    });

    app.on_undo_complete({
        let app_weak = app_weak.clone();
        let state = state.clone();
        let undo_timer = undo_timer.clone();
        move || {
            undo_timer.borrow_mut().stop();
            let mut state = state.borrow_mut();
            if state.undo_complete() {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_on_top({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            if let Some(app) = app_weak.upgrade() {
                let mut state = state.borrow_mut();
                state.data.settings.always_on_top = !state.data.settings.always_on_top;
                apply_always_on_top(&app, state.data.settings.always_on_top);
                state.save();
                audio::play_click();
                refresh_ui(&app, &state);
            }
        }
    });

    app.on_show_history({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.toggle_history();
            audio::play_click();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_show_tools({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.toggle_tools();
            audio::play_click();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_restore_history({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.restore_history(task_id as u64) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_move_task_up({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.move_task(task_id as u64, -1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_move_task_down({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.move_task(task_id as u64, 1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_cycle_task_tab({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            if state.cycle_task_tab(task_id as u64) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_drag_task_step({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id, delta| {
            let mut state = state.borrow_mut();
            if state.move_task(task_id as u64, delta as isize) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_task_menu({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |task_id| {
            let mut state = state.borrow_mut();
            state.toggle_task_menu(task_id as u64);
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_submit_tab({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            if let Some(app) = app_weak.upgrade() {
                let mut state = state.borrow_mut();
                state.draft_tab_name = app.get_draft_tab_name().to_string();
                if state.submit_tab() {
                    refresh_ui(&app, &state);
                }
            }
        }
    });

    app.on_move_tab_up({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |name| {
            let mut state = state.borrow_mut();
            if state.move_tab(name.as_str(), -1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_move_tab_down({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |name| {
            let mut state = state.borrow_mut();
            if state.move_tab(name.as_str(), 1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_delete_tab({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |name| {
            let mut state = state.borrow_mut();
            if state.delete_tab(name.as_str()) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_import_data({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.import_data();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_export_data({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.export_data();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_apply_theme_preset({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move |name| {
            let mut state = state.borrow_mut();
            if state.apply_theme_preset(name.as_str()) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_decrease_font_scale({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            if state.adjust_font_scale(-0.1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_increase_font_scale({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            if state.adjust_font_scale(0.1) {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_accessibility_mode({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            if state.toggle_accessibility_mode() {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_item_meta({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            if state.toggle_item_meta() {
                refresh_if_possible(&app_weak, &state);
            }
        }
    });

    app.on_toggle_startup({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            state.toggle_startup();
            refresh_if_possible(&app_weak, &state);
        }
    });

    app.on_open_task_link(move |url| {
        let _ = open_project_link(url.as_str());
    });

    app.on_save_sync_config({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            if let Some(app) = app_weak.upgrade() {
                let mut state = state.borrow_mut();
                state.sync_enabled = app.get_sync_enabled();
                state.sync_path = app.get_sync_path().to_string();
                state.sync_device_id = app.get_sync_device_id().to_string();
                state.save_sync_config();
                refresh_ui(&app, &state);
            }
        }
    });

    app.on_sync_now({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            if let Some(app) = app_weak.upgrade() {
                let mut state = state.borrow_mut();
                state.sync_enabled = app.get_sync_enabled();
                state.sync_path = app.get_sync_path().to_string();
                state.sync_device_id = app.get_sync_device_id().to_string();
                state.sync_now();
                refresh_ui(&app, &state);
            }
        }
    });

    app.on_open_project_link(move || {
        let _ = open_project_link(PROJECT_REPO_URL);
    });
}

fn refresh_if_possible(app_weak: &Weak<AppWindow>, state: &AppState) {
    if let Some(app) = app_weak.upgrade() {
        refresh_ui(&app, state);
    }
}

fn apply_always_on_top(app: &AppWindow, enabled: bool) {
    app.window()
        .with_winit_window(|window: &winit::window::Window| {
            let level = if enabled {
                winit::window::WindowLevel::AlwaysOnTop
            } else {
                winit::window::WindowLevel::Normal
            };
            window.set_window_level(level);
        });
}

fn refresh_ui(app: &AppWindow, state: &AppState) {
    let tabs = build_tab_views(
        &state.data,
        &state.active_tab,
        state.tab_window_start,
        state.visible_tab_count,
    );
    let tasks = build_task_views(&state.data, &state.active_tab);
    let history_items = build_history_views(&state.data);
    let managed_tabs = build_managed_tabs(&state.data);
    let current = current_task(&state.data);
    let (done_today, done_month, done_year) = completion_counts(&state.data);
    let palette = theme_palette(&state.data.settings.theme_name);

    app.set_status_text("".into());
    app.set_bg(parse_hex_color(palette.bg));
    app.set_panel(parse_hex_color(palette.panel));
    app.set_panel_alt(parse_hex_color(palette.panel_alt));
    app.set_panel_soft(parse_hex_color(palette.panel_soft));
    app.set_text_main(parse_hex_color(palette.text_main));
    app.set_text_muted(parse_hex_color(palette.text_muted));
    app.set_accent(parse_hex_color(palette.accent));
    app.set_border(parse_hex_color(palette.border));
    app.set_accent_warm(parse_hex_color(palette.accent_warm));
    app.set_font_scale(state.data.settings.font_scale);
    app.set_accessibility_mode(state.data.settings.accessibility_mode);
    app.set_show_item_meta(state.data.settings.show_item_meta);
    app.set_font_scale_label(
        format!("{}%", (state.data.settings.font_scale * 100.0).round() as i32).into(),
    );
    app.set_footer_text(format_footer(&state.data, &state.active_tab).into());
    app.set_active_tab_name(state.active_tab.clone().into());
    app.set_task_menu_id(state.open_task_menu_id.map(|value| value as i32).unwrap_or(-1));
    app.set_pending_count(visible_items(&state.data, &state.active_tab).len() as i32);
    app.set_done_today_count(done_today as i32);
    app.set_done_month_count(done_month as i32);
    app.set_done_year_count(done_year as i32);
    app.set_on_top_enabled(state.data.settings.always_on_top);
    let tab_overflow = state.data.settings.tabs.len() > state.visible_tab_count.max(1);
    app.set_tab_overflow(tab_overflow);
    app.set_can_shift_tabs_left(state.tab_window_start > 0);
    app.set_can_shift_tabs_right(
        state.tab_window_start + state.visible_tab_count.max(1) < state.data.settings.tabs.len(),
    );
    app.set_tabs(ModelRc::new(VecModel::from(tabs)));
    app.set_tasks(ModelRc::new(VecModel::from(tasks)));
    app.set_history_items(ModelRc::new(VecModel::from(history_items)));
    app.set_managed_tabs(ModelRc::new(VecModel::from(managed_tabs)));
    app.set_current_title(current.0.into());
    app.set_current_meta(current.1.into());
    app.set_draft_title(state.draft_title.clone().into());
    app.set_draft_extra(state.draft_extra.clone().into());
    app.set_draft_due_date(state.draft_due_date.clone().into());
    app.set_draft_has_due(state.draft_has_due);
    app.set_draft_message(state.draft_message.clone().into());
    app.set_draft_tab_name(state.draft_tab_name.clone().into());
    app.set_transfer_path(state.transfer_path.clone().into());
    app.set_tools_message(state.tools_message.clone().into());
    app.set_sync_enabled(state.sync_enabled);
    app.set_sync_path(state.sync_path.clone().into());
    app.set_sync_device_id(state.sync_device_id.clone().into());
    app.set_sync_message(state.sync_message.clone().into());
    app.set_startup_enabled(state.startup_enabled);
    app.set_startup_message(state.startup_message.clone().into());
    app.set_about_version(env!("CARGO_PKG_VERSION").into());
    app.set_about_commit(BUILD_COMMIT.into());
    app.set_about_repo_url(PROJECT_REPO_URL.into());
    app.set_editing_mode(state.editing_task_id.is_some());
    app.set_draft_visible(state.draft_visible);
    app.set_can_undo(state.undo_item.is_some());
    app.set_history_visible(state.history_visible);
    app.set_tools_visible(state.tools_visible);
}

fn theme_palette(name: &str) -> ThemePalette {
    match name.trim().to_ascii_lowercase().as_str() {
        "forest" => ThemePalette {
            bg: "#bcd0bc",
            panel: "#d4e8d4",
            panel_alt: "#c8e0c8",
            panel_soft: "#b0ccb0",
            text_main: "#101e10",
            text_muted: "#406040",
            accent: "#2e8830",
            border: "#98c098",
            accent_warm: "#389838",
        },
        "ocean" => ThemePalette {
            bg: "#b8cede",
            panel: "#cce0f0",
            panel_alt: "#c0d8ec",
            panel_soft: "#a8c4d8",
            text_main: "#080e18",
            text_muted: "#305878",
            accent: "#1468a0",
            border: "#88b0cc",
            accent_warm: "#1878b8",
        },
        "rose" => ThemePalette {
            bg: "#e0c0c0",
            panel: "#f4d8d8",
            panel_alt: "#eccece",
            panel_soft: "#d4aaaa",
            text_main: "#200808",
            text_muted: "#804040",
            accent: "#b83040",
            border: "#cc9898",
            accent_warm: "#c83848",
        },
        "dark" => ThemePalette {
            bg: "#141414",
            panel: "#202020",
            panel_alt: "#282828",
            panel_soft: "#282420",
            text_main: "#e4ddd4",
            text_muted: "#888070",
            accent: "#d4904a",
            border: "#383028",
            accent_warm: "#c07830",
        },
        _ => ThemePalette {
            bg: "#e2d4c0",
            panel: "#f0e8d8",
            panel_alt: "#e8dcc8",
            panel_soft: "#d4c4a8",
            text_main: "#28180a",
            text_muted: "#7a6448",
            accent: "#c07828",
            border: "#c8b898",
            accent_warm: "#c07828",
        },
    }
}

fn open_project_link(url: &str) -> std::io::Result<()> {
    #[cfg(target_os = "windows")]
    {
        Command::new("cmd").args(["/C", "start", "", url]).spawn()?;
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open").arg(url).spawn()?;
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open").arg(url).spawn()?;
        return Ok(());
    }

    #[allow(unreachable_code)]
    Ok(())
}

fn parse_hex_color(value: &str) -> Color {
    let value = value.trim_start_matches('#');
    let r = u8::from_str_radix(&value[0..2], 16).unwrap_or(0);
    let g = u8::from_str_radix(&value[2..4], 16).unwrap_or(0);
    let b = u8::from_str_radix(&value[4..6], 16).unwrap_or(0);
    Color::from_rgb_u8(r, g, b)
}

fn build_tab_views(
    data: &model::AppData,
    active_tab: &str,
    start: usize,
    visible_count: usize,
) -> Vec<TabView> {
    let mut tabs = Vec::with_capacity(visible_count.max(1) + 1);
    tabs.push(TabView {
        name: "All".into(),
        priority: "all".into(),
        selected: active_tab == "All",
    });

    tabs.extend(
        data.settings
            .tabs
            .iter()
            .skip(start)
            .take(visible_count.max(1))
            .map(|tab| TabView {
        name: tab.name.clone().into(),
        priority: format!("{:?}", tab.priority).to_lowercase().into(),
        selected: tab.name == active_tab,
    }),
    );

    tabs
}

fn build_task_views(data: &model::AppData, active_tab: &str) -> Vec<TaskView> {
    let show_meta = data.settings.show_item_meta;
    visible_items(data, active_tab)
        .into_iter()
        .map(|task| {
            let link = extract_first_url(&task.text).or_else(|| extract_first_url(&task.extra_info));
            TaskView {
                id: task.id as i32,
                title: task.text.clone().into(),
                meta: if show_meta { task_meta(task) } else { String::new() }.into(),
                due_label: if show_meta { due_label(task) } else { String::new() }.into(),
                extra: if show_meta {
                    task.extra_info.clone()
                } else {
                    String::new()
                }
                .into(),
                link_label: link
                    .as_deref()
                    .map(short_link_label)
                    .unwrap_or_default()
                    .into(),
                link_url: link.clone().unwrap_or_default().into(),
                is_current: task.current,
                has_due_date: show_meta && !task.due_date.trim().is_empty(),
                has_extra: show_meta && !task.extra_info.trim().is_empty(),
                has_link: link.is_some(),
                progress: if show_meta { due_progress_ratio(task) } else { 0.0 },
            }
        })
        .collect()
}

fn current_task(data: &model::AppData) -> (String, String) {
    data.active
        .iter()
        .find(|task| task.current)
        .or_else(|| data.active.first())
        .map(|task| {
            let meta = if data.settings.show_item_meta {
                task_meta(task)
            } else {
                String::new()
            };
            (task.text.clone(), meta)
        })
        .unwrap_or_else(|| (String::new(), String::new()))
}

fn build_history_views(data: &model::AppData) -> Vec<HistoryView> {
    let show_meta = data.settings.show_item_meta;
    data.history
        .iter()
        .rev()
        .map(|task| {
            let link = extract_first_url(&task.text).or_else(|| extract_first_url(&task.extra_info));
            HistoryView {
                id: task.id as i32,
                title: task.text.clone().into(),
                meta: if show_meta {
                    history_meta(task)
                } else {
                    String::new()
                }
                .into(),
                extra: if show_meta {
                    task.extra_info.clone()
                } else {
                    String::new()
                }
                .into(),
                link_label: link
                    .as_deref()
                    .map(short_link_label)
                    .unwrap_or_default()
                    .into(),
                link_url: link.clone().unwrap_or_default().into(),
                has_extra: show_meta && !task.extra_info.trim().is_empty(),
                has_link: link.is_some(),
            }
        })
        .collect()
}

fn build_managed_tabs(data: &model::AppData) -> Vec<TabManagerView> {
    data.settings
        .tabs
        .iter()
        .map(|tab| TabManagerView {
            name: tab.name.clone().into(),
            priority: format!("{:?}", tab.priority).to_lowercase().into(),
            can_delete: tab.name != model::GENERAL_TAB_NAME,
        })
        .collect()
}

fn visible_items<'a>(data: &'a model::AppData, active_tab: &str) -> Vec<&'a model::TaskItem> {
    let filtered: Vec<&model::TaskItem> = if active_tab == "All" {
        data.active.iter().collect()
    } else {
        data.active
            .iter()
            .filter(|task| task.tab == active_tab)
            .collect()
    };

    let (current, rest): (Vec<&model::TaskItem>, Vec<&model::TaskItem>) =
        filtered.into_iter().partition(|task| task.current);

    current.into_iter().chain(rest).collect()
}

fn task_meta(task: &model::TaskItem) -> String {
    let mut parts = Vec::new();

    if !task.tab.trim().is_empty() {
        parts.push(format!("tab {}", task.tab));
    }
    if !task.created_at.trim().is_empty() {
        parts.push(format!("added {}", task.created_at));
    }
    if !task.due_date.trim().is_empty() {
        let mut due = format!("due {}", format_dt(&task.due_date));
        let remaining = format_remaining_time(&task.due_date);
        if !remaining.is_empty() {
            due.push_str(&format!(" ({remaining})"));
        }
        parts.push(due);
    }
    if task.current {
        parts.push("current".to_string());
    }
    if !task.extra_info.trim().is_empty() {
        parts.push("extra info".to_string());
    }

    parts.join("  ·  ")
}

fn due_label(task: &model::TaskItem) -> String {
    if task.due_date.trim().is_empty() {
        String::new()
    } else {
        let remaining = format_remaining_time(&task.due_date);
        if remaining.is_empty() {
            format!("Due {}", format_dt(&task.due_date))
        } else {
            format!("Due {}  ·  {}", format_dt(&task.due_date), remaining)
        }
    }
}

fn history_meta(task: &model::TaskItem) -> String {
    let mut parts = Vec::new();

    if !task.tab.trim().is_empty() {
        parts.push(format!("tab {}", task.tab));
    }
    if !task.created_at.trim().is_empty() {
        parts.push(format!("added {}", task.created_at));
    }
    if !task.completed_at.trim().is_empty() {
        parts.push(format!("done {}", task.completed_at));
    }
    if !task.due_date.trim().is_empty() {
        parts.push(format!("due {}", format_dt(&task.due_date)));
    }

    parts.join("  ·  ")
}

fn due_progress_ratio(task: &model::TaskItem) -> f32 {
    let due = parse_dt(&task.due_date);
    let created = parse_dt(&task.created_at);

    let (Some(due), Some(created)) = (due, created) else {
        return 0.0;
    };

    let total = (due - created).num_seconds() as f32;
    let elapsed = (Local::now().naive_local() - created).num_seconds() as f32;

    if total <= 0.0 {
        1.0
    } else {
        (elapsed / total).clamp(0.0, 1.0)
    }
}

fn format_dt(value: &str) -> String {
    parse_dt(value)
        .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
        .unwrap_or_else(|| value.trim().to_string())
}

fn format_remaining_time(value: &str) -> String {
    let Some(due) = parse_dt(value) else {
        return String::new();
    };

    let delta = due - Local::now().naive_local();
    let total_minutes = delta.num_minutes();
    let overdue = total_minutes < 0;
    let total_minutes = total_minutes.unsigned_abs();
    let days = total_minutes / 1440;
    let rem = total_minutes % 1440;
    let hours = rem / 60;
    let minutes = rem % 60;

    let mut parts = Vec::new();
    if days > 0 {
        parts.push(format!("{days}d"));
    }
    if hours > 0 {
        parts.push(format!("{hours}h"));
    }
    if minutes > 0 || parts.is_empty() {
        parts.push(format!("{minutes}m"));
    }

    let label = parts.join(" ");
    if overdue {
        format!("overdue {label}")
    } else {
        format!("{label} left")
    }
}

fn normalize_due_input(value: &str) -> Result<String, String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Ok(String::new());
    }

    parse_dt(trimmed)
        .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
        .ok_or_else(|| "Due date must use YYYY-MM-DD or YYYY-MM-DD HH:MM".to_string())
}

fn extract_first_url(text: &str) -> Option<String> {
    text.split_whitespace().find_map(|part| {
        let trimmed = part.trim_matches(|ch: char| {
            matches!(ch, '"' | '\'' | '(' | ')' | '[' | ']' | '{' | '}' | ',' | '.' | ';')
        });
        if trimmed.starts_with("https://") || trimmed.starts_with("http://") {
            Some(trimmed.to_string())
        } else {
            None
        }
    })
}

fn short_link_label(url: &str) -> String {
    let trimmed = url.trim();
    if trimmed.len() <= 48 {
        format!("Open {}", trimmed)
    } else {
        format!("Open {}...", &trimmed[..45])
    }
}

fn completion_counts(data: &model::AppData) -> (usize, usize, usize) {
    let now = Local::now().naive_local().date();
    let mut today = 0;
    let mut month = 0;
    let mut year = 0;

    for item in &data.history {
        let Some(completed) = parse_dt(&item.completed_at) else {
            continue;
        };

        if completed.date() == now {
            today += 1;
        }
        if completed.year() == now.year() && completed.month() == now.month() {
            month += 1;
        }
        if completed.year() == now.year() {
            year += 1;
        }
    }

    (today, month, year)
}

fn format_footer(data: &model::AppData, active_tab: &str) -> String {
    let visible = visible_items(data, active_tab).len();
    let current = data.active.iter().filter(|task| task.current).count();
    format!(
        "{} visible tasks | {} current | {} tabs",
        visible,
        current,
        data.settings.tabs.len()
    )
}

fn parse_dt(value: &str) -> Option<NaiveDateTime> {
    let value = value.trim();
    if value.is_empty() {
        return None;
    }

    NaiveDateTime::parse_from_str(value, "%Y-%m-%d %H:%M")
        .ok()
        .or_else(|| {
            NaiveDate::parse_from_str(value, "%Y-%m-%d")
                .ok()
                .and_then(|date| date.and_hms_opt(0, 0, 0))
        })
}
