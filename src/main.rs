mod model;
mod storage;

use chrono::{Datelike, Local, NaiveDate, NaiveDateTime};
use slint::{ModelRc, SharedString, VecModel};

slint::include_modules!();

fn main() -> Result<(), slint::PlatformError> {
    let app = AppWindow::new()?;
    let store = storage::DataStore::new().ok();
    let data = store
        .as_ref()
        .map(|store| store.load())
        .unwrap_or_else(|| model::AppData::with_default_items(&storage::now_stamp()));

    let active_tab = SharedString::from("All");
    let tabs = build_tab_views(&data, active_tab.as_str());
    let tasks = build_task_views(&data, active_tab.as_str());
    let current = current_task(&data);
    let (done_today, done_month, done_year) = completion_counts(&data);

    app.set_app_title("focus".into());
    app.set_status_text(
        format!(
            "Rust + Slint ready | {} active | {} history",
            data.active.len(),
            data.history.len()
        )
        .into(),
    );
    app.set_footer_text(format_footer(&data).into());
    app.set_active_tab_name(active_tab.clone());
    app.set_pending_count(data.active.len() as i32);
    app.set_done_today_count(done_today as i32);
    app.set_done_month_count(done_month as i32);
    app.set_done_year_count(done_year as i32);
    app.set_on_top_enabled(data.settings.always_on_top);
    app.set_tabs(ModelRc::new(VecModel::from(tabs)));
    app.set_tasks(ModelRc::new(VecModel::from(tasks)));
    app.set_current_title(current.0.into());
    app.set_current_meta(current.1.into());

    #[allow(deprecated)]
    {
        app.window().set_always_on_top(data.settings.always_on_top);
    }

    app.run()
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

fn format_footer(data: &model::AppData) -> String {
    let visible = visible_items(data, "All").len();
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
