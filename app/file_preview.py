from models import CloudFile

TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json", ".log", ".xml", ".html", ".htm", ".py", ".js", ".css")


def can_preview_file(row: CloudFile) -> bool:
    if row.web_view_link and not row.storage_name:
        return True
    if not row.storage_name:
        return False
    mime = (row.mime_type or "").lower()
    name = (row.file_name or "").lower()
    if mime.startswith("image/"):
        return True
    if mime == "application/pdf" or name.endswith(".pdf"):
        return True
    if mime.startswith("video/"):
        return True
    if mime.startswith("audio/"):
        return True
    if mime.startswith("text/"):
        return True
    return name.endswith(TEXT_EXTENSIONS)


def is_image_file(row: CloudFile) -> bool:
    mime = (row.mime_type or "").lower()
    return mime.startswith("image/")
