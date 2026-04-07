mod audio;
mod model;
mod storage;

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;
use std::time::Duration;

use chrono::{Datelike, Local, NaiveDate, NaiveDateTime};
use slint::winit_030::{WinitWindowAccessor, winit};
use slint::{ModelRc, Timer, TimerMode, VecModel, Weak};

slint::include_modules!();

#[derive(Debug)]
struct AppState {
    data: model::AppData,
    active_tab: String,
    tab_window_start: usize,
    visible_tab_count: usize,
    history_visible: bool,
    tools_visible: bool,
    draft_visible: bool,
    draft_title: String,
    draft_extra: String,
    draft_tab_name: String,
    transfer_path: String,
    tools_message: String,
    editing_task_id: Option<u64>,
    undo_item: Option<model::TaskItem>,
    store: Option<storage::DataStore>,
}

impl AppState {
    fn new(data: model::AppData, store: Option<storage::DataStore>) -> Self {
        Self {
            data,
            active_tab: "All".to_string(),
            tab_window_start: 0,
            visible_tab_count: 3,
            history_visible: false,
            tools_visible: false,
            draft_visible: false,
            draft_title: String::new(),
            draft_extra: String::new(),
            draft_tab_name: String::new(),
            transfer_path: storage::default_export_path().display().to_string(),
            tools_message: String::new(),
            editing_task_id: None,
            undo_item: None,
            store,
        }
    }

    fn save(&self) {
        if let Some(store) = &self.store {
            let _ = store.save(&self.data);
        }
    }

    fn clear_draft(&mut self) {
        self.draft_title.clear();
        self.draft_extra.clear();
        self.editing_task_id = None;
        self.draft_visible = false;
    }

    fn clear_tab_draft(&mut self) {
        self.draft_tab_name.clear();
    }

    fn set_tools_message(&mut self, message: impl Into<String>) {
        self.tools_message = message.into();
    }

    fn submit_draft(&mut self) -> bool {
        let text = self.draft_title.trim();
        if text.is_empty() {
            return false;
        }

        if let Some(task_id) = self.editing_task_id {
            if let Some(task) = self.data.active.iter_mut().find(|task| task.id == task_id) {
                task.text = text.to_string();
                task.extra_info = self.draft_extra.trim().to_string();
            }
        } else {
            let mut item = model::TaskItem::new(self.data.next_id(), text);
            item.created_at = storage::now_stamp();
            item.extra_info = self.draft_extra.trim().to_string();
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
            self.draft_visible = true;
            self.history_visible = false;
            self.tools_visible = false;
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
            for task in &mut self.data.active {
                task.current = task.id == task_id;
            }
            if let Some(index) = self.data.active.iter().position(|task| task.id == task_id) {
                let task = self.data.active.remove(index);
                self.data.active.insert(0, task);
            }
        } else if let Some(task) = self.data.active.iter_mut().find(|task| task.id == task_id) {
            task.current = false;
        }

        self.save();
        true
    }

    fn finalize_pending_completion(&mut self) -> bool {
        let Some(item) = self.undo_item.take() else {
            return false;
        };
        self.data.history.push(item);
        self.data.history.truncate(250);
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
        self.undo_item = Some(item);

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
        self.data.active.insert(0, item);
        self.save();
        true
    }

    fn select_tab(&mut self, name: String) {
        self.active_tab = name;
        self.ensure_active_tab_visible();
        self.history_visible = false;
        self.tools_visible = false;
    }

    fn toggle_history(&mut self) {
        self.history_visible = !self.history_visible;
        if self.history_visible {
            self.tools_visible = false;
            self.draft_visible = false;
        }
    }

    fn toggle_tools(&mut self) {
        self.tools_visible = !self.tools_visible;
        if self.tools_visible {
            self.history_visible = false;
            self.draft_visible = false;
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
        self.data.active.push(item);
        self.history_visible = false;
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
            }
        }

        if self.active_tab == name {
            self.active_tab = "All".to_string();
        }

        self.clamp_tab_window();
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
            let mut state = state.borrow_mut();
            if state.submit_draft() {
                refresh_if_possible(&app_weak, &state);
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

    app.on_submit_tab({
        let app_weak = app_weak.clone();
        let state = state.clone();
        move || {
            let mut state = state.borrow_mut();
            if state.submit_tab() {
                refresh_if_possible(&app_weak, &state);
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

    app.set_status_text(
        format!(
            "Rust + Slint ready | {} active | {} history",
            state.data.active.len(),
            state.data.history.len()
        )
        .into(),
    );
    app.set_footer_text(format_footer(&state.data, &state.active_tab).into());
    app.set_active_tab_name(state.active_tab.clone().into());
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
    app.set_draft_tab_name(state.draft_tab_name.clone().into());
    app.set_transfer_path(state.transfer_path.clone().into());
    app.set_tools_message(state.tools_message.clone().into());
    app.set_editing_mode(state.editing_task_id.is_some());
    app.set_draft_visible(state.draft_visible);
    app.set_can_undo(state.undo_item.is_some());
    app.set_history_visible(state.history_visible);
    app.set_tools_visible(state.tools_visible);
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
    visible_items(data, active_tab)
        .into_iter()
        .map(|task| TaskView {
            id: task.id as i32,
            title: task.text.clone().into(),
            meta: task_meta(task).into(),
            due_label: due_label(task).into(),
            extra: task.extra_info.clone().into(),
            is_current: task.current,
            has_due_date: !task.due_date.trim().is_empty(),
            has_extra: !task.extra_info.trim().is_empty(),
            progress: due_progress_ratio(task),
        })
        .collect()
}

fn current_task(data: &model::AppData) -> (String, String) {
    data.active
        .iter()
        .find(|task| task.current)
        .or_else(|| data.active.first())
        .map(|task| (task.text.clone(), task_meta(task)))
        .unwrap_or_else(|| (String::new(), String::new()))
}

fn build_history_views(data: &model::AppData) -> Vec<HistoryView> {
    data.history
        .iter()
        .rev()
        .map(|task| HistoryView {
            id: task.id as i32,
            title: task.text.clone().into(),
            meta: history_meta(task).into(),
            extra: task.extra_info.clone().into(),
            has_extra: !task.extra_info.trim().is_empty(),
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
        parts.push(task.tab.clone());
    }
    if !task.created_at.trim().is_empty() {
        parts.push(format!("Created {}", task.created_at));
    }
    if task.current {
        parts.push("Pinned as current".to_string());
    }

    parts.join(" | ")
}

fn due_label(task: &model::TaskItem) -> String {
    if task.due_date.trim().is_empty() {
        String::new()
    } else {
        format!("Due {}", task.due_date)
    }
}

fn history_meta(task: &model::TaskItem) -> String {
    let mut parts = Vec::new();

    if !task.tab.trim().is_empty() {
        parts.push(task.tab.clone());
    }
    if !task.created_at.trim().is_empty() {
        parts.push(format!("Created {}", task.created_at));
    }
    if !task.completed_at.trim().is_empty() {
        parts.push(format!("Done {}", task.completed_at));
    }

    parts.join(" | ")
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
