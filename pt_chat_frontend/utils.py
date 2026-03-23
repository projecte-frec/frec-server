from uuid import UUID


def uuid_to_html_id(id: UUID) -> str:
    return "uuid_" + str(id)

