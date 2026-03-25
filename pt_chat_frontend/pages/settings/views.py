# fmt: off
from enum import StrEnum
from uuid import UUID
from htpy import article, button, details, dialog, fieldset, form, h1, h2, h3, hr, html, head, body, label, legend, li, meta, option, p, progress, select, span, summary, table, tbody, td, thead, title, link, script, nav, div, a, strong, section, fragment, tr, ul, th
# fmt: on
import htpy
from datastar_py import attribute_generator as data
from platformdirs import user_desktop_dir

from frec_server import configuration
from frec_server.pages.common import page_with_navbar, page_wrapper
from frec_server.persistence import models


class Ids(StrEnum):
    ToolsetStatusModal = "toolset_status_modal"
    ToolsetDeleteModal = "toolset_delete_modal"
    ToolsetModalHeading = "toolset_modal_heading"
    ToolsetModalContents = "toolset_modal_contents"
    TokenCreateModal = "token_create_modal"
    TokenDeleteModal = "token_delete_modal"
    TokenModalContents = "token_modal_contents"
    TokenSectionTable = "token_section_table"
    UserDeleteModal = "user_delete_modal"

    @staticmethod
    def tool_permission_id(id: UUID) -> str:
        return "perm_" + str(id).replace("-", "_")


class Signals(StrEnum):
    ToolsetStatus = "toolset_status"
    ToolsetEnabled = "toolset_enabled"
    ToolsetCrudPageMsg = "toolset_crud_page_msg"
    ToolsetCrudPageError = "toolset_crud_page_error"
    TokenDeleteId = "token_delete_id"
    TokenDeleteLastDigits = "token_delete_last_digits"
    TokenDeleteCreatedAt = "token_delete_created_at"
    UserDeleteId = "user_delete_id"
    UserDeleteUsername = "user_delete_username"
    UserCrudPageMsg = "user_crud_page_msg"
    UserCrudPageError = "user_crud_page_error"


class ToolsetStatus(StrEnum):
    Pending = "pending"
    Online = "active"
    Offline = "offline"


def settings_page(
    username: str,
    current_user_id: UUID,
    users: list[models.User] | None,
    toolsets_and_cfg: list[tuple[str, configuration.Toolset, models.ToolsetConfig]],
    tokens: list[models.UserToken],
) -> htpy.Element:
    return page_with_navbar(
        username,
        div(".p-4.overflow-auto")[
            (
                user_management_section(current_user_id, users)
                if users is not None
                else None
            ),
            tool_settings_section(toolsets_and_cfg),
            tokens_section(tokens),
            div(".max-w-3xl.m-auto")[
                toolset_status_modal(),
                new_token_modal(),
                token_delete_modal(),
                user_delete_modal(),
            ],
        ],
    )


def tool_settings_section(
    toolsets_and_cfg: list[tuple[str, configuration.Toolset, models.ToolsetConfig]],
) -> list[htpy.Element]:
    return [
        div(".flex.flex-row.items-center.py-4")[
            h1(".text-lg.font-bold")["Opcions d'Eines"],
            div(".flex-1"),
        ],
        div(".overflow-x-auto.rounded-box.border.border-gray-200.bg-base-100")[
            table(".table")[
                thead[
                    tr[
                        th["Eina"],
                        th["Tipus"],
                        th["Estat"],
                        th["Activada"],
                        th["Gestiona"],
                    ]
                ],
                tbody[
                    [
                        tr[
                            td[toolset.name],
                            td[toolset.kind.capitalize()],
                            td[toolset_status_badge(toolset_key)],
                            td[toolset_enable_toggle(toolset_key, toolset_cfg.enabled)],
                            td[toolset_controls(toolset_key)],
                        ]
                        for toolset_key, toolset, toolset_cfg in toolsets_and_cfg
                    ]
                ],
            ],
        ],
    ]


def toolset_status_modal() -> htpy.Element:
    return dialog(".modal.transition-none", id=Ids.ToolsetStatusModal)[
        div(".modal-box")[
            h3(".text-lg.font-bold", id=Ids.ToolsetModalHeading)["..."],
            p(".py-4", id=Ids.ToolsetModalContents)["Press esc to close"],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]


def toolset_status_badge(toolset_key: str) -> htpy.Element:
    signal = f"${Signals.ToolsetStatus}.{str(toolset_key)}"
    badge_classes = ".badge.badge-soft.py-0.px-2.text-xs.rounded-sm.min-w-18"
    return div(
        ".tooltip",
        data.signals(
            {Signals.ToolsetStatus: {str(toolset_key): ToolsetStatus.Pending}}
        ),
        data.init(f"@post('/fetch_toolset_status/{toolset_key}')"),
        data.on(
            "click",
            f"""
        @post('fetch_toolset_status/{toolset_key}');
        {Ids.ToolsetStatusModal}.showModal();
        """,
        ),
        data_tip="click for details",
    )[
        span(
            f"{badge_classes}.badge-success",
            data.show(f"{signal} === '{ToolsetStatus.Online}'"),
        )[div(".status.status-success"), "Active"],
        span(
            f"{badge_classes}.badge-error",
            data.show(f"{signal} === '{ToolsetStatus.Offline}'"),
        )[div(".status.status-error"), "Offline"],
        span(
            f"{badge_classes}",
            data.show(f"{signal} === '{ToolsetStatus.Pending}'"),
        )[span(".loading.loading-dots.loading-xs")],
    ]


def toolset_enable_toggle(toolset_key: str, is_enabled: bool) -> htpy.VoidElement:
    return htpy.input(
        ".toggle.toggle-xs",
        data.attr({"checked": f"${Signals.ToolsetEnabled}.{toolset_key}"}),
        data.signals({Signals.ToolsetEnabled: {str(toolset_key): is_enabled}}),
        data.on("click", f"@post('/toggle_toolset_enabled/{toolset_key}')"),
        type="checkbox",
    )


def toolset_controls(toolset_key: str) -> htpy.Element:
    return div(".flex.flex-row.gap-1")[
        a(
            ".btn.btn-square.w-6.h-6.text-xs",
            href=f"/settings/tool-conn/{toolset_key}",
        )["🔧"],
    ]


def permission_tri_state_switch(
    perm: models.ToolPermission,
) -> htpy.Element:
    def make_button(kind: models.ToolPermissionKind, index: int) -> htpy.Element:
        is_selected = perm.kind == kind
        class_name = ".py-1.px-1.text-xs.font-medium.focus:outline-none.transition-colors.rounded-none."
        if is_selected:
            class_name += ".btn-accent.text-white "
        else:
            class_name += ".bg-white.text-gray-700.hover:bg-gray-50"
        # Middle separators between segments
        if index > 0:
            class_name += ".border-l.border-gray-300"
        return button(
            ".btn.btn-xs.w-10.transition" + class_name,
            data.on("click", f"@post('/set_tool_permission/{perm.id}/{kind}')"),
            style="font-size: 8pt",
        )[kind.display()]

    return div(
        ".flex.flex-row.inline-flex.rounded-md.border.border-gray-300.overflow-hidden.shadow-sm.bg-white.gap-0",
        id=Ids.tool_permission_id(perm.id),
    )[(make_button(kind, idx) for idx, kind in enumerate(models.ToolPermissionKind))]


def tool_settings_page(
    username: str,
    toolset: configuration.Toolset,
    permissions: list[models.ToolPermission],
) -> htpy.Element:
    def form_field(
        label: str, contents: htpy.Element | htpy.VoidElement
    ) -> htpy.Fragment:
        return fragment[htpy.label(".label")[label], contents]

    return page_with_navbar(
        username,
        div(".p-4.overflow-y-auto")[
            div(".max-w-3xl.m-auto")[
                div(".flex.flex-row.items-center.gap-2.pb-2")[
                    div(".flex.self-center")[
                        a(".btn.btn-outline.btn-square.btn-xs", href="/settings")["<"]
                    ],
                    h1(".flex.text-lg.font-bold.self-center")[
                        f"Editar els permisos de l'eina: {toolset.name}"
                    ],
                ],
                (
                    fieldset(
                        ".fieldset.bg-base-200.border-base-300.rounded-box.w-full.border.p-4"
                    )[
                        legend(".fieldset-legend")["Permissions"],
                        ul(".list")[
                            (
                                li(".list-row")[
                                    div(".flex.flex-row.gap-2.items-center")[
                                        permission_tri_state_switch(perm),
                                        perm.tool_key,
                                    ]
                                ]
                                for perm in permissions
                            )
                        ],
                    ]
                    if len(permissions) > 0
                    else None
                ),
            ]
        ],
    )


def tokens_section(
    tokens: list[models.UserToken],
) -> list[htpy.Element]:
    return [
        div(".flex.flex-row.items-center.py-4")[
            h1(".text-lg.font-bold")["Tokens d'API"],
            div(".flex-1"),
            button(
                ".btn.btn-outline.btn-sm",
                data.on("click", "@post('/create_new_user_token')"),
            )["+ Nou Token"],
        ],
        token_section_table(tokens),
    ]


def token_section_table(tokens: list[models.UserToken]) -> htpy.Element:
    return div(
        ".overflow-x-auto.rounded-box.border.border-gray-200.bg-base-100",
        id=Ids.TokenSectionTable,
    )[
        table(".table")[
            thead[
                tr[
                    th["Token"],
                    th["Data de creació"],
                    th["Gestiona"],
                ]
            ],
            tbody[
                [
                    tr[
                        td[f"{models.UserToken.token_prefix()}..{utk.last_chars}"],
                        td[utk.created_at.strftime("%Y-%m-%d %H:%M:%S")],
                        td[
                            button(
                                ".btn.btn-square.w-6.h-6.text-xs",
                                data.on(
                                    "click",
                                    f"""
                                    ${Signals.TokenDeleteId} = '{utk.token_sha512}';
                                    ${Signals.TokenDeleteCreatedAt} = '{utk.created_at.strftime("%Y-%m-%d %H:%M:%S")}';
                                    ${Signals.TokenDeleteLastDigits} = '{models.UserToken.token_prefix()}..{utk.last_chars}';
                                    {Ids.TokenDeleteModal}.showModal();
                                    """,
                                ),
                            )["🗑️"]
                        ],
                    ]
                    for utk in tokens
                ]
            ],
        ],
    ]


def new_token_modal() -> htpy.Element:
    return dialog(
        ".modal.transition-none",
        id=Ids.TokenCreateModal,
    )[
        div(".modal-box")[
            h3(".text-lg.font-bold")["El teu nou token"],
            p[
                "Copia'l i guarda'l en un lloc segur. No el podràs tornar a obtenir un cop tanquis aquesta finestra."
            ],
            p(
                ".p-1.my-6.rounded-sm.border-1.border-solid.border-gray-400.bg-purple-50",
                id=Ids.TokenModalContents,
            )[
                # NOTE: The generated token will be put here by the backend by patching this
                # element's inner HTML
                ""
            ],
            div(".flex.flex-row.gap-2")[
                div(".flex-1"),
                button(
                    ".btn.flex-1",
                    data.on(
                        "click",
                        f"{Ids.TokenCreateModal}.close();",
                    ),
                )["Ok"],
            ],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]


def token_delete_modal() -> htpy.Element:
    return dialog(
        ".modal.transition-none",
        id=Ids.TokenDeleteModal,
    )[
        div(".modal-box")[
            h3(".text-lg.font-bold")["Esborrar token"],
            div(".py-4")[
                "El token s'esborrarà. No es permetrà cap més accés fent servir aquest token. Aquesta acció és irreversible. Vols continuar?",
                div(".py-2")[
                    p[
                        span(".font-bold")["Token: "],
                        span(data.text(f"${Signals.TokenDeleteLastDigits}")),
                    ],
                    p[
                        span(".font-bold")["Data de creació: "],
                        span(data.text(f"${Signals.TokenDeleteCreatedAt}")),
                    ],
                ],
            ],
            div(".flex.flex-row.gap-2")[
                button(
                    ".btn.flex-1.btn-warning",
                    data.on(
                        "click",
                        f"@post('/delete_user_token/'+${Signals.TokenDeleteId})",
                    ),
                )["Esborra'l"],
                button(
                    ".btn.flex-1",
                    data.on(
                        "click",
                        f"{Ids.TokenDeleteModal}.close();",
                    ),
                )["No l'esborris"],
            ],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]


def user_management_section(
    current_user_id: UUID,
    users: list[models.User],
) -> list[htpy.Element]:
    return [
        div(".flex.flex-row.items-center.py-4")[
            h1(".text-lg.font-bold")["Gestió d'Usuaris"],
            div(".flex-1"),
            a(".btn.btn-outline.btn-sm", href="/settings/user/new")["+ Nou Usuari"],
        ],
        user_management_section_table(current_user_id, users),
    ]


def user_management_section_table(
    current_user_id: UUID, users: list[models.User]
) -> htpy.Element:
    return div(
        ".overflow-x-auto.rounded-box.border.border-gray-200.bg-base-100",
        id=Ids.TokenSectionTable,
    )[
        table(".table")[
            thead[
                tr[
                    th["Nom"],
                    th["Data de creació"],
                    th["Administrador"],
                    th["Gestiona"],
                ]
            ],
            tbody[
                [
                    tr[
                        td[user.username],
                        td[user.created_at.strftime("%Y-%m-%d %H:%M:%S")],
                        td[str(user.is_admin)],
                        (
                            td[
                                button(
                                    ".btn.btn-square.w-6.h-6.text-xs",
                                    data.on(
                                        "click",
                                        f"""
                                    ${Signals.UserDeleteUsername} = '{user.username}';
                                    ${Signals.UserDeleteId} = '{user.id}';
                                    {Ids.UserDeleteModal}.showModal();
                                    """,
                                    ),
                                )["🗑️"],
                                a(
                                    ".btn.btn-square.w-6.h-6.text-xs",
                                    href=f"/settings/user/{user.id}",
                                )["✏️"],
                            ]
                            if current_user_id != user.id
                            else td["-"]
                        ),
                    ]
                    for user in users
                ]
            ],
        ],
    ]


def user_settings_page(
    username: str,
    user: models.User | None,
) -> htpy.Element:
    def form_field(
        label: str, contents: htpy.Element | htpy.VoidElement
    ) -> htpy.Fragment:
        return fragment[htpy.label(".label")[label], contents]

    return page_with_navbar(
        username,
        div(".p-4.overflow-y-auto")[
            div(".max-w-3xl.m-auto")[
                div(".flex.flex-row.items-center.gap-2.pb-2")[
                    div(".flex.self-center")[
                        a(".btn.btn-outline.btn-square.btn-xs", href="/settings")["<"]
                    ],
                    h1(".flex.text-lg.font-bold.self-center")[
                        (
                            f"Editant Usuari: {user.username}"
                            if user is not None
                            else "Nou Usuari"
                        )
                    ],
                ],
                div(
                    data.signals(
                        {
                            "username": (user.username if user is not None else ""),
                            "password": "",
                            "password_confirm": "",
                            "is_admin": user.is_admin if user is not None else False,
                        }
                    )
                )[
                    fieldset(
                        ".fieldset.bg-base-200.border-base-300.rounded-box.w-full.border.p-4"
                    )[
                        legend(".fieldset-legend")["Opcions Generals"],
                        form_field(
                            "Nom d'Usuari",
                            htpy.input(
                                ".input",
                                data.bind("username"),
                                type="text",
                                name="username",
                            ),
                        ),
                        form_field(
                            "Contrasenya" + (" (deixa el camp buit si no la vols canviar)" if user is not None else ""),
                            htpy.input(
                                ".input",
                                data.bind("password"),
                                type="password",
                                name="password",
                            ),
                        ),
                        form_field(
                            "Confirma la contrasenya",
                            htpy.input(
                                ".input",
                                data.bind("confirm_password"),
                                type="password",
                                name="confirm_password",
                            ),
                        ),
                        form_field(
                            "És administrador?",
                            htpy.input(
                                ".checkbox",
                                data.bind("is_admin"),
                                type="checkbox",
                                name="is_admin",
                            ),
                        ),
                        div(".flex.flex-row.p-2")[
                            div(".flex-1"),
                            p(
                                ".self-center.p-2.text-md",
                                data.text(f"${Signals.UserCrudPageMsg}"),
                            ),
                            button(
                                ".btn.btn-primary.btn-md",
                                data.on(
                                    "click",
                                    (
                                        f"@post('/update_user/{user.id}')"
                                        if user is not None
                                        else f"@post('/create_user');"
                                    ),
                                ),
                            )["Actualitza" if user is not None else "Crea"],
                        ],
                        p(
                            ".text-md.text-red-600",
                            data.text(f"${Signals.UserCrudPageError}"),
                        ),
                    ],
                ],
            ]
        ],
    )


def user_delete_modal() -> htpy.Element:
    return dialog(
        ".modal.transition-none",
        id=Ids.UserDeleteModal,
    )[
        div(".modal-box")[
            h3(".text-lg.font-bold")["Esborra l'usuari"],
            div(".py-4")[
                "L'usuari s'esborrarà. Aquesta acció és irreversible. Vols continuar?",
                div(".py-2")[
                    p[
                        span(".font-bold")["Usuari: "],
                        span(data.text(f"${Signals.UserDeleteUsername}")),
                    ],
                ],
            ],
            div(".flex.flex-row.gap-2")[
                button(
                    ".btn.flex-1.btn-warning",
                    data.on(
                        "click",
                        f"@post('/delete_user/'+${Signals.UserDeleteId})",
                    ),
                )["Esborra'l"],
                button(
                    ".btn.flex-1",
                    data.on(
                        "click",
                        f"{Ids.UserDeleteModal}.close();",
                    ),
                )["No l'esborris"],
            ],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]
