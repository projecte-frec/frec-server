from enum import StrEnum
from uuid import UUID
import datastar_py
from markupsafe import Markup
import htpy
# fmt: off
from htpy import article, button, details, form, h2, hr, html, head, body, label, li, meta, option, p, progress, select, span, summary, table, tbody, td, thead, title, link, script, nav, div, a, strong, section, fragment, tr, ul, th
# fmt: on
from datastar_py import attribute_generator as data
from frec_server.pages.common import page_wrapper
from frec_server.persistence import models
from frec_server.utils import uuid_to_html_id

class Ids(StrEnum):
    ErrorText = "error_text"

def login_page():
    return page_wrapper(
        div(".flex.justify-center")[
            div(".card.w-96.bg-base-100.shadow-xl.mt-20.mb-20")[
                form(".card-body")[
                    h2(".card-title")["Accedeix a FREC"],
                    div(".items-center.mt-2.w-full")[
                        label(
                            ".input.input-bordered.flex.items-center.gap-2.mb-2.w-full"
                        )[
                            Markup(
                                """
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4 opacity-70">
                                    <path d="M2.5 3A1.5 1.5 0 0 0 1 4.5v.793c.026.009.051.02.076.032L7.674 8.51c.206.1.446.1.652 0l6.598-3.185A.755.755 0 0 1 15 5.293V4.5A1.5 1.5 0 0 0 13.5 3h-11Z" />
                                    <path d="M15 6.954 8.978 9.86a2.25 2.25 0 0 1-1.956 0L1 6.954V11.5A1.5 1.5 0 0 0 2.5 13h11a1.5 1.5 0 0 0 1.5-1.5V6.954Z" />
                                 </svg>
                                """
                            ),
                            htpy.input(".grow", type="text", name="username", placeholder="Nom d'Usuari"),
                        ],
                        label(
                            ".input.input-bordered.flex.items-center.gap-2.mb-2.w-full"
                        )[
                            Markup(
                                """
                                 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4 opacity-70">
                                    <path fill-rule="evenodd" d="M14 6a4 4 0 0 1-4.899 3.899l-1.955 1.955a.5.5 0 0 1-.353.146H5v1.5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1-.5-.5v-2.293a.5.5 0 0 1 .146-.353l3.955-3.955A4 4 0 1 1 14 6Zm-4-2a.75.75 0 0 0 0 1.5.5.5 0 0 1 .5.5.75.75 0 0 0 1.5 0 2 2 0 0 0-2-2Z" clip-rule="evenodd" />
                                 </svg>
                                """
                            ),
                            htpy.input(
                                ".grow", type="password", name="password", placeholder="Contrasenya"
                            ),
                        ],
                    ],
                    p(".text-red-700", id=Ids.ErrorText),
                    div(".card-actions.justify-end")[
                        button(
                            ".btn.btn-primary.w-full",
                            data.on(
                                "click", "@post('/login/auth', {contentType: 'form'})"
                            ),
                        )["Entra"]
                    ],
                ]
            ]
        ]
    )
