mod model;
mod storage;

slint::include_modules!();

fn main() -> Result<(), slint::PlatformError> {
    let app = AppWindow::new()?;
    let store = storage::DataStore::new().ok();
    let data = store
        .as_ref()
        .map(|store| store.load())
        .unwrap_or_else(|| model::AppData::with_default_items(&storage::now_stamp()));

    app.set_app_title("focus".into());
    app.set_status_text(format!("Rust + Slint ready | {} task(s)", data.active.len()).into());
    app.set_footer_text(
        format!("Pending {} | Today 0 | Month 0 | Year 0", data.active.len()).into(),
    );
    app.set_on_top_enabled(data.settings.always_on_top);

    #[allow(deprecated)]
    {
        app.window().set_always_on_top(data.settings.always_on_top);
    }

    app.run()
}
