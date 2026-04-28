from uuid import UUID
import datastar_py
from datastar_py import attribute_generator as data
import htpy
import fastapi
import markdown
import markdown.treeprocessors
from frec_server.persistence import models
from commonmark import Parser, HtmlRenderer
from bs4 import BeautifulSoup

# fmt: off
from htpy import article, button, details, form, h2, html, head, body, img, label, li, meta, option, p, progress, select, span, summary, table, tbody, td, thead, title, link, script, nav, div, a, strong, section, fragment, tr, ul
# fmt: on


def set_request_user(request: fastapi.Request, user: models.User):
    request.state.user = user


def get_request_user(request: fastapi.Request) -> models.User:
    user = request.state.user
    if type(user) is not models.User:
        raise Exception("No user id in request")
    return user


def get_request_user_id(request: fastapi.Request) -> UUID:
    return get_request_user(request).id


def set_request_user_session(request: fastapi.Request, user_session_id: UUID):
    request.state.user_session_id = user_session_id


def get_request_user_session(request: fastapi.Request) -> UUID:
    user_session_id = request.state.user_session_id
    if type(user_session_id) is not UUID:
        raise Exception("No user id in request")
    return user_session_id


def page_wrapper(contents: htpy.Element) -> htpy.Element:
    return html[
        head[
            title["FREC - Xat"],
            meta(charset="utf-8"),
            meta(name="viewport", content="width=device-width, initial-scale=1"),
            link(rel="stylesheet", href="/assets/daisyui-5.5.5.min.css"),
            script(src="/assets/tailwind-4.1.17.min.js"),
            script(type="module", src="/assets/datastar-1.0.0-RC.6.min.js"),
            script(src="/assets/cookieManager.js"),
            script(src="/assets/textareaAutogrowth.js"),
        ],
        body(".h-screen")[contents],
    ]


def navbar(username: str | None, center: htpy.Element | None) -> htpy.Element:
    return div(".flex.flex-row.align-items-center.bg-base-100.shadow-xs.min-h-12.pl-3")[
        a(".btn.self-center.btn-ghost.text-xl", href="/")[
            img(src="/assets/Logo Frec Black.svg", alt="Frec Logo", style="height:35px")
        ],
        div(".flex-1"),
        center,
        div(".flex-1"),
        ul(".menu.menu-horizontal.px-1.mr-3")[
            li[a(href="/chat")["Xat"]],
            li[a(href="/settings")["Configuració"]],
            (
                li[
                    div(
                        ".dropdown.dropdown-end.border.rounded-sm.ml-2.border-gray-400"
                    )[
                        div(".font-semibold", tabindex=0)[username],
                        ul(
                            ".menu.menu-sm.dropdown-content.bg-base-100.mt-20.rounded-box.z-1.mt-3.w-40.p-2.shadow",
                            tabindex=-1,
                        )[
                            li[
                                button(
                                    ".justify-between",
                                    data.on("click", "@post('/log-out')"),
                                )["Tanca la sessió"]
                            ]
                        ],
                    ]
                ]
                if username is not None
                else None
            ),
        ],
    ]


def page_with_navbar(
    username: str | None,
    contents: htpy.Element,
    navbar_center: htpy.Element | None = None,
) -> htpy.Element:
    return page_wrapper(
        div(
            ".flex.flex-col.h-screen.overflow-hidden",
        )[
            div(
                ".flex.flex-row.min-h-12.shrink-0",
            )[
                div(".flex-1")[navbar(username, navbar_center),],
            ],
            div(".flex-1.flex.flex-col.min-h-0")[contents],
        ]
    )


def data_on_enter(action: str) -> datastar_py.attributes.OnAttr:
    return datastar_py.attribute_generator.on(
        "keypress",
        # https://stackoverflow.com/a/10905506
        f"""
        var code = (evt.keyCode ? evt.keyCode : evt.which);
        if (code == 13 && !evt.shiftKey) {{ // Enter keycode (without shift)
            evt.preventDefault();
            {action}
        }}
        """,
    )


def markdown_to_html(
    md_text: str, cleanup_links: bool = False, remove_images: bool = False
) -> str:
    parser = Parser()
    renderer = HtmlRenderer()

    ast = parser.parse(md_text)
    html = renderer.render(ast)

    soup = BeautifulSoup(html, "html.parser")

    # Headings
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        tag["class"] = tag.get("class", []) + [  # type:ignore
            "font-bold",
            "mt-2",
            "mb-2",
        ]

    # Paragraphs
    for tag in soup.find_all("p"):
        tag["class"] = tag.get("class", []) + ["leading-relaxed"]  # type:ignore

    # Links
    for tag in soup.find_all("a"):
        tag["class"] = tag.get("class", []) + ["link", "link-primary"]  # type:ignore
        if cleanup_links:
            tag["href"] = ""

    # Lists
    for tag in soup.find_all("ul"):
        tag["class"] = tag.get("class", []) + [  # type:ignore
            "list-disc",
            "ml-6",
            "my-4",
        ]

    # Images
    if remove_images:
        for tag in soup.find_all("img"):
            tag.decompose()

    for tag in soup.find_all("ol"):
        tag["class"] = tag.get("class", []) + [  # type:ignore
            "list-decimal",
            "ml-6",
            "my-4",
        ]

    for tag in soup.find_all("li"):
        tag["class"] = tag.get("class", []) + ["my-1"]  # type:ignore

    # Blockquotes
    for tag in soup.find_all("blockquote"):
        tag["class"] = tag.get("class", []) + [  # type:ignore
            "border-l-4",
            "border-base-300",
            "pl-4",
            "italic",
            "my-4",
        ]

    # Code blocks
    for tag in soup.find_all("pre"):
        tag["class"] = tag.get("class", []) + [  # type:ignore
            "bg-base-200",
            "p-4",
            "rounded-lg",
            "overflow-x-auto",
        ]

    for tag in soup.find_all("code"):
        tag["class"] = tag.get("class", []) + ["font-mono", "text-sm"]  # type:ignore

    return str(soup)
