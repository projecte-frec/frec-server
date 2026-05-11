from enum import StrEnum
from uuid import UUID
import datastar_py
from markupsafe import Markup
import htpy
# fmt: off
from htpy import article, button, details, dialog, form, h2, h3, hr, html, head, body, img, label, li, meta, option, p, progress, select, span, summary, table, tbody, td, textarea, thead, title, link, script, nav, div, a, strong, section, fragment, tr, ul, th
# fmt: on
from datastar_py import attribute_generator as data
from frec_server.pages.common import data_on_enter, page_with_navbar, page_wrapper
from frec_server.persistence import models
from frec_server.utils import uuid_to_html_id


class Ids(StrEnum):
    MessagesList = "messages-list"
    MessageInputBox = "message-input-box"
    DeleteConvModal = "DeleteConvModal"
    CitationOverviewModal = "CitationOverviewModal"
    CitationOverviewModalHeading = "CitationOverviewModalHeading"
    CitationOverviewModalContent = "CitationOverviewModalContent"


class ChatSignals(StrEnum):
    UserCanSendInput = "can_send_input"
    UserMessage = "user_message"
    EditTitle = "edit_title"
    TitleValue = "title_value"
    ExternalToolOutputs = "external_tool_outputs"
    CitationOverviewModalHref = "CitationOverviewModalHref"
    DeleteConvModalTitle = "DeleteConvModalTitle"
    DeleteConvModalConvId = "DeleteConvModalConvId"


class JsFunctions(StrEnum):
    ScrollChatToBottom = "scrollChatToBottom"
    FocusInputBox = "focusInputBox"


def chat_page_scripts() -> htpy.Element:
    return script[
        Markup(
            f"""
                window.{JsFunctions.ScrollChatToBottom} = () => {{
                    setTimeout(() => {{
                        var msgList = document.getElementById("{Ids.MessagesList}")
                        msgList.parentElement.scrollTo(0, msgList.scrollHeight);
                    }}, 0);
                }};

                window.{JsFunctions.FocusInputBox} = () => {{
                    setTimeout(() => {{
                        var msgInputBox = document.getElementById("{Ids.MessageInputBox}")
                        msgInputBox.focus();
                    }}, 0);
                }};
                """
        )
    ]


def chat_page(
    username: str,
    conversation: models.Conversation | None,
    all_conversations: list[models.Conversation],
) -> htpy.Element:
    return page_with_navbar(
        username,
        div(
            ".flex.flex-row.flex-1.min-h-0",
            data.signals({ChatSignals.UserCanSendInput: True}),
        )[
            (
                div(data.init(f"@post('/attach_conversation_task/{conversation.id}')"))
                if conversation is not None
                else None
            ),
            chat_page_scripts(),
            div(
                ".max-w-60.flex-1.overflow-y-auto",
                style="margin-top:3px; border-right: solid 1px; border-color: #fff0ff; background-color: #fffbff; scrollbar-color: #00000011 #00000000; scrollbar-width: 1px;",
            )[
                conversation_history(
                    conversation.id if conversation is not None else None,
                    all_conversations,
                )
            ],
            div(".flex.flex-col.flex-1")[
                div(".flex.flex-col.flex-1.overflow-y-auto.p-4")[
                    div(".max-w-3xl.w-full.mx-auto", id=Ids.MessagesList)
                ],
                action_bar(conversation.id if conversation is not None else None),
            ],
            citation_overview_modal(),
            conversation_delete_modal(),
        ],
        navbar_center=(
            conversation_title(conversation) if conversation is not None else None
        ),
    )


def conversation_title(conversation: models.Conversation) -> htpy.Element:
    edit_action = f"""
        @post('/rename_conversation/{conversation.id}');
        ${ChatSignals.EditTitle} = false;
    """
    return div(
        ".flex.flex-row",
        data.signals(
            {
                ChatSignals.EditTitle: False,
                ChatSignals.TitleValue: conversation.name or "Xat sense nom",
            }
        ),
    )[
        button(
            ".btn.self-center.btn-xs.btn-square.btn-soft.bg-gray-100.border-gray-50",
            data.on(
                "click", f"@post('/generate_conversation_title/{conversation.id}');"
            ),
        )["✨"],
        button(
            ".btn.self-center.btn-xs.btn-square.btn-soft.bg-gray-100.border-gray-50",
            data.on(
                "click",
                f"""
                if (!${ChatSignals.EditTitle}) {{
                    ${ChatSignals.EditTitle} = true;
                }} else {{
                    {edit_action}
                }}
                """,
            ),
        )[
            span(data.show(f"!${ChatSignals.EditTitle}"))["✏️"],
            span(data.show(f"${ChatSignals.EditTitle}"))["✅"],
        ],
        div(".ml-2"),
        p(
            ".self-center.font-semibold",
            data.show(f"!${ChatSignals.EditTitle}"),
            data.text(f"${ChatSignals.TitleValue}"),
        ),
        htpy.input(
            ".self-center.input.input-sm",
            data.show(f"${ChatSignals.EditTitle}"),
            data.bind(ChatSignals.TitleValue),
            data_on_enter(edit_action),
            type="text",
        ),
    ]


def conversation_history(
    current_conversation_id: UUID | None, all_conversations: list[models.Conversation]
) -> htpy.Element:
    convs_by_date = reversed(sorted(all_conversations, key=lambda x: x.created_at))
    return div(".flex.flex-col.p-2.pl-0")[
        conversation_button(
            label="✏️ Xat nou", label_signal=None, target="/chat/new", conv_id=None
        ),
        hr(".my-2.mx-3.border-gray-200"),
        p(".text-sm.font-normal.ml-5.my-2.text-gray-500")["Els teus xats"],
        [
            conversation_button(
                label=c.name or "Xat sense nom",
                label_signal=(
                    ChatSignals.TitleValue if c.id == current_conversation_id else None
                ),
                target=f"/chat/{c.id}",
                conv_id=c.id,
            )
            for c in convs_by_date
        ],
    ]


def conversation_button(
    label: str, label_signal: ChatSignals | None, target: str, conv_id: UUID | None
) -> htpy.Element:
    on_delete_handler = f"""
        ${ChatSignals.DeleteConvModalTitle} = '{label}';
        ${ChatSignals.DeleteConvModalConvId} = '{conv_id}';
        {Ids.DeleteConvModal}.showModal();
    """

    action_delete = a(data.on("click", on_delete_handler))[
        img(
            src="/assets/icons/trash.svg",
            style="height:16px;",
        ),
        "Esborra",
    ]

    actions_menu = (
        (
            ul(
                ".dropdown.menu.w-52.rounded-box.bg-base-100.shadow-sm",
                popover=True,
                id=f"popover-{conv_id}",
                style=f"position-anchor:--anchor-{conv_id}",
            )[
                li[action_delete],
            ],
        )
        if conv_id is not None
        else None
    )

    return div(
        ".flex.flex-row.flex-1.px-2.group.relative.btn.btn-outline.border-0.rounded-none.transition-none.flex-1.rounded-xl.shadow-none.ml-3"
    )[
        a(
            ".py-2",
            href=target,
        )[
            p(
                ".font-normal.text-sm.text-left.whitespace-nowrap.overflow-hidden.text-ellipsis.w-full",
                *([data.text(f"${label_signal}")] if label_signal is not None else []),
                # HACK: Text ellipsis won't work otherise...
                style="width:180px;",
            )[label],
        ],
        button(
            ".absolute.right-2.top-1/2.-translate-y-1/2.opacity-0.group-hover:opacity-100.transition-opacity.p-2",
            # data.on("click", 'console.log("click");'),
            popovertarget=f"popover-{conv_id}",
            style=f"background-color:#e2e2e2; anchor-name:--anchor-{conv_id}",
        )[
            img(
                ".group-hover:opacity-100.transition-opacity",
                src="/assets/icons/gear.png",
                style="height:16px",
            )
        ],
        actions_menu,
    ]


def chat_message(
    html_id: str,
    role: models.MessageRole,
    tool_calls: list[models.ToolCall],
    citations: list[models.DocumentCitation],
) -> htpy.Element:
    contents = []
    if role == models.MessageRole.User:
        contents.append(
            div(".chat.chat-end.my-3")[div(".chat-bubble", id=html_id)["..."]]
        )
    else:
        contents.append(div(id=html_id)["..."])

    for tool_call in tool_calls:
        contents.append(tool_call_box(tool_call))

    if len(citations) > 0:
        contents.append(h2(".text-lg.font-semibold.mt-2.mb-1")["Fonts consultades:"])
    for citation in citations:
        if citation.page_start == 0 and citation.page_end == 0:
            pags = ""
        elif citation.page_start == citation.page_end:
            pags = f", pàg. {citation.page_start}"
        else:
            pags = f", pàgs. {citation.page_start}-{citation.page_end}"
        contents.append(
            p[
                span[citation.citation_literal],
                span[": "],
                a(
                    ".link.link-primary",
                    data.on(
                        "click",
                        f"@post('/show-document-citation-overview/{citation.id}')",
                    ),
                )[
                    span[citation.document_filename],
                ],
                span[pags],
            ]
        )

    return div[contents]


def conversation_delete_modal() -> htpy.Element:
    return dialog(
        ".modal.transition-none",
        id=Ids.DeleteConvModal,
    )[
        div(".modal-box")[
            h3(".text-lg.font-bold")["Esborrar Conversa"],
            div(".py-4")[
                "La conversa ",
                span(data.text(f"${ChatSignals.DeleteConvModalTitle}")),
                " s'esborrarà. Vols continuar?",
            ],
            div(".flex.flex-row.gap-2")[
                button(
                    ".btn.flex-1.btn-warning",
                    data.on(
                        "click",
                        f"@post('/delete_conversation/'+${ChatSignals.DeleteConvModalConvId})",
                    ),
                )["Esborra-la"],
                button(
                    ".btn.flex-1",
                    data.on(
                        "click",
                        f"{Ids.DeleteConvModal}.close();",
                    ),
                )["No l'esborris"],
            ],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]


def citation_overview_modal() -> htpy.Element:
    return dialog(
        ".modal.transition-none",
        data.signals({ChatSignals.CitationOverviewModalHref: ""}),
        id=Ids.CitationOverviewModal,
    )[
        div(".modal-box.w-11/12.max-w-5xl.flex.flex-col", style="height: 90vh;")[
            h2(".text-lg.font-bold", id=Ids.CitationOverviewModalHeading)["..."],
            div(
                ".px-2.m-2.overflow-auto.border-base-300.border.flex-1",
                style="background-color: #fefdff; focus:border-transparent;",
            )[
                div(".prose", id=Ids.CitationOverviewModalContent, style="")["..."],
            ],
            a(
                ".btn",
                data.attr({"href": f"${ChatSignals.CitationOverviewModalHref}"}),
                target="_blank",
                rel="noopener noreferrer",
            )["Veure document original"],
        ],
        form(".modal-backdrop", method="dialog")[button["close"]],
    ]


def tool_call_box(tool_call: models.ToolCall) -> htpy.Element:

    consent_status_box = None
    if tool_call.status == models.ToolCallStatus.PendingConfirm:
        consent_status_box = div(
            ".flex.flex-row.pb-3.px-3.gap-2",
        )[
            button(
                ".btn.btn-sm.btn-error.font-bold.text-white.flex-1",
                data.on("click", f"@post('/tool-consent/{tool_call.id}/reject')"),
            )["Reject"],
            button(
                ".btn.btn-sm.btn-accent.font-bold.text-white.flex-1",
                data.on("click", f"@post('/tool-consent/{tool_call.id}/accept')"),
            )["Accept"],
        ]
    elif tool_call.status == models.ToolCallStatus.PendingExecution:
        consent_status_box = div(
            ".flex.flex-row.pb-3.px-3.gap-2",
        )[
            div(".flex-1"),
            span(".loading.loading-dots.loading.md"),
            div(".flex-1"),
        ]

    pending_external_status_box = None
    if tool_call.status == models.ToolCallStatus.PendingExternalResult:
        pending_external_status_box = div(
            ".px-3.pb-3.flex.flex-col.gap-2",
            data.signals({ChatSignals.ExternalToolOutputs: {str(tool_call.id): ""}}),
        )[
            p["Output of the external tool:"],
            # p(data.text(f"${ChatSignals.ExternalToolOutputs}.{tool_call.id}")),
            textarea(
                ".textarea.w-full",
                data.bind(f"{ChatSignals.ExternalToolOutputs}.{tool_call.id}"),
                placeholder="Enter the tool's output here...",
            ),
            button(
                ".btn.btn-sm.btn-accent.font-bold.text-white.flex-1",
                data.on("click", f"@post('/external-tool-output/{tool_call.id}')"),
            )["Envia"],
        ]

    return div(
        ".collapse.bg-purple-100.border-base-300.border.my-5",
        id=uuid_to_html_id(tool_call.id),
    )[
        htpy.input(type="checkbox"),
        div(".collapse-title.pb-0.pt-3.px-2")[
            div(".flex.flex-row")[
                div(".badge.bg-purple-200.border-transparent")["Tool call"],
                div(".font-bold.ml-2")[f"{tool_call.toolset_key}.{tool_call.tool_key}"],
            ],
            div(".p-3")[
                [
                    div(".flex.flex-row")[
                        div(".font-semibold.mr-2")[k],
                        div[[p[str(line)] for line in str(v).splitlines()]],
                    ]
                    for k, v in tool_call.tool_args.items()
                ]
            ],
        ],
        consent_status_box,
        pending_external_status_box,
        (
            div(".collapse-content")[
                p(".font-semibold.ml-1")["Tool Answer:"],
                hr(".border-base-300"),
                div(".p-3")[
                    [
                        div(".flex.flex-row")[
                            div(".font-semibold.mr-2")[k],
                            div[[p[line] for line in str(v).splitlines()]],
                        ]
                        for k, v in (tool_call.tool_answer or {}).items()
                    ],
                ],
            ]
            if tool_call.status == models.ToolCallStatus.Completed
            else None
        ),
    ]


def action_bar(conversation_id: UUID | None) -> htpy.Element:
    send_msg_action = f"""
        ${ChatSignals.UserCanSendInput} = false; 
        @post('/send-message/{conversation_id or 'new'}');
        ${ChatSignals.UserMessage} = '';
        window.{JsFunctions.ScrollChatToBottom}();
    """
    return div[
        div(".flex.flex-row.p-4.gap-2")[
            htpy.textarea(
                ".input.flex-1",
                data.bind(ChatSignals.UserMessage),
                data.attr({"disabled": f"!${ChatSignals.UserCanSendInput}"}),
                data.effect(
                    f"""
                    window.{JsFunctions.ScrollChatToBottom}();
                    window.{JsFunctions.FocusInputBox}();
                """
                ),
                data_on_enter(send_msg_action),
                datastar_py.attribute_generator.on(
                    "input", "window.autoGrowTextarea(evt.target);"
                ),
                id=Ids.MessageInputBox,
                rows="1",
                style="resize:none; overflow-y: hidden; line-height: 36px; max-height: 120px",
                # type="text",
                placeholder="Escriu un missatge...",
                autocomplete="off",
            ),
            button(
                ".btn",
                data.attr({"disabled": f"!${ChatSignals.UserCanSendInput}"}),
                data.on("click", send_msg_action),
            )["Envia"],
        ],
    ]
