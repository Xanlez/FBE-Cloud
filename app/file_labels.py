"""Человекочитаемые подписи типа/расширения файла."""

MIME_TO_EXT = {
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/json": "json",
    "application/xml": "xml",
    "text/plain": "txt",
    "text/csv": "csv",
    "text/html": "html",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/octet-stream": "bin",
}


def extension_from_name(file_name: str | None) -> str | None:
    if not file_name or "." not in file_name:
        return None
    ext = file_name.rsplit(".", 1)[-1].strip().lower()
    if not ext or len(ext) > 12 or "/" in ext or "\\" in ext:
        return None
    return ext


def format_file_type(file_name: str | None, mime_type: str | None = None) -> str:
    ext = extension_from_name(file_name)
    if ext:
        return f".{ext}"

    if mime_type:
        mime = mime_type.strip().lower()
        mapped = MIME_TO_EXT.get(mime)
        if mapped:
            return f".{mapped}"
        if "/" in mime:
            subtype = mime.split("/", 1)[1]
            if subtype in ("pdf", "json", "xml", "csv", "plain"):
                return f".{subtype.replace('plain', 'txt')}"
            if len(subtype) <= 8 and subtype.isalnum():
                return f".{subtype}"

    return "—"
