import reflex as rx

config = rx.Config(
    app_name="emma_web",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)