mod model;

slint::include_modules!();

fn main() -> Result<(), slint::PlatformError> {
    let app = AppWindow::new()?;
    let data = model::AppData::default();

    app.set_app_title("focus".into());
    app.set_status_text(
        format!(
            "Rust + Slint scaffold ready | {} tab(s)",
            data.settings.tabs.len()
        )
        .into(),
    );
    app.set_footer_text("Pending 0 | Today 0 | Month 0 | Year 0".into());
    app.set_on_top_enabled(true);

    #[allow(deprecated)]
    {
        app.window().set_always_on_top(true);
    }

    app.run()
}
