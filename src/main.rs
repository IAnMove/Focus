mod model;
mod storage;

use std::cell::RefCell;
use std::rc::Rc;
use std::time::Duration;

use chrono::{Datelike, Local, NaiveDate, NaiveDateTime};
use slint::{ModelRc, Timer, TimerMode, VecModel, Weak};

slint::include_modules!();

#[derive(Debug)]
struct AppState {
    data: model::AppData,
    active_tab: String,
    draft_title: String,
    draft_extra: String,
    editing_task_id: Option<u64>,
    undo_item: Option<model::TaskItem>,
    store: Option<storage::DataStore>,
}

impl AppState {
    fn new(data: model::AppData, store: Option<storage::DataStore>) -> Self {
        Self {
            data,
            active_tab: "All".to_string(),
            draft_title: String::new(),
            draft_extra: String::new(),
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
    }
}

fn main() -> Result<(), slint::PlatformError> {
    let app = AppWindow::new()?;
    let store = storage::DataStore::new().ok();
    let data = store
        .as_ref()
        .map(|store| store.load())
        .unwrap_or_else(|| model::AppData::with_default_items(&storage::now_stamp()));

    let state = Rc::new(RefCell::new(AppState::new(data, store)));
    let undo_timer = Rc::new(RefCell::new(Timer::default()));

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
                #[allow(deprecated)]
                {
                    app.window()
                        .set_always_on_top(state.data.settings.always_on_top);
                }
                state.save();
                refresh_ui(&app, &state);
            }
        }
    });

    app.on_show_history(|| {});
    app.on_show_tools(|| {});
}

fn refresh_if_possible(app_weak: &Weak<AppWindow>, state: &AppState) {
    if let Some(app) = app_weak.upgrade() {
        refresh_ui(&app, state);
    }
}

fn refresh_ui(app: &AppWindow, state: &AppState) {
    let tabs = build_tab_views(&state.data, &state.active_tab);
    let tasks = build_task_views(&state.data, &state.active_tab);
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
    app.set_tabs(ModelRc::new(VecModel::from(tabs)));
    app.set_tasks(ModelRc::new(VecModel::from(tasks)));
    app.set_current_title(current.0.into());
    app.set_current_meta(current.1.into());
    app.set_draft_title(state.draft_title.clone().into());
    app.set_draft_extra(state.draft_extra.clone().into());
    app.set_editing_mode(state.editing_task_id.is_some());
    app.set_can_undo(state.undo_item.is_some());
}

fn build_tab_views(data: &model::AppData, active_tab: &str) -> Vec<TabView> {
    let mut tabs = Vec::with_capacity(data.settings.tabs.len() + 1);
    tabs.push(TabView {
        name: "All".into(),
        priority: "all".into(),
        selected: active_tab == "All",
    });

    tabs.extend(data.settings.tabs.iter().map(|tab| TabView {
        name: tab.name.clone().into(),
        priority: format!("{:?}", tab.priority).to_lowercase().into(),
        selected: tab.name == active_tab,
    }));

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
